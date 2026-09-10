import re
from typing import Any

from flask import Flask, current_app, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import RequestEntityTooLarge

import mail_service
from config import Config


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ALLOWED_FIELDS = {"name", "email", "message", "website"}


def _error(error_code: str, status_code: int):
    return jsonify({"error": error_code}), status_code


def _validate_payload(payload: dict[str, Any]) -> tuple[dict[str, str] | None, str | None]:
    if not set(payload).issubset(ALLOWED_FIELDS):
        return None, "invalid_request"

    website = payload.get("website", "")
    if not isinstance(website, str):
        return None, "invalid_request"
    if website.strip():
        return {"honeypot": "filled"}, None

    if not all(isinstance(payload.get(field), str) for field in ("name", "email", "message")):
        return None, "validation_failed"

    name = payload["name"].strip()
    email = payload["email"].strip()
    message = payload["message"].strip()

    if not 2 <= len(name) <= 100:
        return None, "validation_failed"
    if (
        not email
        or len(email) > 254
        or "\r" in email
        or "\n" in email
        or EMAIL_PATTERN.fullmatch(email) is None
    ):
        return None, "validation_failed"
    if len(message) > 5000 or len(message.split()) < 3:
        return None, "validation_failed"

    return {"name": name, "email": email, "message": message}, None


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    allowed_origin = str(app.config["ALLOWED_ORIGIN"]).strip()
    if not allowed_origin or allowed_origin == "*":
        raise ValueError("ALLOWED_ORIGIN must contain one explicit frontend origin")

    CORS(
        app,
        resources={
            r"/api/contact": {
                "origins": [allowed_origin],
                "methods": ["POST", "OPTIONS"],
                "allow_headers": ["Content-Type"],
                "supports_credentials": False,
            }
        },
    )

    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[],
        storage_uri=str(app.config["RATELIMIT_STORAGE_URI"]),
    )

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(_error: RequestEntityTooLarge):
        return _error_response("request_too_large", 413)

    @app.errorhandler(429)
    def handle_rate_limit(_error: Exception):
        return _error_response("rate_limited", 429)

    def _error_response(error_code: str, status_code: int):
        return jsonify({"error": error_code}), status_code

    @app.post("/api/contact")
    @limiter.limit(str(app.config["CONTACT_RATE_LIMIT"]))
    def contact():
        if not request.is_json:
            return _error("unsupported_media_type", 415)

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _error("invalid_json", 400)

        validated, validation_error = _validate_payload(payload)
        if validation_error:
            status_code = 400 if validation_error == "invalid_request" else 422
            return _error(validation_error, status_code)
        if validated == {"honeypot": "filled"}:
            return "", 204

        assert validated is not None
        try:
            mail_service.send_contact_email(
                name=validated["name"],
                email=validated["email"],
                message=validated["message"],
                config=current_app.config,
            )
        except Exception:
            current_app.logger.error("Contact email delivery failed")
            return _error("delivery_failed", 502)

        return jsonify({"status": "sent"}), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
