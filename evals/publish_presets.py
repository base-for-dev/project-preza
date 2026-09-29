"""Publish evals/templates/*.pptx as the shared preset library (maintainers only).

Credentials come from the environment and are never stored:

    PRESETS_S3_ENDPOINT  PRESETS_S3_BUCKET  PRESETS_S3_KEY_ID  PRESETS_S3_SECRET
    [PRESETS_S3_PREFIX=presets/]

Uploads every template plus manifest.json (name, size, sha256). Users' servers
read those over plain HTTPS (see server/presets.py); the bucket must allow
public reads, and nothing users generate is ever written there.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import boto3

TEMPLATES = Path(__file__).parent / "templates"


def _same(s3, bucket: str, key: str, size: int) -> bool:
    """Already published with this size (templates are replaced, not edited in place)."""
    try:
        return s3.head_object(Bucket=bucket, Key=key)["ContentLength"] == size
    except Exception:
        return False


def main() -> None:
    prefix = os.environ.get("PRESETS_S3_PREFIX", "presets/")
    bucket = os.environ["PRESETS_S3_BUCKET"]
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["PRESETS_S3_ENDPOINT"],
        aws_access_key_id=os.environ["PRESETS_S3_KEY_ID"],
        aws_secret_access_key=os.environ["PRESETS_S3_SECRET"],
        region_name="auto",
    )
    entries = []
    for path in sorted(TEMPLATES.glob("*.pptx")):
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if not _same(s3, bucket, prefix + path.name, path.stat().st_size):
            print(f"upload {path.name}")
            s3.upload_file(str(path), bucket, prefix + path.name)
        entries.append({"name": path.name, "size": path.stat().st_size, "sha256": sha})
    body = json.dumps({"templates": entries}, ensure_ascii=False).encode()
    s3.put_object(Bucket=bucket, Key=prefix + "manifest.json", Body=body, ContentType="application/json")
    print(f"{len(entries)} templates published")


if __name__ == "__main__":
    main()
