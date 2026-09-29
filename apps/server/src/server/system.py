"""What the app knows about the machine it runs on: version, folders, LibreOffice, updates.

Behind the settings screen's "Система" section, the first-run notice about
LibreOffice, and the `preza doctor` / `preza install-libreoffice` commands.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Iterator
from importlib import metadata

from export.render import soffice_path

from server import storage

VERSION = "1.0.0"
RELEASES_API = "https://api.github.com/repos/base-for-dev/project-preza/releases/latest"
DOWNLOAD_PAGE = "https://www.libreoffice.org/download/download-libreoffice/"


def version() -> str:
    try:
        return metadata.version("preza-server")
    except metadata.PackageNotFoundError:
        return VERSION


def libreoffice() -> dict:
    """Where LibreOffice is (None if missing) and what this machine would use to install it."""
    path = soffice_path()
    return {"installed": path is not None, "path": path, "installer": installer_name()}


def installer_name() -> str | None:
    """The package manager the install button will use, if there is one."""
    system = platform.system()
    if system == "Darwin" and shutil.which("brew"):
        return "Homebrew"
    if system == "Windows" and shutil.which("winget"):
        return "winget"
    if system == "Linux":
        for tool, name in (
            ("apt-get", "apt"),
            ("dnf", "dnf"),
            ("pacman", "pacman"),
            ("zypper", "zypper"),
        ):
            if shutil.which(tool):
                return name
    return None


def _install_command() -> list[str] | None:
    system = platform.system()
    if system == "Darwin" and shutil.which("brew"):
        return ["brew", "install", "--cask", "libreoffice"]
    if system == "Windows" and shutil.which("winget"):
        return [
            "winget",
            "install",
            "--id",
            "TheDocumentFoundation.LibreOffice",
            "-e",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]
    if system == "Linux":
        # pkexec asks the desktop for the password; a terminal without one falls back to sudo.
        elevate = ["pkexec"] if shutil.which("pkexec") else ["sudo"]
        for tool, args in (
            ("apt-get", ["apt-get", "install", "-y", "libreoffice-impress", "fonts-liberation"]),
            ("dnf", ["dnf", "install", "-y", "libreoffice-impress"]),
            ("pacman", ["pacman", "-S", "--noconfirm", "libreoffice-fresh"]),
            ("zypper", ["zypper", "--non-interactive", "install", "libreoffice-impress"]),
        ):
            if shutil.which(tool):
                return [*elevate, *args]
    return None


def install_libreoffice() -> Iterator[str]:
    """Run the platform's package manager and yield its output line by line.

    The last line is `OK` or `FAILED: <why>`; when there is nothing to run, the
    line says where to download it by hand.
    """
    command = _install_command()
    if command is None:
        yield f"FAILED: нет менеджера пакетов — скачайте LibreOffice вручную: {DOWNLOAD_PAGE}"
        return
    yield f"$ {' '.join(command)}"
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
    except OSError as exc:
        yield f"FAILED: {exc}"
        return
    assert process.stdout is not None
    for line in process.stdout:
        yield line.rstrip()
    code = process.wait()
    if code == 0 and soffice_path() is not None:
        yield "OK"
    elif code == 0:
        yield "FAILED: установка завершилась, но LibreOffice не найден — перезапустите приложение"
    else:
        yield f"FAILED: код выхода {code}"


def latest_release() -> dict:
    """The newest GitHub release and whether it is newer than this build."""
    try:
        request = urllib.request.Request(RELEASES_API, headers={"User-Agent": "preza"})
        with urllib.request.urlopen(request, timeout=6) as response:
            data = json.load(response)
    except Exception as exc:
        return {"current": version(), "latest": None, "newer": False, "error": str(exc)[:120]}
    latest = str(data.get("tag_name", "")).lstrip("v")

    def parts(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.split(".") if x.isdigit())

    return {
        "current": version(),
        "latest": latest or None,
        "newer": bool(latest) and parts(latest) > parts(version()),
        "url": data.get("html_url"),
    }


def summary() -> dict:
    return {
        "version": version(),
        "platform": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
        "packaged": bool(getattr(sys, "frozen", False)),
        "data_dir": str(storage.DATA_DIR),
        "libreoffice": libreoffice(),
    }
