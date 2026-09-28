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
    ("post", "/api/preview"),
    ("post", "/api/audit/deep"),
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


def _minimal_deck() -> dict:
    return {
        "slide_width": 9_144_000,
        "slide_height": 6_858_000,
        "slides": [{"index": 0, "layout_name": "L", "shapes": []}],
    }


def test_deep_audit_is_501_without_a_renderer(monkeypatch):
    from export.render import RenderUnavailable

    def unavailable(_deck):
        raise RenderUnavailable("LibreOffice is not installed")

    monkeypatch.setattr("server.main._rendered_pages", unavailable)
    res = client.post("/api/audit/deep", json={"deck": _minimal_deck(), "brief": "тест"})
    assert res.status_code == 501


def test_deep_audit_returns_model_findings_when_rendered(monkeypatch):
    from audit import Finding

    monkeypatch.setattr("server.main._rendered_pages", lambda _deck: [b"fake-png-bytes"])
    monkeypatch.setattr(
        "server.main.run_model_checks",
        lambda deck, brief, images: [
            Finding(check="typo", kind="model", slide_index=0, message="found one")
        ],
    )
    res = client.post("/api/audit/deep", json={"deck": _minimal_deck(), "brief": "тест"})
    assert res.status_code == 200
    findings = res.json()["findings"]
    assert findings == [
        {
            "check": "typo",
            "kind": "model",
            "slide_index": 0,
            "shape_id": None,
            "message": "found one",
        }
    ]
