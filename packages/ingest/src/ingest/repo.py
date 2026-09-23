"""Repository (ZIP archive or public GitHub URL) -> a compact text digest.

The digest is what a person skimming the repo for a talk would read: the
README, top-level and `docs/` Markdown, package manifests, and a shallow file
tree with language counts. Source code itself is not included — for a
presentation the *story* of the project lives in its docs, and whole source
files would blow the prompt budget without adding pitchable facts.

Archives are read in place via `zipfile` (never extracted to disk), so a
malicious entry name like `../../etc/passwd` can't write anywhere.
"""

from __future__ import annotations

import io
import json
import re
import tomllib
import zipfile
from collections import Counter
from pathlib import PurePosixPath

import httpx

# Directories that are build output, dependencies, or VCS internals — never
# part of the project's story.
_SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", "vendor", ".idea", ".vscode", "target", ".pytest_cache", ".ruff_cache",
    "coverage", ".turbo", ".cache",
}
_DOC_SUFFIXES = {".md", ".markdown", ".rst", ".txt", ".adoc"}
_LANGUAGE_BY_SUFFIX = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
    ".swift": "Swift", ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".cpp": "C++",
    ".c": "C", ".scala": "Scala", ".dart": "Dart", ".vue": "Vue", ".svelte": "Svelte",
    ".sql": "SQL", ".ipynb": "Jupyter",
}
_MANIFESTS = {"package.json", "pyproject.toml", "Cargo.toml", "go.mod", "requirements.txt"}

MAX_ARCHIVE_BYTES = 80 * 1024 * 1024
README_BUDGET = 10_000
DOC_BUDGET = 5_000
TOTAL_BUDGET = 28_000

_GITHUB_URL = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?"
    r"(?:/tree/(?P<ref>[^?#]+))?/?(?:[?#].*)?$"
)


class RepoError(ValueError):
    """The archive or URL couldn't be turned into a repo digest."""


def fetch_github_zip(url: str, *, client: httpx.Client | None = None) -> tuple[str, bytes]:
    """Download a public GitHub repo as a ZIP. Returns (repo name, archive bytes)."""
    match = _GITHUB_URL.match(url.strip())
    if not match:
        raise RepoError(f"not a GitHub repository URL: {url!r}")
    owner, repo, ref = match["owner"], match["repo"], match["ref"] or "HEAD"
    archive_url = f"https://codeload.github.com/{owner}/{repo}/zip/{ref}"
    http = client or httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))
    try:
        response = http.get(archive_url, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise RepoError(f"could not download {url}: {exc}") from exc
    finally:
        if client is None:
            http.close()
    if response.status_code != 200:
        raise RepoError(
            f"GitHub returned {response.status_code} for {url} — is the repository public?"
        )
    if len(response.content) > MAX_ARCHIVE_BYTES:
        raise RepoError(f"repository archive is over {MAX_ARCHIVE_BYTES // 2**20} MB")
    return repo, response.content


def digest_zip(archive: bytes, name: str) -> str:
    """Text digest of a repository archive (see module docstring for what's in it)."""
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise RepoError(f"archive is over {MAX_ARCHIVE_BYTES // 2**20} MB")
    try:
        zf = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise RepoError("not a valid ZIP archive") from exc

    with zf:
        files = _repo_files(zf)
        root = _common_root(files)
        rel = {path: _strip_root(path, root) for path in files}

        def read(path: str, limit: int) -> str:
            data = zf.read(path)[: limit * 4]
            return data.decode("utf-8", errors="replace")[:limit]

        parts = [f"# Repository: {name}", _tree_summary(list(rel.values()))]

        readmes = sorted(
            (p for p, r in rel.items() if PurePosixPath(r).stem.lower() == "readme"),
            key=lambda p: rel[p].count("/"),
        )
        if readmes:
            parts.append(f"## {rel[readmes[0]]}\n{read(readmes[0], README_BUDGET)}")

        for path in sorted(files, key=lambda p: rel[p]):
            r = PurePosixPath(rel[path])
            if r.name in _MANIFESTS and len(r.parts) <= 3:
                summary = _manifest_summary(r.name, read(path, 20_000))
                if summary:
                    parts.append(f"## {rel[path]}\n{summary}")

        docs = [
            p for p in files
            if PurePosixPath(rel[p]).suffix.lower() in _DOC_SUFFIXES
            and p not in readmes[:1]
            and PurePosixPath(rel[p]).name not in _MANIFESTS
        ]
        # Top-level docs first (ARCHITECTURE.md, PRODUCT.md...), then docs/.
        docs.sort(key=lambda p: (rel[p].count("/"), not rel[p].lower().startswith("docs"), rel[p]))
        for path in docs:
            if sum(len(p) for p in parts) >= TOTAL_BUDGET:
                break
            parts.append(f"## {rel[path]}\n{read(path, DOC_BUDGET)}")

    return "\n\n".join(parts)[:TOTAL_BUDGET]


def _repo_files(zf: zipfile.ZipFile) -> list[str]:
    files = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        parts = PurePosixPath(info.filename).parts
        if any(part in _SKIP_DIRS for part in parts):
            continue
        files.append(info.filename)
    return files


def _common_root(files: list[str]) -> str:
    """GitHub archives wrap everything in one `<repo>-<ref>/` folder — find it."""
    tops = {PurePosixPath(f).parts[0] for f in files if len(PurePosixPath(f).parts) > 1}
    if len(tops) == 1 and all(len(PurePosixPath(f).parts) > 1 for f in files):
        return tops.pop()
    return ""


def _strip_root(path: str, root: str) -> str:
    return path[len(root) + 1 :] if root and path.startswith(root + "/") else path


def _tree_summary(paths: list[str]) -> str:
    languages = Counter(
        _LANGUAGE_BY_SUFFIX[s] for p in paths if (s := PurePosixPath(p).suffix.lower())
        in _LANGUAGE_BY_SUFFIX
    )
    dirs: Counter[str] = Counter()
    for p in paths:
        parts = PurePosixPath(p).parts
        if len(parts) > 1:
            dirs["/".join(parts[: min(2, len(parts) - 1)])] += 1
    lines = [f"{len(paths)} files."]
    if languages:
        lines.append(
            "Languages (files): " + ", ".join(f"{k} {v}" for k, v in languages.most_common(8))
        )
    if dirs:
        lines.append("Structure:")
        lines.extend(f"- {d}/ ({n} files)" for d, n in sorted(dirs.items())[:40])
    return "\n".join(lines)


def _manifest_summary(filename: str, text: str) -> str | None:
    """Name, description, and dependency names — the pitchable parts of a manifest."""
    try:
        if filename == "package.json":
            data = json.loads(text)
            deps = list(data.get("dependencies", {}))[:25]
            return _join(data.get("name"), data.get("description"), deps)
        if filename == "pyproject.toml":
            project = tomllib.loads(text).get("project", {})
            deps = [re.split(r"[<>=!~\[; ]", d)[0] for d in project.get("dependencies", [])]
            return _join(project.get("name"), project.get("description"), deps[:25])
        if filename == "Cargo.toml":
            data = tomllib.loads(text)
            package = data.get("package", {})
            return _join(package.get("name"), package.get("description"), list(data.get("dependencies", {}))[:25])
        if filename in {"go.mod", "requirements.txt"}:
            return text[:1_500]
    except (ValueError, tomllib.TOMLDecodeError):
        return None
    return None


def _join(name: str | None, description: str | None, deps: list[str]) -> str | None:
    lines = []
    if name:
        lines.append(f"name: {name}")
    if description:
        lines.append(f"description: {description}")
    if deps:
        lines.append("dependencies: " + ", ".join(deps))
    return "\n".join(lines) or None
