"""On-disk storage for brand packs and task sources (`data/`, gitignored).

data/brand_packs/<id>/files/*       the pack's uploaded files, as uploaded
data/brand_packs/<id>/status.json   {"name", "status": building|ready|error, "error"}
data/brand_packs/<id>/context.json  the built `BrandContext`
data/sources/<id>.json              a `SourceBundle` (already text)
data/sources/<id>.facts-<sha>.json  the talk's `FactSheet`, per request text
data/catalogs/<sha256>.json         a template's `SlideCatalog`, keyed by file content

Plain files rather than a database: packs are few and built once, and a
developer can inspect or hand-edit `context.json` directly.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path

from brand import BrandContext
from design_system import SlideCatalog
from ingest import FactSheet, SourceBundle

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "data"
PACKS_DIR = DATA_DIR / "brand_packs"
SOURCES_DIR = DATA_DIR / "sources"
CATALOGS_DIR = DATA_DIR / "catalogs"
# A template uploaded via POST /api/templates: kept here, not in
# evals/templates/, so it never shows up in GET /api/templates' shared
# library for anyone else — only the id the upload response handed back
# (and that the uploader's own browser then holds) can ever load it.
UPLOADED_TEMPLATES_DIR = DATA_DIR / "uploaded_templates"

_ID_RE = re.compile(r"^[a-z0-9-]+$")


def new_id(name: str) -> str:
    """Readable, unique id: an ASCII-ish slug of `name` plus a short random suffix."""
    # ASCII-only so ids are safe in URLs and paths as-is; a Cyrillic name
    # just falls back to the generic prefix.
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32]
    return f"{slug or 'pack'}-{uuid.uuid4().hex[:6]}"


def safe_filename(filename: str) -> str:
    """Keep the uploaded name, drop any path and reserved characters."""
    name = Path(filename or "file").name
    name = re.sub(r'[\/\\\0:*?"<>|]', "-", name).strip() or "file"
    return name


def _check_id(item_id: str) -> str:
    # Ids reach the filesystem — never let one be a path.
    if not _ID_RE.match(item_id):
        raise KeyError(item_id)
    return item_id


def pack_dir(pack_id: str) -> Path:
    return PACKS_DIR / _check_id(pack_id)


def pack_files_dir(pack_id: str) -> Path:
    return pack_dir(pack_id) / "files"


def write_pack_status(pack_id: str, name: str, status: str, error: str | None = None) -> None:
    path = pack_dir(pack_id) / "status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"name": name, "status": status, "error": error}, ensure_ascii=False),
        encoding="utf-8",
    )


def read_pack_status(pack_id: str) -> dict | None:
    path = pack_dir(pack_id) / "status.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_brand(context: BrandContext) -> None:
    (pack_dir(context.id) / "context.json").write_text(
        context.model_dump_json(indent=2), encoding="utf-8"
    )


def load_brand(pack_id: str) -> BrandContext | None:
    try:
        path = pack_dir(pack_id) / "context.json"
    except KeyError:
        return None
    if not path.is_file():
        return None
    return BrandContext.model_validate_json(path.read_text(encoding="utf-8"))


def list_pack_ids() -> list[str]:
    if not PACKS_DIR.is_dir():
        return []
    return sorted(
        p.name
        for p in PACKS_DIR.iterdir()
        if _ID_RE.match(p.name) and (p / "status.json").is_file()
    )


def pack_templates() -> list[tuple[str, Path]]:
    """(pack id, template path) for every .pptx in every pack."""
    return [
        (pack_id, path)
        for pack_id in list_pack_ids()
        for path in sorted(pack_files_dir(pack_id).glob("*.pptx"))
    ]


def save_sources(bundle: SourceBundle) -> None:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    (SOURCES_DIR / f"{_check_id(bundle.id)}.json").write_text(
        bundle.model_dump_json(), encoding="utf-8"
    )


def load_sources(source_id: str) -> SourceBundle | None:
    try:
        path = SOURCES_DIR / f"{_check_id(source_id)}.json"
    except KeyError:
        return None
    if not path.is_file():
        return None
    return SourceBundle.model_validate_json(path.read_text(encoding="utf-8"))


def _catalog_path(template: Path) -> Path:
    # Keyed by content, not name: the same template uploaded twice (or
    # renamed) reuses its catalog; an edited file gets a fresh one.
    digest = hashlib.sha256(template.read_bytes()).hexdigest()[:24]
    return CATALOGS_DIR / f"{digest}.json"


def save_catalog(template: Path, catalog: SlideCatalog) -> None:
    CATALOGS_DIR.mkdir(parents=True, exist_ok=True)
    _catalog_path(template).write_text(catalog.model_dump_json(indent=2), encoding="utf-8")


def load_catalog(template: Path) -> SlideCatalog | None:
    path = _catalog_path(template)
    if not path.is_file():
        return None
    return SlideCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def _fact_sheet_path(source_id: str, request: str) -> Path:
    digest = hashlib.sha256(request.strip().encode()).hexdigest()[:16]
    return SOURCES_DIR / f"{_check_id(source_id)}.facts-{digest}.json"


def save_fact_sheet(source_id: str, request: str, sheet: FactSheet) -> None:
    _fact_sheet_path(source_id, request).write_text(sheet.model_dump_json(), encoding="utf-8")


def load_fact_sheet(source_id: str, request: str) -> FactSheet | None:
    try:
        path = _fact_sheet_path(source_id, request)
    except KeyError:
        return None
    if not path.is_file():
        return None
    return FactSheet.model_validate_json(path.read_text(encoding="utf-8"))
