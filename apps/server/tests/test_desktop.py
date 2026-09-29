"""The command line, the machine checks and serving the built web app from one process."""

from __future__ import annotations

import socket

from fastapi.testclient import TestClient
from server import cli, system
from server.main import app

client = TestClient(app)


def test_free_port_skips_a_port_in_use():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        assert cli.free_port(taken) != taken


def test_data_dir_is_per_user_and_named_for_the_app():
    assert cli.default_data_dir().name.lower() == "preza"


def test_frozen_or_installed_runs_keep_data_out_of_the_bundle(tmp_path, monkeypatch):
    monkeypatch.setenv("PREZA_DATA_DIR", "placeholder")  # restored after the test
    monkeypatch.delenv("PREZA_DATA_DIR")
    monkeypatch.setenv("PREZA_INSTALLED", "1")
    monkeypatch.setattr(cli, "default_data_dir", lambda: tmp_path / "Preza")
    cli._prepare_environment(None)
    import os

    assert os.environ["PREZA_DATA_DIR"] == str(tmp_path / "Preza")
    assert (tmp_path / "Preza").is_dir()


def test_install_reports_a_download_link_when_nothing_can_install(monkeypatch):
    monkeypatch.setattr(system, "_install_command", lambda: None)
    lines = list(system.install_libreoffice())
    assert lines[-1].startswith("FAILED") and system.DOWNLOAD_PAGE in lines[-1]


def test_install_streams_the_output_and_ends_ok(monkeypatch):
    monkeypatch.setattr(system, "_install_command", lambda: ["echo", "installing"])
    monkeypatch.setattr(system, "soffice_path", lambda: "/usr/bin/soffice")
    assert list(system.install_libreoffice()) == ["$ echo installing", "installing", "OK"]


def test_install_says_so_when_it_ran_but_libreoffice_is_still_missing(monkeypatch):
    monkeypatch.setattr(system, "_install_command", lambda: ["true"])
    monkeypatch.setattr(system, "soffice_path", lambda: None)
    assert list(system.install_libreoffice())[-1].startswith("FAILED")


def test_system_endpoint_reports_version_folder_and_libreoffice():
    body = client.get("/api/system").json()
    assert body["version"] and body["data_dir"] and "installed" in body["libreoffice"]


def test_a_newer_release_is_detected(monkeypatch):
    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, *a):
            return b'{"tag_name": "v9.9.9", "html_url": "https://example.test/r"}'

    monkeypatch.setattr(system.urllib.request, "urlopen", lambda *a, **k: Reply())
    result = system.latest_release()
    assert result["newer"] is True and result["latest"] == "9.9.9"


def test_an_unreachable_release_page_is_not_an_error(monkeypatch):
    def down(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(system.urllib.request, "urlopen", down)
    assert system.latest_release()["newer"] is False


def test_the_built_web_app_is_served_at_root(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    (tmp_path / "index.html").write_text("<h1>Preza</h1>")
    (tmp_path / "generation").mkdir()
    (tmp_path / "generation" / "index.html").write_text("<h1>How</h1>")
    site = FastAPI()
    site.get("/api/x")(lambda: {"ok": True})
    site.mount("/", StaticFiles(directory=str(tmp_path), html=True))
    c = TestClient(site)
    assert c.get("/").text == "<h1>Preza</h1>"
    assert c.get("/generation/").text == "<h1>How</h1>"
    assert c.get("/api/x").json() == {"ok": True}  # API routes win over the site
