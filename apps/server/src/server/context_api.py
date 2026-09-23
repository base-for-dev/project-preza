"""Endpoints for the two kinds of context generation draws on.

- Brand packs (`/api/brand-packs`): the preparation stage. Upload a company's
  content pack once; the `BrandContext` is built in the background (it may
  take minutes — that's allowed, it's not on the 5-minute path) and reused
  by every later generation.
- Task sources (`/api/sources`): the material for one talk — repo ZIPs,
  documents, the team's story. Converted to text on
  upload (no LLM), so the generation request only has to digest it.
"""

from __future__ import annotations

import io
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path, PurePosixPath

from brand import build_brand_context
from brand.pack import FONT_SUFFIXES, IMAGE_SUFFIXES
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from ingest import (
    DOC_SUFFIXES,
    NamedText,
    RepoError,
    SourceBundle,
    digest_zip,
    extract_text,
    member_name,
)

from server import storage

router = APIRouter()


def _build_pack(pack_id: str, name: str) -> None:
    try:
        files = sorted(storage.pack_files_dir(pack_id).iterdir())
        context = build_brand_context(pack_id, name, files)
        storage.save_brand(context)
        storage.write_pack_status(pack_id, name, "ready")
    except Exception as exc:  # surfaced to the UI via status.json
        storage.write_pack_status(pack_id, name, "error", str(exc))


def _pack_summary(pack_id: str) -> dict:
    status = storage.read_pack_status(pack_id) or {}
    templates = [
        f"{pack_id}:{path.stem}" for path in sorted(storage.pack_files_dir(pack_id).glob("*.pptx"))
    ]
    return {"id": pack_id, **status, "templates": templates}


@router.post("/api/brand-packs")
def create_brand_pack(
    name: str = Form(...),
    file: UploadFile = File(...),  # noqa: B008 (FastAPI's DI pattern)
) -> dict:
    """Unpack a zipped content pack and start building its `BrandContext` in the background.

    The pack is always one `.zip` — templates, brand docs, logos and fonts
    together — so a pack is a single artifact the company hands over.
    """
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "a brand pack is uploaded as a single .zip archive")
    data = file.file.read()
    pack_id = storage.new_id(name)
    files_dir = storage.pack_files_dir(pack_id)
    files_dir.mkdir(parents=True, exist_ok=True)
    try:
        _unpack_pack_zip(data, files_dir)
    except HTTPException:
        shutil.rmtree(storage.pack_dir(pack_id), ignore_errors=True)
        raise
    if not any(files_dir.iterdir()):
        shutil.rmtree(storage.pack_dir(pack_id), ignore_errors=True)
        raise HTTPException(400, "the archive has no supported files (.pptx, .pdf, .docx, .md, images, fonts)")
    storage.write_pack_status(pack_id, name, "building")
    threading.Thread(target=_build_pack, args=(pack_id, name), daemon=True).start()
    return _pack_summary(pack_id)


_PACK_SUFFIXES = DOC_SUFFIXES | IMAGE_SUFFIXES | FONT_SUFFIXES
_MAX_PACK_MEMBER_BYTES = 100 * 1024 * 1024


def _unpack_pack_zip(data: bytes, files_dir: Path) -> None:
    """Flatten a zipped content pack into the pack's files dir.

    Only formats the pack builder understands are kept, each under its own
    base name (never the archive's path — no zip-slip), with a numeric
    suffix on name clashes.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, "brand pack archive is not a valid ZIP") from exc
    with archive:
        for info in archive.infolist():
            path = PurePosixPath(member_name(info))
            if info.is_dir() or path.name.startswith(("._", ".")) or "__MACOSX" in path.parts:
                continue
            if path.suffix.lower() not in _PACK_SUFFIXES or info.file_size > _MAX_PACK_MEMBER_BYTES:
                continue
            name = storage.safe_filename(path.name)
            dest = files_dir / name
            n = 2
            while dest.exists():
                dest = files_dir / f"{Path(name).stem}-{n}{Path(name).suffix}"
                n += 1
            dest.write_bytes(archive.read(info))


@router.get("/api/brand-packs")
def list_brand_packs() -> dict:
    return {"packs": [_pack_summary(pack_id) for pack_id in storage.list_pack_ids()]}


@router.get("/api/brand-packs/{pack_id}")
def get_brand_pack(pack_id: str) -> dict:
    try:
        summary = _pack_summary(pack_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown brand pack: {pack_id!r}") from exc
    if "status" not in summary:
        raise HTTPException(404, f"unknown brand pack: {pack_id!r}")
    context = storage.load_brand(pack_id)
    return {**summary, "context": context.model_dump() if context else None}


@router.post("/api/sources")
def create_sources(
    story: str = Form(""),
    files: list[UploadFile] | None = File(None),  # noqa: B008 (FastAPI's DI pattern)
) -> dict:
    """Turn a talk's material into a stored `SourceBundle` of plain text.

    `.zip` uploads become repo digests; any
    document format `ingest.extract_text` reads becomes a document. Files it
    can't read are reported back in `skipped`, not treated as a failure.
    """
    repos: list[NamedText] = []
    documents: list[NamedText] = []
    skipped: list[str] = []

    for upload in files or []:
        filename = storage.safe_filename(upload.filename or "file")
        data = upload.file.read()
        suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if suffix == ".zip":
            try:
                stem = filename.rsplit(".", 1)[0]
                repos.append(NamedText(name=stem, text=digest_zip(data, stem)))
            except RepoError:
                skipped.append(filename)
        elif suffix in DOC_SUFFIXES:
            text = _document_text(filename, data)
            if text and text.strip():
                documents.append(NamedText(name=filename, text=text))
            else:
                skipped.append(filename)
        else:
            skipped.append(filename)

    if not (repos or documents or story.strip()):
        raise HTTPException(400, "no usable material: add a story, a repository, or documents")

    bundle = SourceBundle(
        id=storage.new_id("src"), repos=repos, documents=documents, story=story
    )
    storage.save_sources(bundle)
    return {
        "id": bundle.id,
        "repos": [r.name for r in repos],
        "documents": [d.name for d in documents],
        "skipped": skipped,
        "chars": len(bundle.source_text(budget=10**9)),
    }


def _document_text(filename: str, data: bytes) -> str | None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / filename
        path.write_bytes(data)
        return extract_text(path)
