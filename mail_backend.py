import imaplib
import smtplib
import email
import email.utils
import email.header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dataclasses import dataclass, field
from typing import Optional
import os
import re
import html
import base64
import ssl
import threading


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name)
    name = name.replace("..", "")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = name.strip('. ')
    return name or "attachment"


def _decode_imap_utf7(data: bytes) -> str:
    """Decode IMAP modified UTF-7 folder names to Unicode."""
    result = []
    i = 0
    while i < len(data):
        if data[i:i+1] == b"&":
            end = data.index(b"-", i + 1)
            if end == i + 1:
                result.append("&")
            else:
                encoded = data[i+1:end].replace(b",", b"/")
                decoded = base64.b64decode(encoded + b"==")
                result.append(decoded.decode("utf-16-be"))
            i = end + 1
        else:
            result.append(chr(data[i]))
            i += 1
    return "".join(result)


@dataclass
class MailAccount:
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    use_ssl: bool = True


@dataclass
class MailMessage:
    uid: int
    subject: str
    sender: str
    to: str
    date: str
    seen: bool
    body_text: str = ""
    body_html: str = ""
    has_attachments: bool = False
    attachments: list = field(default_factory=list)
    cc: str = ""
    message_id: str = ""
    in_reply_to: str = ""
    size: int = 0


def _decode_header(raw: str) -> str:
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def _decode_payload(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


class MailClient:
    def __init__(self, account: MailAccount):
        self.account = account
        self._imap: Optional[imaplib.IMAP4_SSL | imaplib.IMAP4] = None
        self._lock = threading.RLock()

    def connect_imap(self):
        ctx = ssl.create_default_context()
        if self.account.use_ssl:
            self._imap = imaplib.IMAP4_SSL(
                self.account.imap_host, self.account.imap_port, ssl_context=ctx
            )
        else:
            self._imap = imaplib.IMAP4(self.account.imap_host, self.account.imap_port)
            self._imap.starttls(ssl_context=ctx)
        self._imap.login(self.account.username, self.account.password)

    def reconnect(self):
        try:
            if self._imap:
                self._imap.logout()
        except Exception:
            pass
        self._imap = None
        self.connect_imap()

    def _ensure_alive(self):
        if not self._imap:
            self.connect_imap()
            return
        try:
            self._imap.noop()
        except Exception:
            self.reconnect()

    def disconnect(self):
        if self._imap:
            try:
                self._imap.logout()
            except Exception:
                pass
            self._imap = None

    def noop(self):
        with self._lock:
            self._ensure_alive()

    def _select_folder(self, folder: str = "INBOX") -> int:
        self._ensure_alive()
        status, data = self._imap.select(f'"{folder}"' if " " in folder else folder)
        if status != "OK":
            return 0
        return int(data[0])

    def list_folders(self) -> list[str]:
        with self._lock:
            if not self._imap:
                self.connect_imap()
            status, data = self._imap.list()
            if status != "OK":
                return []
            folders = []
            for item in data:
                if isinstance(item, bytes):
                    match = re.search(rb'"([^"]*)"$|(\S+)$', item)
                    if match:
                        name = match.group(1) or match.group(2)
                        folders.append(_decode_imap_utf7(name) if isinstance(name, bytes) else str(name))
                elif isinstance(item, tuple):
                    line = item[0] if isinstance(item[0], bytes) else b""
                    match = re.search(rb'"([^"]*)"$|(\S+)$', line)
                    if match:
                        name = match.group(1) or match.group(2)
                        folders.append(name.decode("utf-8", errors="replace"))
            return folders

    def fetch_message_list(self, folder: str = "INBOX", limit: int = 50) -> list[MailMessage]:
        with self._lock:
            count = self._select_folder(folder)
            if count == 0:
                return []

            status, data = self._imap.uid("search", None, "ALL")
            if status != "OK":
                return []

            uids = data[0].split()
            uids = list(reversed(uids))[:limit]

            if not uids:
                return []

            uid_str = b",".join(uids)
            status, data = self._imap.uid("fetch", uid_str, "(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO CC DATE MESSAGE-ID)] RFC822.SIZE)")
            if status != "OK":
                return []

            messages = []
            i = 0
            while i < len(data):
                item = data[i]
                if isinstance(item, tuple) and len(item) >= 2:
                    meta_line = item[0].decode("utf-8", errors="replace") if isinstance(item[0], bytes) else str(item[0])
                    header_data = item[1]

                    uid_match = re.search(r"UID (\d+)", meta_line)
                    uid = int(uid_match.group(1)) if uid_match else 0

                    seen = "\\Seen" in meta_line

                    size_match = re.search(r"RFC822\.SIZE (\d+)", meta_line)
                    size = int(size_match.group(1)) if size_match else 0

                    msg = email.message_from_bytes(header_data) if isinstance(header_data, bytes) else email.message_from_string(str(header_data))

                    messages.append(MailMessage(
                        uid=uid,
                        subject=_decode_header(msg.get("Subject", "(No Subject)")),
                        sender=_decode_header(msg.get("From", "")),
                        to=_decode_header(msg.get("To", "")),
                        cc=_decode_header(msg.get("Cc", "")),
                        date=msg.get("Date", ""),
                        seen=seen,
                        message_id=msg.get("Message-ID", ""),
                        size=size,
                    ))
                i += 1

            return messages

    def fetch_message(self, uid: int, folder: str = "INBOX") -> Optional[MailMessage]:
        with self._lock:
            self._select_folder(folder)
            status, data = self._imap.uid("fetch", str(uid), "(FLAGS RFC822)")
            if status != "OK" or not data or data[0] is None:
                return None

            for item in data:
                if isinstance(item, tuple) and len(item) >= 2:
                    meta_line = item[0].decode("utf-8", errors="replace") if isinstance(item[0], bytes) else str(item[0])
                    raw = item[1]
                    break
            else:
                return None

            seen = "\\Seen" in meta_line
            msg = email.message_from_bytes(raw) if isinstance(raw, bytes) else email.message_from_string(str(raw))

        body_text = ""
        body_html = ""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                maintype = part.get_content_maintype()
                disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in disposition or maintype not in ("text", "multipart", "message"):
                    filename = part.get_filename()
                    if filename:
                        filename = _sanitize_filename(_decode_header(filename))
                    if maintype == "multipart":
                        continue
                    attachments.append({
                        "filename": filename or "attachment",
                        "content_type": content_type,
                        "data": part.get_payload(decode=True),
                    })
                elif content_type == "text/plain" and not body_text:
                    body_text = _decode_payload(part)
                elif content_type == "text/html" and not body_html:
                    body_html = _decode_payload(part)
        else:
            content_type = msg.get_content_type()
            if content_type == "text/html":
                body_html = _decode_payload(msg)
            elif content_type == "text/plain":
                body_text = _decode_payload(msg)
            else:
                attachments.append({
                    "filename": _sanitize_filename(_decode_header(msg.get_filename() or "attachment")),
                    "content_type": content_type,
                    "data": msg.get_payload(decode=True),
                })

        return MailMessage(
            uid=uid,
            subject=_decode_header(msg.get("Subject", "(No Subject)")),
            sender=_decode_header(msg.get("From", "")),
            to=_decode_header(msg.get("To", "")),
            cc=_decode_header(msg.get("Cc", "")),
            date=msg.get("Date", ""),
            seen=seen,
            body_text=body_text,
            body_html=body_html,
            has_attachments=len(attachments) > 0,
            attachments=attachments,
            message_id=msg.get("Message-ID", ""),
            in_reply_to=msg.get("In-Reply-To", ""),
        )

    def mark_seen(self, uid: int, folder: str = "INBOX"):
        with self._lock:
            self._select_folder(folder)
            self._imap.uid("store", str(uid), "+FLAGS", "\\Seen")

    def mark_unseen(self, uid: int, folder: str = "INBOX"):
        with self._lock:
            self._select_folder(folder)
            self._imap.uid("store", str(uid), "-FLAGS", "\\Seen")

    def delete_message(self, uid: int, folder: str = "INBOX"):
        with self._lock:
            self._select_folder(folder)
            self._imap.uid("store", str(uid), "+FLAGS", "\\Deleted")
            self._imap.expunge()

    def move_message(self, uid: int, src_folder: str, dst_folder: str):
        with self._lock:
            self._select_folder(src_folder)
            status, data = self._imap.uid("fetch", str(uid), "(RFC822)")
            if status != "OK" or not data or data[0] is None:
                return
            for item in data:
                if isinstance(item, tuple) and len(item) >= 2:
                    raw = item[1]
                    break
            else:
                return
            self._imap.append(dst_folder, None, None, raw)
            self._imap.uid("store", str(uid), "+FLAGS", "\\Deleted")
            self._imap.expunge()

    @staticmethod
    def _clean_header(value: str) -> str:
        return re.sub(r"[\r\n]", "", value)

    def send_message(self, to: str, subject: str, body: str, cc: str = "",
                     attachments: list[str] | None = None,
                     in_reply_to: str = "", references: str = ""):
        to = self._clean_header(to)
        subject = self._clean_header(subject)
        cc = self._clean_header(cc)

        msg = MIMEMultipart() if attachments else MIMEText(body, "plain", "utf-8")

        msg["From"] = self.account.username
        msg["To"] = to
        if cc:
            msg["Cc"] = cc
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid()
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = references or in_reply_to

        if attachments:
            msg.attach(MIMEText(body, "plain", "utf-8"))
            for filepath in attachments:
                if not os.path.isfile(filepath):
                    continue
                with open(filepath, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename=\"{os.path.basename(filepath)}\"")
                msg.attach(part)

        all_recipients = [addr.strip() for addr in to.split(",")]
        if cc:
            all_recipients += [addr.strip() for addr in cc.split(",")]

        ctx = ssl.create_default_context()
        if self.account.smtp_port == 465:
            with smtplib.SMTP_SSL(self.account.smtp_host, self.account.smtp_port, context=ctx) as smtp:
                smtp.login(self.account.username, self.account.password)
                smtp.sendmail(self.account.username, all_recipients, msg.as_string())
        else:
            with smtplib.SMTP(self.account.smtp_host, self.account.smtp_port) as smtp:
                smtp.starttls(context=ctx)
                smtp.login(self.account.username, self.account.password)
                smtp.sendmail(self.account.username, all_recipients, msg.as_string())
