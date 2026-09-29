"""Optional S3 storage for what would otherwise live only in one browser tab.

Connected in the settings screen (any S3-compatible service: AWS, Yandex Object
Storage, MinIO, Cloudflare R2, ...). Two things go there:

- every finished generation (the request and all three decks with their audit),
  as `history/<time>-<id>.json`, so the history survives a closed tab;
- the templates a user uploaded, as `templates/<name>.pptx`, pulled back to this
  machine on start and on demand.

Nothing else changes when it is not connected: `get_store()` is then None and
every caller simply skips saving. The secret key is written to
`data/storage.json` (owner-only) and never sent back to the browser.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from server import storage

log = logging.getLogger(__name__)


class StorageConfig(BaseModel):
    endpoint_url: str = ""  # empty: AWS
    region: str = ""
    bucket: str = ""
    access_key: str = ""
    secret_key: str = ""
    prefix: str = "preza/"
    path_style: bool = False  # MinIO and some others need it

    def connected(self) -> bool:
        return bool(self.bucket and self.access_key and self.secret_key)


def config_path() -> Path:
    return Path(os.environ.get("PREZA_STORAGE_CONFIG") or storage.DATA_DIR / "storage.json")


def load_config() -> StorageConfig:
    path = config_path()
    if not path.is_file():
        return StorageConfig()
    try:
        return StorageConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return StorageConfig()


def save_config(config: StorageConfig) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Owner-only from the first byte: write a private temp file, then swap it in.
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(config.model_dump_json(indent=2))
    tmp.replace(path)


@dataclass
class ObjectStore:
    config: StorageConfig

    def _client(self):
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            endpoint_url=self.config.endpoint_url or None,
            region_name=self.config.region or None,
            aws_access_key_id=self.config.access_key,
            aws_secret_access_key=self.config.secret_key,
            config=Config(
                s3={"addressing_style": "path" if self.config.path_style else "auto"},
                connect_timeout=8,
                read_timeout=30,
                retries={"max_attempts": 2},
            ),
        )

    def _key(self, name: str) -> str:
        return f"{self.config.prefix.strip('/')}/{name}".lstrip("/")

    def put(self, name: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._client().put_object(
            Bucket=self.config.bucket, Key=self._key(name), Body=data, ContentType=content_type
        )

    def get(self, name: str) -> bytes:
        return (
            self._client().get_object(Bucket=self.config.bucket, Key=self._key(name))["Body"].read()
        )

    def names(self, folder: str) -> list[tuple[str, float]]:
        """(name relative to the prefix, modified timestamp) of every object under `folder/`."""
        client = self._client()
        root = self._key(folder + "/")
        base = self._key("")
        found: list[tuple[str, float]] = []
        for page in client.get_paginator("list_objects_v2").paginate(
            Bucket=self.config.bucket, Prefix=root
        ):
            for item in page.get("Contents", []):
                found.append((item["Key"][len(base) :], item["LastModified"].timestamp()))
        return found

    def check(self) -> None:
        """Raises unless the bucket is reachable and writable with these keys."""
        client = self._client()
        client.head_bucket(Bucket=self.config.bucket)
        probe = self._key(".preza-check")
        client.put_object(Bucket=self.config.bucket, Key=probe, Body=b"ok")
        client.delete_object(Bucket=self.config.bucket, Key=probe)


def get_store() -> ObjectStore | None:
    config = load_config()
    return ObjectStore(config) if config.connected() else None


# --- history ------------------------------------------------------------------


def save_generation(request: dict, result: dict) -> None:
    """Keep a finished generation. Never raises: a broken bucket must not break a deck."""
    store = get_store()
    if store is None:
        return
    import time
    import uuid

    stamp = time.strftime("%Y%m%d-%H%M%S")
    record_id = f"{stamp}-{uuid.uuid4().hex[:6]}"
    record = {"id": record_id, "created": time.time(), "request": request, "result": result}
    try:
        store.put(
            f"history/{record_id}.json",
            json.dumps(record, ensure_ascii=False).encode("utf-8"),
            "application/json",
        )
        # A few bytes the list can read without fetching whole decks.
        meta = {
            "id": record_id,
            "created": record["created"],
            "brief": str(request.get("brief", ""))[:120],
        }
        store.put(
            f"history/{record_id}.meta.json",
            json.dumps(meta, ensure_ascii=False).encode("utf-8"),
            "application/json",
        )
    except Exception:
        log.warning("could not save generation %s to S3", record_id, exc_info=True)


def list_history(limit: int = 30) -> list[dict]:
    """The newest saved generations: id, time and the start of the brief."""
    store = get_store()
    if store is None:
        return []
    newest = sorted(
        (n for n in store.names("history") if n[0].endswith(".meta.json")),
        key=lambda x: x[1],
        reverse=True,
    )[:limit]
    out = []
    for name, _ in newest:
        try:
            out.append(json.loads(store.get(name)))
        except Exception:
            continue
    return out


def load_generation(record_id: str) -> dict | None:
    store = get_store()
    if store is None or "/" in record_id or ".." in record_id:
        return None
    try:
        return json.loads(store.get(f"history/{record_id}.json"))
    except Exception:
        return None


# --- templates ----------------------------------------------------------------


def push_template(path: Path) -> None:
    store = get_store()
    if store is None:
        return
    try:
        store.put(f"templates/{path.name}", path.read_bytes(), "application/octet-stream")
    except Exception:
        log.warning("could not save template %s to S3", path.name, exc_info=True)


def sync_templates() -> dict[str, int]:
    """Both ways: upload local uploaded templates the bucket lacks, download the reverse."""
    store = get_store()
    if store is None:
        return {"uploaded": 0, "downloaded": 0}
    storage.UPLOADED_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    remote = {Path(n).name for n, _ in store.names("templates") if n.endswith(".pptx")}
    local = {p.name for p in storage.UPLOADED_TEMPLATES_DIR.glob("*.pptx")}
    for name in sorted(local - remote):
        store.put(
            f"templates/{name}",
            (storage.UPLOADED_TEMPLATES_DIR / name).read_bytes(),
            "application/octet-stream",
        )
    for name in sorted(remote - local):
        (storage.UPLOADED_TEMPLATES_DIR / name).write_bytes(store.get(f"templates/{name}"))
    return {"uploaded": len(local - remote), "downloaded": len(remote - local)}
