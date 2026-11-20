"""Plain-text SMTP for the seven Zoho outreach mailboxes."""

from __future__ import annotations

import smtplib
import uuid
from email.message import EmailMessage
from email.utils import formataddr, formatdate

from outreach.config import Mailbox, Settings


def new_message_id(domain: str) -> str:
    return f"<{uuid.uuid4()}@{domain}>"


def rfc_message_id(value: str) -> str | None:
    text = value.strip()
    if text.startswith("<") and text.endswith(">") and "@" in text[1:-1]:
        return text
    return None


def build_message(
    *,
    mailbox: Mailbox,
    reply_to: str,
    to_email: str,
    subject: str,
    body: str,
    message_id: str,
    parent_message_id: str = "",
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((mailbox.display_name, mailbox.email))
    message["To"] = to_email
    message["Reply-To"] = reply_to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = message_id
    parent = rfc_message_id(parent_message_id)
    if parent:
        message["In-Reply-To"] = parent
        message["References"] = parent
    message.set_content(body)
    return message


class SmtpMailer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.disabled: set[str] = set()

    def send(self, mailbox: Mailbox, message: EmailMessage) -> None:
        if mailbox.email.casefold() in self.disabled:
            raise smtplib.SMTPException(f"{mailbox.email} is disabled for this run")
        host = self.settings.smtp_host
        port = self.settings.smtp_port
        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                    smtp.login(mailbox.email, mailbox.password())
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.ehlo()
                    smtp.login(mailbox.email, mailbox.password())
                    smtp.send_message(message)
        except smtplib.SMTPAuthenticationError:
            self.disabled.add(mailbox.email.casefold())
            raise
