#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wait until the target report slot time in Asia/Seoul."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    KST = ZoneInfo("Asia/Seoul")
except ZoneInfoNotFoundError:
    KST = timezone(timedelta(hours=9), name="Asia/Seoul")
TARGET_TIMES = {
    "morning": (9, 4),
    "evening": (17, 4),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wait until the report slot target time in KST.")
    parser.add_argument("report_slot", choices=sorted(TARGET_TIMES))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(KST)
    hour, minute = TARGET_TIMES[args.report_slot]
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    seconds = int((target - now).total_seconds())
    if seconds <= 0:
        print(f"[OK] {args.report_slot} target time already passed: now={now.isoformat()} target={target.isoformat()}")
        return 0

    print(f"[INFO] Waiting {seconds}s until {args.report_slot} target time: {target.isoformat()}")
    sys.stdout.flush()
    time.sleep(seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
