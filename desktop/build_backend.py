"""Freeze the API and the pipeline into one folder the desktop app ships.

    uv run python desktop/build_backend.py

Builds the static web app first (unless `--skip-web`), makes the small sample
templates, then runs PyInstaller. Result: `desktop/build/backend/` — a
`preza-backend` executable with `skills/`, `web/` and `evals/templates/`
beside it (read-only resources; the app's data goes to the user's data folder).
"""

from __future__ import annotations

import argparse
import os
import platform
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "desktop" / "build"
SEP = ";" if platform.system() == "Windows" else ":"


def build_web() -> Path:
    env = {**os.environ, "PREZA_STATIC": "1", "NEXT_PUBLIC_API_URL": ""}
    subprocess.run(["pnpm", "--filter", "web", "build"], cwd=ROOT, env=env, check=True)
    return ROOT / "apps" / "web" / ".next-static"


def make_samples(target: Path) -> None:
    """Three small templates built from code — the licensed ones never ship."""
    target.mkdir(parents=True, exist_ok=True)
    namespace = runpy.run_path(str(ROOT / "evals" / "generate_behance_templates.py"))
    namespace["main"].__globals__["OUT_DIR"] = target
    namespace["main"]()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-web", action="store_true")
    args = parser.parse_args()

    web = ROOT / "apps" / "web" / ".next-static"
    if not args.skip_web or not (web / "index.html").is_file():
        web = build_web()

    if BUILD.exists():
        shutil.rmtree(BUILD)
    resources = BUILD / "resources"
    shutil.copytree(web, resources / "web")
    shutil.copytree(ROOT / "skills", resources / "skills", ignore=shutil.ignore_patterns("__pycache__"))
    make_samples(resources / "evals" / "templates")

    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
            "--name", "preza-backend",
            "--distpath", str(BUILD / "dist"), "--workpath", str(BUILD / "work"),
            "--specpath", str(BUILD),
            "--collect-all", "pptx", "--collect-all", "pypdfium2", "--collect-all", "botocore",
            "--collect-submodules", "uvicorn", "--collect-submodules", "server",
            "--hidden-import", "uvicorn.logging", "--hidden-import", "uvicorn.loops.auto",
            "--hidden-import", "uvicorn.protocols.http.auto",
            "--hidden-import", "uvicorn.lifespan.on",
            "--add-data", f"{resources}{SEP}resources",
            str(ROOT / "desktop" / "backend_entry.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    print(f"backend: {BUILD / 'dist' / 'preza-backend'}")


if __name__ == "__main__":
    main()
