from unittest.mock import patch

import pytest

from app import create_app


VALID_PAYLOAD = {
    "name": "Florian Weimann",
    "email": "florian@example.com",
    "message": "Das ist eine Testnachricht.",
    "website": "",
}


@pytest.fixture
def app():
    return create_app(
        {
            "TESTING": True,
            "ALLOWED_ORIGIN": "http://localhost:4200",
            "CONTACT_RATE_LIMIT": "100 per minute",
            "RATELIMIT_STORAGE_URI": "memory://",
            "SMTP_USERNAME": "sender@example.com",
            "SMTP_PASSWORD": "test-password",
            "MAIL_FROM_ADDRESS": "sender@example.com",
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def test_valid_request_sends_trimmed_payload(client):
    payload = {
        **VALID_PAYLOAD,
        "name": "  Florian Weimann  ",
        "email": "  florian@example.com  ",
        "message": "  Das ist eine Testnachricht.  ",
    }

    with patch("app.mail_service.send_contact_email") as send_mail:
        response = client.post("/api/contact", json=payload)

    assert response.status_code == 200
    send_mail.assert_called_once()
    assert send_mail.call_args.kwargs["name"] == "Florian Weimann"
    assert send_mail.call_args.kwargs["email"] == "florian@example.com"
    assert send_mail.call_args.kwargs["message"] == "Das ist eine Testnachricht."


def test_missing_name_is_rejected(client):
    response = client.post("/api/contact", json={**VALID_PAYLOAD, "name": ""})

    assert response.status_code == 422
    assert response.get_json() == {"error": "validation_failed"}


def test_invalid_email_is_rejected(client):
    response = client.post("/api/contact", json={**VALID_PAYLOAD, "email": "invalid"})

    assert response.status_code == 422


def test_message_with_fewer_than_three_words_is_rejected(client):
    response = client.post("/api/contact", json={**VALID_PAYLOAD, "message": "Zu kurz"})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "n" * 101),
        ("email", f"{'a' * 245}@example.com"),
        ("message", "wort " * 1001),
    ],
)
def test_too_long_fields_are_rejected(client, field, value):
    response = client.post("/api/contact", json={**VALID_PAYLOAD, field: value})

    assert response.status_code == 422


def test_filled_honeypot_returns_success_without_sending(client):
    with patch("app.mail_service.send_contact_email") as send_mail:
        response = client.post("/api/contact", json={**VALID_PAYLOAD, "website": "spam"})

    assert response.status_code == 204
    send_mail.assert_not_called()


def test_wrong_content_type_is_rejected(client):
    response = client.post("/api/contact", data="not json", content_type="text/plain")

    assert response.status_code == 415
    assert response.get_json() == {"error": "unsupported_media_type"}


def test_invalid_json_is_rejected(client):
    response = client.post("/api/contact", data="{", content_type="application/json")

    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_json"}


def test_mail_failure_returns_generic_error(client):
    with patch(
        "app.mail_service.send_contact_email",
        side_effect=RuntimeError("private SMTP detail"),
    ):
        response = client.post("/api/contact", json=VALID_PAYLOAD)

    assert response.status_code == 502
    assert response.get_json() == {"error": "delivery_failed"}
    assert "SMTP" not in response.get_data(as_text=True)


def test_successful_delivery_returns_sent_status(client):
    with patch("app.mail_service.send_contact_email"):
        response = client.post("/api/contact", json=VALID_PAYLOAD)

    assert response.status_code == 200
    assert response.get_json() == {"status": "sent"}


def test_cors_allows_only_configured_origin(client):
    with patch("app.mail_service.send_contact_email"):
        allowed = client.post(
            "/api/contact",
            json=VALID_PAYLOAD,
            headers={"Origin": "http://localhost:4200"},
        )
        denied = client.post(
            "/api/contact",
            json=VALID_PAYLOAD,
            headers={"Origin": "https://untrusted.example"},
        )

    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:4200"
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_rate_limit_returns_generic_429_response():
    rate_limited_app = create_app(
        {
            "TESTING": True,
            "ALLOWED_ORIGIN": "http://localhost:4200",
            "CONTACT_RATE_LIMIT": "1 per minute",
            "RATELIMIT_STORAGE_URI": "memory://",
        }
    )
    rate_limited_client = rate_limited_app.test_client()

    with patch("app.mail_service.send_contact_email"):
        first = rate_limited_client.post("/api/contact", json=VALID_PAYLOAD)
        second = rate_limited_client.post("/api/contact", json=VALID_PAYLOAD)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.get_json() == {"error": "rate_limited"}
