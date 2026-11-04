import secrets
import threading
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from mail_backend import MailClient
from webapp.mail_service import make_client


@dataclass
class Session:
    username: str
    client: MailClient
    csrf_token: str
    message_cache: dict[tuple[str, int], object] = field(default_factory=dict)


_sessions: dict[str, Session] = {}
_lock = threading.Lock()


def session_exists(token: str | None) -> bool:
    return bool(token) and token in _sessions


def get_session(token: str | None) -> Session | None:
    if not token:
        return None
    return _sessions.get(token)


def create_session(username: str, password: str) -> str:
    client = make_client(username, password)
    client.connect_imap()

    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = Session(username=username, client=client, csrf_token=csrf_token)
    return token


def destroy_session(token: str | None) -> None:
    if not token:
        return
    with _lock:
        session = _sessions.pop(token, None)
    if session:
        session.client.disconnect()


def require_session(request: Request) -> Session:
    session = get_session(request.cookies.get("session_id"))
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session
