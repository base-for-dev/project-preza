"""S3 storage against a fake S3 (moto): connect, keep history and templates, restore them."""

from __future__ import annotations

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from server import object_store, storage
from server.main import app

client = TestClient(app)
FORM = {
    "bucket": "preza-test",
    "access_key": "AKIATEST",
    "secret_key": "secret-value-1234",
    "region": "us-east-1",
    "prefix": "preza/",
}


@pytest.fixture()
def bucket(tmp_path, monkeypatch):
    monkeypatch.setenv("PREZA_STORAGE_CONFIG", str(tmp_path / "storage.json"))
    monkeypatch.setattr(storage, "UPLOADED_TEMPLATES_DIR", tmp_path / "uploaded")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="preza-test")
        yield


def test_not_connected_by_default_and_history_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PREZA_STORAGE_CONFIG", str(tmp_path / "none.json"))
    assert client.get("/api/settings/storage").json()["connected"] is False
    assert client.get("/api/history").json() == {"connected": False, "items": []}


def test_connection_is_tested_saved_and_the_secret_never_returned(bucket):
    assert client.post("/api/settings/storage/test", json=FORM).json() == {"ok": True, "error": ""}
    saved = client.put("/api/settings/storage", json=FORM).json()
    assert saved["connected"] and saved["has_secret"] and "secret_key" not in saved
    assert "secret-value" not in client.get("/api/settings/storage").text
    # Saving without a secret keeps the stored one.
    kept = client.put("/api/settings/storage", json={**FORM, "secret_key": None}).json()
    assert kept["has_secret"]


def test_a_wrong_bucket_reports_the_failure(bucket):
    res = client.post(
        "/api/settings/storage/test", json={**FORM, "bucket": "no-such-bucket"}
    ).json()
    assert res["ok"] is False and res["error"]


def test_a_finished_generation_is_kept_and_can_be_reopened(bucket):
    client.put("/api/settings/storage", json=FORM)
    object_store.save_generation({"brief": "питч"}, {"standard": {"deck": {}, "findings": []}})
    listed = client.get("/api/history").json()
    assert listed["connected"] and len(listed["items"]) == 1
    record = client.get(f"/api/history/{listed['items'][0]['id']}").json()
    assert record["request"]["brief"] == "питч"
    assert client.get("/api/history/nope").status_code == 404
    assert client.get("/api/history/..%2Fsecret").status_code in (404, 422)


def test_uploaded_templates_are_saved_and_restored_on_a_fresh_machine(bucket, tmp_path):
    client.put("/api/settings/storage", json=FORM)
    storage.UPLOADED_TEMPLATES_DIR.mkdir(parents=True)
    (storage.UPLOADED_TEMPLATES_DIR / "mine.pptx").write_bytes(b"PK-template")
    assert client.post("/api/storage/sync").json() == {"uploaded": 1, "downloaded": 0}
    # A new machine: the local folder is empty, the bucket still has it.
    (storage.UPLOADED_TEMPLATES_DIR / "mine.pptx").unlink()
    assert client.post("/api/storage/sync").json() == {"uploaded": 0, "downloaded": 1}
    assert (storage.UPLOADED_TEMPLATES_DIR / "mine.pptx").read_bytes() == b"PK-template"


def test_saving_does_nothing_and_never_fails_without_a_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("PREZA_STORAGE_CONFIG", str(tmp_path / "none.json"))
    object_store.save_generation({}, {})  # no store: silently skipped
    assert object_store.sync_templates() == {"uploaded": 0, "downloaded": 0}
