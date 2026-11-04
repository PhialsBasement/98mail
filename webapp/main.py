import os
import secrets
import shutil
import tempfile
from datetime import timezone
from email.utils import parsedate_to_datetime

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mail_backend import _sanitize_filename
from webapp.auth import Session, create_session, destroy_session, get_session, require_session, session_exists
from webapp.config import config
from webapp.email_render import render_message_html


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="98Mail Webmail")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'none'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; img-src 'self' data:; font-src 'none'; "
        "connect-src 'self'; frame-src 'self';",
    )
    return response


@app.get("/")
def index(request: Request):
    if session_exists(request.cookies.get("session_id")):
        return RedirectResponse("/mail", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"config": config, "error": None},
    )


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    username = username.strip()
    if not username or not password:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"config": config, "error": "Username and password are required."},
            status_code=400,
        )

    try:
        token = create_session(username, password)
    except Exception as exc:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"config": config, "error": f"Login failed: {exc}"},
            status_code=401,
        )

    response = RedirectResponse("/mail", status_code=303)
    response.set_cookie(
        "session_id",
        token,
        httponly=True,
        secure=config.session_secure,
        samesite="lax",
        max_age=config.session_max_age,
    )
    return response


@app.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    token = request.cookies.get("session_id")
    session = get_session(token)
    if session is None or not secrets.compare_digest(session.csrf_token, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    destroy_session(token)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session_id")
    return response


@app.get("/mail")
def mail(request: Request):
    session = get_session(request.cookies.get("session_id"))
    if session is None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="mail.html",
        context={"config": config, "username": session.username, "csrf_token": session.csrf_token},
    )


@app.get("/games")
def games(request: Request):
    session = get_session(request.cookies.get("session_id"))
    if session is None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="games.html",
        context={"config": config, "username": session.username},
    )


def check_csrf(session: Session, request: Request) -> None:
    token = request.headers.get("X-CSRF-Token", "")
    if not token or not secrets.compare_digest(token, session.csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def parse_date(raw_date: str):
    try:
        dt = parsedate_to_datetime(raw_date)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def message_timestamp(raw_date: str) -> float:
    dt = parse_date(raw_date)
    return dt.timestamp() if dt else 0.0


def iso_date(raw_date: str) -> str | None:
    dt = parse_date(raw_date)
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def serialize_message(msg) -> dict:
    return {
        "uid": msg.uid,
        "subject": msg.subject,
        "sender": msg.sender,
        "to": msg.to,
        "cc": msg.cc,
        "date": msg.date,
        "date_iso": iso_date(msg.date),
        "seen": msg.seen,
        "size": msg.size,
        "has_attachments": msg.has_attachments,
    }


@app.get("/api/folders")
def api_folders(session: Session = Depends(require_session)):
    return {"folders": session.client.list_folders()}


@app.get("/api/messages")
def api_messages(
    folder: str = "INBOX",
    limit: int = 50,
    session: Session = Depends(require_session),
):
    limit = max(1, min(limit, 100))
    messages = session.client.fetch_message_list(folder, limit)
    messages.sort(key=lambda m: (message_timestamp(m.date), m.uid), reverse=True)
    return {"folder": folder, "messages": [serialize_message(m) for m in messages]}


@app.get("/api/messages/{uid}")
def api_message(
    uid: int,
    folder: str = "INBOX",
    load_images: bool = False,
    session: Session = Depends(require_session),
):
    cache_key = (folder, uid)
    msg = session.message_cache.get(cache_key)
    if msg is None:
        msg = session.client.fetch_message(uid, folder)
        if msg is None:
            raise HTTPException(status_code=404, detail="Message not found")
        session.message_cache[cache_key] = msg

    if not msg.seen:
        session.client.mark_seen(uid, folder)
        msg.seen = True

    return {
        "uid": msg.uid,
        "subject": msg.subject,
        "sender": msg.sender,
        "to": msg.to,
        "cc": msg.cc,
        "date": msg.date,
        "date_iso": iso_date(msg.date),
        "seen": msg.seen,
        "message_id": msg.message_id,
        "in_reply_to": msg.in_reply_to,
        "body_text": msg.body_text,
        "html": render_message_html(msg, load_images=load_images),
        "attachments": [
            {"index": i, "filename": a["filename"], "content_type": a["content_type"]}
            for i, a in enumerate(msg.attachments)
        ],
    }


@app.post("/api/messages/{uid}/seen")
def mark_seen(request: Request, uid: int, folder: str = "INBOX", session: Session = Depends(require_session)):
    check_csrf(session, request)
    session.client.mark_seen(uid, folder)
    cached = session.message_cache.get((folder, uid))
    if cached:
        cached.seen = True
    return {"ok": True}


@app.post("/api/messages/{uid}/unseen")
def mark_unseen(request: Request, uid: int, folder: str = "INBOX", session: Session = Depends(require_session)):
    check_csrf(session, request)
    session.client.mark_unseen(uid, folder)
    session.message_cache.pop((folder, uid), None)
    return {"ok": True}


@app.delete("/api/messages/{uid}")
def delete_message(request: Request, uid: int, folder: str = "INBOX", session: Session = Depends(require_session)):
    check_csrf(session, request)
    session.client.delete_message(uid, folder)
    session.message_cache.pop((folder, uid), None)
    return {"ok": True}


@app.get("/api/messages/{uid}/attachments/{index}")
def get_attachment(
    uid: int,
    index: int,
    folder: str = "INBOX",
    session: Session = Depends(require_session),
):
    msg = session.client.fetch_message(uid, folder)
    if msg is None or index < 0 or index >= len(msg.attachments):
        raise HTTPException(status_code=404, detail="Attachment not found")

    att = msg.attachments[index]
    data = att.get("data")
    if data is None:
        raise HTTPException(status_code=404, detail="Attachment has no data")

    filename = _sanitize_filename(att.get("filename") or "attachment")
    return Response(
        content=data,
        media_type=att.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/send")
def send_message(
    to: str = Form(...),
    subject: str = Form(""),
    body: str = Form(""),
    cc: str = Form(""),
    in_reply_to: str = Form(""),
    references: str = Form(""),
    csrf_token: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    session: Session = Depends(require_session),
):
    if not secrets.compare_digest(csrf_token, session.csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    if not to.strip():
        raise HTTPException(status_code=400, detail="Recipient is required")

    tmpdir = tempfile.mkdtemp(prefix="98mail_attachments_")
    paths: list[str] = []
    try:
        for upload in files:
            if not upload.filename:
                continue
            name = _sanitize_filename(upload.filename)
            path = os.path.join(tmpdir, name)
            with open(path, "wb") as out:
                out.write(upload.file.read())
            paths.append(path)

        session.client.send_message(
            to=to.strip(),
            subject=subject.strip(),
            body=body,
            cc=cc.strip(),
            attachments=paths or None,
            in_reply_to=in_reply_to,
            references=references,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True}
