import hashlib
import io
import json
import zipfile

from server import presets


def _pptx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<x/>")
    return buf.getvalue()


def _serve(monkeypatch, manifest, files):
    def fake_get(url, limit=0):
        return json.dumps(manifest).encode()

    def fake_download(url, target):
        target.write_bytes(files[url.rsplit("/", 1)[-1]])

    monkeypatch.setenv("PREZA_PRESETS_URL", "https://example.test/presets/")
    monkeypatch.setattr(presets, "_get", fake_get)
    monkeypatch.setattr(presets, "_download", fake_download)


def test_sync_downloads_verified_files_once(tmp_path, monkeypatch):
    data = _pptx_bytes()
    sha = hashlib.sha256(data).hexdigest()
    _serve(monkeypatch, {"templates": [{"name": "a.pptx", "sha256": sha}]}, {"a.pptx": data})
    assert presets.sync_presets(tmp_path) == 1
    assert (tmp_path / "a.pptx").read_bytes() == data
    assert presets.sync_presets(tmp_path) == 0


def test_bad_entries_are_skipped_not_fatal(tmp_path, monkeypatch):
    data = _pptx_bytes()
    good = hashlib.sha256(data).hexdigest()
    manifest = {"templates": [
        {"name": "../evil.pptx", "sha256": good},            # path stripped to evil.pptx, served below
        {"name": "nohash.pptx"},                             # no checksum: never trusted
        {"name": "wrong.pptx", "sha256": "0" * 64},          # checksum mismatch
        {"name": "notzip.pptx", "sha256": hashlib.sha256(b"x").hexdigest()},
        {"name": "ok.pptx", "sha256": good},
    ]}
    _serve(monkeypatch, manifest, {"evil.pptx": data, "wrong.pptx": data, "notzip.pptx": b"x", "ok.pptx": data})
    presets.sync_presets(tmp_path)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["evil.pptx", "ok.pptx"]  # inside the folder, never outside it
    assert not (tmp_path.parent / "evil.pptx").exists()


def test_only_https_addresses(tmp_path, monkeypatch):
    monkeypatch.setenv("PREZA_PRESETS_URL", "file:///etc")
    assert presets.base_url() == ""
    monkeypatch.setenv("PREZA_PRESETS_URL", "http://evil.example/presets")
    assert presets.base_url() == ""
    monkeypatch.setenv("PREZA_PRESETS_URL", "https://ok.example/presets/")
    assert presets.base_url() == "https://ok.example/presets"
    monkeypatch.delenv("PREZA_PRESETS_URL")
    monkeypatch.setattr(presets, "DEFAULT_PRESETS_URL", "")  # no address: nothing to fetch
    assert presets.sync_presets(tmp_path) == 0
