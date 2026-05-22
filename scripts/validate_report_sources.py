#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate that generated reports keep today schedules and previous-day issues separated."""
from __future__ import annotations
import argparse, json, sys
from datetime import date, timedelta
from pathlib import Path

HOLIDAYS_2026 = {
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18",
    "2026-03-02", "2026-05-01", "2026-05-05", "2026-05-25",
    "2026-06-03", "2026-08-17", "2026-09-24", "2026-09-25", "2026-09-28",
    "2026-10-05", "2026-10-09", "2026-12-25",
}

def is_workday(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS_2026

def prev_workday(d: date) -> date:
    cur = d - timedelta(days=1)
    for _ in range(14):
        if is_workday(cur):
            return cur
        cur -= timedelta(days=1)
    return d - timedelta(days=1)

def check(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding='utf-8'))
    rep = data.get('report', {})
    target = rep.get('report_date') or path.name.split('.')[0]
    try:
        target_d = date.fromisoformat(target)
    except Exception:
        return [f'{path}: report_date 파싱 실패: {target!r}']
    auto = data.get('automation', {}).get('safetimes', {})
    today_src = auto.get('today_source_file_date')
    prev_src = auto.get('previous_source_file_date')
    expected_prev = prev_workday(target_d).isoformat()
    errors = []
    if today_src and today_src != target:
        errors.append(f'{path}: today_source_file_date={today_src}, expected={target}')
    if target_d != prev_workday(target_d):
        if prev_src and prev_src != expected_prev:
            errors.append(f'{path}: previous_source_file_date={prev_src}, expected={expected_prev}')
        if prev_src and prev_src == today_src:
            errors.append(f'{path}: today_source_file_date와 previous_source_file_date가 동일함: {today_src}')
    return errors

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--report-dir', default='data/reports')
    ap.add_argument('--date', default='')
    ap.add_argument('--start', default='')
    ap.add_argument('--end', default='')
    args = ap.parse_args()
    paths = []
    rd = Path(args.report_dir)
    if args.date:
        paths = [rd / f'{args.date}.report.json']
    elif args.start and args.end:
        s, e = date.fromisoformat(args.start), date.fromisoformat(args.end)
        cur = s
        while cur <= e:
            if is_workday(cur):
                paths.append(rd / f'{cur.isoformat()}.report.json')
            cur += timedelta(days=1)
    else:
        paths = sorted(rd.glob('*.report.json'))
    all_errors = []
    for p in paths:
        if p.exists():
            all_errors.extend(check(p))
    if all_errors:
        print('\n'.join('[ERROR] '+e for e in all_errors))
        return 1
    print(f'[OK] report source validation passed: {len(paths)} target(s)')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
