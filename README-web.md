# 98Mail Webmail

Web version of 98Mail: a Win98-style webmail client with a FastAPI backend.

The desktop files (`main.py`, `win98style.py`) are kept for reference. The web app lives in `webapp/`.

## Setup

```bash
pip install -r requirements-web.txt
cp .env.example .env
# edit .env with the fixed IMAP/SMTP server details
uvicorn --env-file .env webapp.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

## Configuration

The IMAP/SMTP server is preconfigured through environment variables:

```text
IMAP_HOST
IMAP_PORT
IMAP_USE_SSL
SMTP_HOST
SMTP_PORT
SESSION_SECURE
SESSION_MAX_AGE
```

The login form asks only for username/password. It does not accept a host or port.

## Security notes

- Serve behind HTTPS in production.
- Keep `SESSION_SECURE=true` behind TLS.
- Add a reverse proxy, rate limiting, and CSRF protection before public exposure.
- The backend sanitizes and downgrades email HTML before rendering.
- Remote images are blocked by default; the preview offers a "Load Remote Images" action.
- Credentials stay server-side; the session cookie contains only a session token.

## Endpoints

```text
GET  /api/folders
GET  /api/messages?folder=INBOX
GET  /api/messages/{uid}?folder=INBOX
POST /api/messages/{uid}/seen
POST /api/messages/{uid}/unseen
DELETE /api/messages/{uid}?folder=INBOX
GET  /api/messages/{uid}/attachments/{index}?folder=INBOX
POST /api/send
GET  /api/health
```
