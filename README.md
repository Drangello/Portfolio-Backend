# Portfolio contact API

This standalone Flask service accepts portfolio contact-form messages at `POST /api/contact`, validates them, and sends them as plaintext email through SMTP. It does not persist message content.

## Prerequisites

- Python 3.11 or newer
- A separate frontend that sends JSON requests to this API
- SMTP credentials only for a manual delivery test

## Virtual environment and installation

From the `portfolio-backend` directory on Windows PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

`requirements.txt` contains runtime dependencies. `requirements-dev.txt` additionally installs the test dependency.

## Environment configuration

Copy `.env.example` to `.env` and replace its placeholders locally. The `.env` file and comparable secret files are ignored by Git.

`ALLOWED_ORIGIN` must contain the exact frontend origin. For local development this is normally `http://localhost:4200`. Never use `*` and never expose SMTP credentials to the frontend.

For a manual Gmail SMTP test, enable two-step verification for the sending Google account and place a dedicated Google app password in `SMTP_PASSWORD`. `SMTP_USERNAME` and `MAIL_FROM_ADDRESS` identify the fixed server-side sender. Do not commit these values.

## Development start

```powershell
.venv/Scripts/python -m app
```

Flask listens on `http://localhost:5000`. The contact endpoint is `POST http://localhost:5000/api/contact` and accepts:

```json
{
  "name": "Example Name",
  "email": "person@example.com",
  "message": "This is a message.",
  "website": ""
}
```

`website` is a honeypot and must remain empty for legitimate requests.

## Tests

```powershell
.venv/Scripts/python -m pytest tests
```

The automated tests mock the mail service and SMTP connection; they never send email.

For multiple production workers, replace the in-memory limiter storage with a shared store and configure trusted reverse-proxy client-IP handling before relying on IP-based limits.
