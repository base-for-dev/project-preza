"""The preinstalled template library, shared by every user.

The templates are too big for git (~800 MB), so they live in a public
read-only bucket (Cloudflare R2 / any S3 host with public reads) as
`<base url>/manifest.json` + `<base url>/<file>.pptx`. On start the server
downloads whatever is missing into the local template folder. Reading needs no
credentials and nothing is ever written back: a user's generations and uploads
stay on their machine (or in their own storage from the settings screen).

Maintainers publish with `evals/publish_presets.py`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

# Empty until the bucket has a public address; PREZA_PRESETS_URL overrides it.
DEFAULT_PRESETS_URL = ""
TIMEOUT = 30
MAX_PRESET_BYTES = 200 * 1024 * 1024


def base_url() -> str:
    """The library address; https only (plain http just for a local test server)."""
    url = (os.environ.get("PREZA_PRESETS_URL") or DEFAULT_PRESETS_URL).rstrip("/")
    host = urllib.parse.urlparse(url).hostname or ""
    if url.startswith("https://") or (url.startswith("http://") and host in ("localhost", "127.0.0.1")):
        return url
    if url:
        log.warning("ignoring PREZA_PRESETS_URL: only https:// addresses are accepted")
    return ""


def _get(url: str, limit: int = 1 << 20) -> bytes:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as response:  # noqa: S310 (https, fixed base)
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("response too large")
    return data


def _download(url: str, target: Path) -> None:
    """Stream `url` to `target`, refusing anything over the size cap."""
    total = 0
    with urllib.request.urlopen(url, timeout=TIMEOUT) as response, target.open("wb") as out:  # noqa: S310
        while chunk := response.read(1 << 20):
            total += len(chunk)
            if total > MAX_PRESET_BYTES:
                raise ValueError("file too large")
            out.write(chunk)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sync_presets(directory: Path) -> int:
    """Download the presets missing from (or changed in) `directory`; how many were fetched.

    Only files the manifest vouches for with a sha256 are taken, checked after
    download, and must be real zip (pptx) containers. A bad entry is skipped.
    """
    root = base_url()
    if not root:
        return 0
    manifest = json.loads(_get(f"{root}/manifest.json"))
    directory.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for entry in manifest.get("templates", []):
        try:
            name = Path(str(entry["name"])).name  # never a path out of the folder
            digest = str(entry["sha256"]).lower()
        except (KeyError, TypeError):
            continue
        if not name.lower().endswith(".pptx") or name.startswith(".") or not re.fullmatch(r"[0-9a-f]{64}", digest):
            continue
        target = directory / name
        if target.is_file() and _sha256(target) == digest:
            continue
        tmp = target.with_suffix(".part")
        try:
            _download(f"{root}/{urllib.parse.quote(name)}", tmp)
            if _sha256(tmp) != digest:
                raise ValueError("checksum mismatch")
            if not zipfile.is_zipfile(tmp):
                raise ValueError("not a pptx")
            tmp.replace(target)
            fetched += 1
        except Exception:
            log.warning("could not fetch preset %s", name, exc_info=True)
            tmp.unlink(missing_ok=True)
    return fetched
