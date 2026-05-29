#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guard daily report slot runs with done files."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    KST = ZoneInfo("Asia/Seoul")
except ZoneInfoNotFoundError:
    KST = timezone(timedelta(hours=9), name="Asia/Seoul")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check or mark report slot run completion.")
    parser.add_argument("action", choices=["check", "mark"])
    parser.add_argument("--date", required=True)
    parser.add_argument("--report-slot", choices=["morning", "evening"], required=True)
    parser.add_argument("--status-dir", default="data/run_status")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def done_path(status_dir: str, date_text: str, report_slot: str) -> Path:
    return Path(status_dir) / f"{date_text}.{report_slot}.done.json"


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, prefix=f".{path.name}.", suffix=".tmp") as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def force_enabled(args: argparse.Namespace) -> bool:
    return args.force or os.environ.get("FORCE_RUN", "").lower() == "true"


def main() -> int:
    args = parse_args()
    path = done_path(args.status_dir, args.date, args.report_slot)
    if args.action == "check":
        if path.exists() and not force_enabled(args):
            print(f"[SKIP] done file already exists: {path}")
            return 10
        if path.exists():
            print(f"[INFO] FORCE_RUN=true, ignoring existing done file: {path}")
        else:
            print(f"[OK] no done file: {path}")
        return 0

    payload = {
        "date": args.date,
        "report_slot": args.report_slot,
        "completed_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
        "status": "done",
    }
    atomic_write_json(path, payload)
    print(f"[OK] marked done: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
