from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from flask import request

from app import create_app
from production import allow_request


@pytest.fixture
def prod(tmp_path):
    return create_app({"TESTING": True, "PRODUCTION": True,
                       "ALLOWED_ORIGIN": "https://weimanndev.com",
                       "RATE_LIMIT_DB": str(tmp_path / "limits.sqlite3")})


def post(client, ip="198.51.100.7"):
    # Invalid payload exercises limits without opening SMTP.
    return client.post("/api/contact", json={},
                       environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
                       headers={"X-Forwarded-For": ip, "Origin": "https://weimanndev.com"})


def test_persistent_limit_survives_new_app(prod):
    for _ in range(5):
        assert post(prod.test_client()).status_code == 422
    second = create_app(dict(prod.config))
    response = post(second.test_client())
    assert response.status_code == 429
    assert response.json == {"error": "rate_limited"}
    assert response.headers["Access-Control-Allow-Origin"] == "https://weimanndev.com"
    assert post(second.test_client(), "198.51.100.8").status_code == 422


def test_proxy_rejects_non_loopback(prod):
    assert prod.test_client().post("/api/contact", json={},
        environ_overrides={"REMOTE_ADDR": "198.51.100.8"},
        headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 403


def test_proxy_uses_only_one_hop_and_not_forwarded_host(prod):
    @prod.get("/test-peer")
    def peer():
        return {"ip": request.remote_addr, "scheme": request.scheme, "host": request.host}
    response = prod.test_client().get("/test-peer", environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        headers={"X-Forwarded-For": "spoofed, 198.51.100.9", "X-Forwarded-Proto": "https",
                 "X-Forwarded-Host": "attacker.example", "Host": "api.weimanndev.com"})
    assert response.json == {"ip": "198.51.100.9", "scheme": "https", "host": "api.weimanndev.com"}


def test_production_preflight_does_not_consume_limit(prod):
    client = prod.test_client()
    for _ in range(8):
        response = client.options("/api/contact", headers={"Origin": "https://weimanndev.com",
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type"})
        assert response.headers["Access-Control-Allow-Origin"] == "https://weimanndev.com"
    assert post(client).status_code == 422
    response = client.options("/api/contact", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in response.headers


def test_storage_failure_fails_closed(prod):
    with patch("app.allow_request", side_effect=OSError), patch("app.mail_service.send_contact_email") as smtp:
        assert post(prod.test_client()).status_code == 503
        smtp.assert_not_called()


def test_atomic_counts_and_global_limit(tmp_path):
    path = str(tmp_path / "rate.sqlite3")
    with patch("production.time.time", return_value=7201):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: allow_request(path, "same", 5, 30), range(20)))
        assert sum(results) == 5
        assert sum(allow_request(path, str(i), 5, 30) for i in range(40)) == 25
    with patch("production.time.time", return_value=10801):
        assert allow_request(path, "same", 5, 30)


def test_production_requires_canonical_origin():
    with pytest.raises(ValueError):
        create_app({"PRODUCTION": True, "ALLOWED_ORIGIN": "http://localhost:4200"})


def test_production_success_mocks_smtp(prod):
    with patch("app.mail_service.send_contact_email") as smtp:
        r = prod.test_client().post("/api/contact", json={"name": "Test", "email": "test@example.com",
            "message": "This is a test", "website": ""})
        assert r.status_code == 200
        smtp.assert_called_once()
