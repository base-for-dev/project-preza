"""Промежуточная сдача: один бриф × N шаблонов × 3 варианта вёрстки = N*3 колод .pptx.

Работает против запущенного сервера (`uv run --package preza-server uvicorn server.main:app`):
генерация идёт тем же путём, что и из интерфейса (`POST /api/audit`), экспорт — тем же
`POST /api/export`, что и кнопка «Скачать .pptx». Рядом с колодами кладётся
`summary.json` — сколько находок аудита у каждой и сколько заняла генерация.

    uv run python evals/build_submission.py
    uv run python evals/build_submission.py --templates vktech vk-education --out submission
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

DEFAULT_TEMPLATES = ["vktech", "vk-education", "vk-workspace-conf"]
VARIANTS = ("compact", "standard", "detailed")
DEFAULT_BRIEF = (
    "Питч стартапа для инвесторов: платформа умного полива для частных садов. "
    "Проблема, решение, рынок, экономика, команда, план развития"
)


def build_one(api: str, template_id: str, brief: str, slides: int, out: Path) -> dict:
    with httpx.Client(base_url=api, timeout=httpx.Timeout(600.0)) as client:
        res = client.post(
            "/api/audit",
            json={"template_id": template_id, "brief": brief, "slide_count": slides},
        )
        res.raise_for_status()
        audit = res.json()
        summary = {
            "template": template_id,
            "total_seconds": audit["timings"]["total"],
            "variants": {},
        }
        for variant in VARIANTS:
            deck = audit[variant]["deck"]
            exported = client.post("/api/export", json=deck)
            exported.raise_for_status()
            path = out / f"{template_id}__{variant}.pptx"
            path.write_bytes(exported.content)
            checks: dict[str, int] = {}
            for f in audit[variant]["findings"]:
                checks[f["check"]] = checks.get(f["check"], 0) + 1
            summary["variants"][variant] = {
                "file": path.name,
                "slides": len(deck["slides"]),
                "findings": len(audit[variant]["findings"]),
                "by_check": checks,
                "messages": [
                    f"слайд {f['slide_index'] + 1}: {f['check']} — {f['message']}"
                    for f in audit[variant]["findings"]
                ],
            }
        return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--templates", nargs="+", default=DEFAULT_TEMPLATES)
    parser.add_argument("--brief", default=DEFAULT_BRIEF)
    parser.add_argument("--slides", type=int, default=12)
    parser.add_argument("--out", type=Path, default=Path("submission"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=len(args.templates)) as pool:
        futures = {
            t: pool.submit(build_one, args.api, t, args.brief, args.slides, args.out)
            for t in args.templates
        }
        summaries, failed = [], []
        for template_id, future in futures.items():
            try:
                summaries.append(future.result())
            except Exception as exc:  # one template failing must not lose the others
                failed.append({"template": template_id, "error": str(exc)})

    (args.out / "summary.json").write_text(
        json.dumps(
            {"brief": args.brief, "decks": summaries, "failed": failed},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    for s in summaries:
        counts = ", ".join(f"{v}={d['findings']}" for v, d in s["variants"].items())
        print(f"{s['template']}: {s['total_seconds']}s  находок: {counts}")
    for f in failed:
        print(f"{f['template']}: FAILED — {f['error']}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
