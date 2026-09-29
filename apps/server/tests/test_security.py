from fastapi.testclient import TestClient

from export.fonts import _safe_family
from server import main, settings_api


def client():
    return TestClient(main.app)


def test_foreign_origin_is_refused_even_for_simple_posts():
    r = client().post("/api/system/open-data", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_foreign_host_is_refused():
    r = client().get("/api/templates", headers={"Host": "evil.example"})
    assert r.status_code == 403


def test_local_origin_is_served_with_cors():
    r = client().get("/api/templates", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_upload_id_cannot_leave_the_uploads_folder():
    for bad in ("upload:../../x", "upload:..", "upload:a/b", "upload:"):
        assert main._uploaded_template_path(bad) is None


def test_font_family_names_cannot_traverse():
    assert _safe_family("Montserrat SemiBold")
    for bad in ("../../etc", "a/b", ".hidden", "a\\b", "x" * 200):
        assert not _safe_family(bad)


def test_stored_key_is_not_reused_for_another_address(monkeypatch):
    from inference.runtime import UserConfig

    stored = UserConfig(provider="openrouter", api_base="https://good.example/v1", api_key="SECRET")
    monkeypatch.setattr(settings_api, "load_config", lambda: stored)
    same = settings_api.ConfigIn(api_base="https://good.example/v1").merged(probe=True)
    other = settings_api.ConfigIn(api_base="https://attacker.example/v1").merged(probe=True)
    typed = settings_api.ConfigIn(api_base="https://attacker.example/v1", api_key="mine").merged(probe=True)
    assert same.api_key == "SECRET"
    assert other.api_key == ""
    assert typed.api_key == "mine"


def test_address_must_be_http():
    import pytest

    with pytest.raises(ValueError):
        settings_api.ConfigIn(api_base="file:///etc/passwd")
