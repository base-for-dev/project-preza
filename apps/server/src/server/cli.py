"""The `preza` command: start the app, check the machine, install what is missing.

preza                     start (opens the browser)
preza --port 9000 --no-browser
preza doctor              what is set up and what is not
preza install-libreoffice
preza version
"""

from __future__ import annotations

import argparse
import os
import platform
import socket
import sys
import threading
import webbrowser
from pathlib import Path


def default_data_dir() -> Path:
    """The user's application-data folder for this OS."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Preza"
    if system == "Windows":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Preza"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "preza"


def free_port(preferred: int) -> int:
    """`preferred` if nothing listens there, else the next free port."""
    for port in range(preferred, preferred + 50):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit(f"нет свободного порта рядом с {preferred}")


def _prepare_environment(data_dir: Path | None) -> None:
    """Point the app at its folders before `server.main` reads them."""
    if getattr(sys, "frozen", False):
        bundle = Path(getattr(sys, "_MEIPASS", "."))
        os.environ.setdefault("PREZA_RESOURCES_DIR", str(bundle / "resources"))
    if data_dir is not None:
        os.environ["PREZA_DATA_DIR"] = str(data_dir)
    elif "PREZA_DATA_DIR" not in os.environ and (
        getattr(sys, "frozen", False) or os.environ.get("PREZA_INSTALLED")
    ):
        os.environ["PREZA_DATA_DIR"] = str(default_data_dir())
    if "PREZA_DATA_DIR" in os.environ:
        Path(os.environ["PREZA_DATA_DIR"]).mkdir(parents=True, exist_ok=True)


def _start(args: argparse.Namespace) -> int:
    _prepare_environment(args.data_dir)
    import uvicorn

    from server.main import app

    port = free_port(args.port)
    url = f"http://{args.host}:{port}"
    print(
        f"Preza {url}   (данные: {os.environ.get('PREZA_DATA_DIR', 'папка проекта')})", flush=True
    )
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=port, log_level="warning")
    return 0


def _doctor(_args: argparse.Namespace) -> int:
    _prepare_environment(None)
    from server import system

    info = system.summary()
    lo = info["libreoffice"]
    from inference import effective_settings

    key = bool(effective_settings().api_key)
    rows = [
        ("Версия", info["version"]),
        ("Система", info["platform"]),
        ("Папка данных", info["data_dir"]),
        ("Ключ модели", "есть" if key else "нет — введите в «Настройки»"),
        ("LibreOffice", lo["path"] or "не найден (превью шаблонов и PDF будет рисовать браузер)"),
    ]
    for name, value in rows:
        print(f"{name:<14}{value}")
    if not lo["installed"]:
        how = lo["installer"]
        print(
            "\nУстановить LibreOffice:",
            f"preza install-libreoffice (через {how})" if how else system.DOWNLOAD_PAGE,
        )
    return 0


def _install_libreoffice(_args: argparse.Namespace) -> int:
    from server import system

    ok = False
    for line in system.install_libreoffice():
        print(line, flush=True)
        ok = line == "OK"
    return 0 if ok else 1


def _version(_args: argparse.Namespace) -> int:
    from server import system

    print(system.version())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="preza", description="Цифровой дизайнер презентаций")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    parser.add_argument("--data-dir", type=Path, help="где хранить данные приложения")
    parser.set_defaults(run=_start)
    sub = parser.add_subparsers()
    sub.add_parser("doctor", help="что настроено, а что нет").set_defaults(run=_doctor)
    sub.add_parser("install-libreoffice", help="поставить LibreOffice").set_defaults(
        run=_install_libreoffice
    )
    sub.add_parser("version").set_defaults(run=_version)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
