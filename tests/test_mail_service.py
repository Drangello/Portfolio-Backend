from unittest.mock import patch

import pytest

from mail_service import MailConfigurationError, send_contact_email


MAIL_CONFIG = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": 587,
    "SMTP_USERNAME": "sender@example.com",
    "SMTP_PASSWORD": "app-password",
    "MAIL_FROM_ADDRESS": "sender@example.com",
    "CONTACT_RECIPIENT_EMAIL": "florianweimann9@gmail.com",
    "SMTP_TIMEOUT_SECONDS": 10,
}


def test_smtp_uses_fixed_headers_reply_to_and_plaintext():
    with patch("mail_service.smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value

        send_contact_email(
            name="Florian Weimann",
            email="visitor@example.com",
            message="Eine Nachricht mit <strong>Text</strong>.",
            config=MAIL_CONFIG,
        )

    smtp_class.assert_called_once_with("smtp.gmail.com", 587, timeout=10)
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("sender@example.com", "app-password")
    sent_message = smtp.send_message.call_args.args[0]
    assert sent_message["From"] == "sender@example.com"
    assert sent_message["To"] == "florianweimann9@gmail.com"
    assert sent_message["Reply-To"] == "visitor@example.com"
    assert sent_message.get_content_type() == "text/plain"
    assert "<strong>Text</strong>" in sent_message.get_content()


def test_missing_server_credentials_fail_before_smtp_connection():
    with patch("mail_service.smtplib.SMTP") as smtp_class:
        with pytest.raises(MailConfigurationError):
            send_contact_email(
                name="Florian Weimann",
                email="visitor@example.com",
                message="Das ist eine Nachricht.",
                config={**MAIL_CONFIG, "SMTP_PASSWORD": ""},
            )

    smtp_class.assert_not_called()
