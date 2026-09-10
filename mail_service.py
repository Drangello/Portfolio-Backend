import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Mapping


class MailConfigurationError(RuntimeError):
    """Raised when the server-side mail configuration is incomplete."""


def _validated_address(value: str, setting_name: str) -> str:
    display_name, address = parseaddr(value)
    if display_name or address != value or "\r" in value or "\n" in value or "@" not in address:
        raise MailConfigurationError(f"Invalid {setting_name} configuration")
    return address


def send_contact_email(
    *,
    name: str,
    email: str,
    message: str,
    config: Mapping[str, object],
) -> None:
    smtp_host = str(config.get("SMTP_HOST", "")).strip()
    smtp_port = int(config.get("SMTP_PORT", 587))
    smtp_username = str(config.get("SMTP_USERNAME", "")).strip()
    smtp_password = str(config.get("SMTP_PASSWORD", ""))
    mail_from = _validated_address(
        str(config.get("MAIL_FROM_ADDRESS", "")).strip(),
        "MAIL_FROM_ADDRESS",
    )
    recipient = _validated_address(
        str(config.get("CONTACT_RECIPIENT_EMAIL", "")).strip(),
        "CONTACT_RECIPIENT_EMAIL",
    )

    if not smtp_host or not smtp_username or not smtp_password:
        raise MailConfigurationError("Incomplete SMTP configuration")

    email_message = EmailMessage()
    email_message["Subject"] = "Neue Portfolio-Nachricht"
    email_message["From"] = mail_from
    email_message["To"] = recipient
    email_message["Reply-To"] = email
    email_message.set_content(
        f"Name: {name}\n"
        f"E-Mail: {email}\n\n"
        f"Nachricht:\n{message}\n"
    )

    timeout = int(config.get("SMTP_TIMEOUT_SECONDS", 10))
    with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(smtp_username, smtp_password)
        smtp.send_message(email_message)
