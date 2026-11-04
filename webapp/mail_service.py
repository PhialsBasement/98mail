from mail_backend import MailAccount, MailClient, MailMessage, _sanitize_filename
from webapp.config import config


def build_account(username: str, password: str) -> MailAccount:
    return MailAccount(
        imap_host=config.imap_host,
        imap_port=config.imap_port,
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        username=username,
        password=password,
        use_ssl=config.imap_use_ssl,
    )


def make_client(username: str, password: str) -> MailClient:
    return MailClient(build_account(username, password))
