"""The API surface stays intact across module splits.

uv run pytest apps/server
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)

EXPECTED = {
    ("get", "/health"),
    ("get", "/api/templates"),
    ("post", "/api/templates"),
    ("get", "/api/templates/{template_id}/inspect"),
    ("post", "/api/outline"),
    ("post", "/api/content"),
    ("post", "/api/audit"),
    ("post", "/api/audit/stream"),
    ("post", "/api/layout"),
    ("post", "/api/export"),
}


def test_every_public_route_is_registered():
    schema = client.get("/openapi.json").json()["paths"]
    have = {(method, path) for path, ops in schema.items() for method in ops}
    assert EXPECTED <= have


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_templates_are_listed_and_inspectable():
    templates = client.get("/api/templates").json()["templates"]
    assert templates
    first = templates[0]["id"]
    body = client.get(f"/api/templates/{first}/inspect").json()
    assert body["slides"] and body["deck"]["slides"]


def test_unknown_template_is_404():
    assert client.get("/api/templates/no-such-template/inspect").status_code == 404
