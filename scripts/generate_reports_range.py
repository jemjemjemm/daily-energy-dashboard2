#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_reports_range.py v4

기간 내 주말 제외 평일 리포트를 일괄 생성합니다.
각 날짜별로 세이프타임즈 일정 수집을 먼저 시도하고,
성공하면 일정 기반 리포트를 만들고,
실패하면 빈 리포트/fallback 리포트를 보강한 뒤 가격 중심 리포트를 생성합니다.

이 스크립트는 반드시 --start, --end를 받습니다.
--date를 받는 파일이 아닙니다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="기간별 평일 리포트 일괄 생성")
    parser.add_argument("--start", required=True, help="시작일 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="종료일 YYYY-MM-DD")
    parser.add_argument("--skip-weekends", action="store_true", default=True, help="토/일 제외")
    parser.add_argument("--report-dir", default="data/reports")
    parser.add_argument("--schedule-dir", default="data/schedules")
    parser.add_argument("--price-dir", default="data/prices")
    parser.add_argument("--history", default="data/prices/history.json")
    parser.add_argument("--html-dir", default="docs/reports")
    parser.add_argument("--index-out", default="docs/report-index.json")
    parser.add_argument("--base-report", default="report_sample.json")
    parser.add_argument("--chart-months", default="2")
    parser.add_argument("--max-pages", default="12")
    return parser.parse_args()


def date_range(start: str, end: str):
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    if s > e:
        raise ValueError("--start가 --end보다 늦습니다.")
    cur = s
    while cur <= e:
        yield cur
        cur += timedelta(days=1)


def run(cmd, allow_fail: bool = False) -> bool:
    print("[RUN]", " ".join(cmd))
    completed = subprocess.run(cmd, text=True)
    if completed.returncode != 0:
        if allow_fail:
            print(f"[WARN] 명령 실패를 허용하고 다음 단계로 진행합니다: {' '.join(cmd)}")
            return False
        raise RuntimeError(f"명령 실패: {' '.join(cmd)}")
    return True


def file_exists(path: str) -> bool:
    return Path(path).exists()


def main() -> int:
    args = parse_args()

    required_files = [
        "scripts/fetch_safetimes_schedule.py",
        "scripts/build_report_draft_from_schedule.py",
        "scripts/ensure_report_draft.py",
        "scripts/merge_prices_into_report.py",
        "scripts/generate_html_report.py",
        "scripts/generate_report_index.py",
        args.history,
        args.base_report,
    ]

    for file_name in required_files:
        if not Path(file_name).exists():
            print(f"[ERROR] 필수 파일이 없습니다: {file_name}")
            return 1

    generated_dates = []

    for d in date_range(args.start, args.end):
        if args.skip_weekends and d.weekday() >= 5:
            print(f"[SKIP] 주말 제외: {d.isoformat()}")
            continue

        date_text = d.isoformat()
        generated_dates.append(date_text)

        print(f"\n=== {date_text} 리포트 생성 ===")

        schedule_path = f"{args.schedule_dir}/{date_text}.json"
        report_path = f"{args.report_dir}/{date_text}.report.json"

        # 1. 세이프타임즈 일정 수집. 실패해도 전체 백필은 멈추지 않음.
        if file_exists(schedule_path):
            print(f"[OK] 기존 세이프타임즈 일정 JSON 사용: {schedule_path}")
        else:
            run([
                sys.executable,
                "scripts/fetch_safetimes_schedule.py",
                "--date", date_text,
                "--out-dir", args.schedule_dir,
                "--max-retries", "1",
                "--retry-delay", "5",
                "--max-pages", str(args.max_pages),
            ], allow_fail=True)

        # 2. 일정 JSON이 있으면 일정 기반 리포트 재생성.
        # 기존 fallback/빈 리포트를 실제 일정 기반 리포트로 교체하기 위해 report_path를 삭제 후 생성.
        if file_exists(schedule_path):
            if file_exists(report_path):
                Path(report_path).unlink()
                print(f"[INFO] 기존 리포트 JSON 삭제 후 일정 기반으로 재생성: {report_path}")

            run([
                sys.executable,
                "scripts/build_report_draft_from_schedule.py",
                "--date", date_text,
                "--schedule-dir", args.schedule_dir,
                "--base-report", args.base_report,
                "--out-dir", args.report_dir,
            ])
        else:
            print(f"[WARN] 일정 JSON이 없어 가격 중심 기본 리포트로 보강합니다: {date_text}")

        # 3. 리포트가 없거나 빈/fallback이면 보강.
        run([
            sys.executable,
            "scripts/ensure_report_draft.py",
            "--date", date_text,
            "--out-dir", args.report_dir,
            "--base-report", args.base_report,
            "--refresh-fallback",
        ])

        # 4. 가격 병합. 과거 날짜는 history.json 기준.
        run([
            sys.executable,
            "scripts/merge_prices_into_report.py",
            "--date", date_text,
            "--report-dir", args.report_dir,
            "--price-dir", args.price_dir,
            "--history", args.history,
            "--chart-months", str(args.chart_months),
        ])

        # 5. HTML 리포트 생성.
        run([
            sys.executable,
            "scripts/generate_html_report.py",
            "--date", date_text,
            "--report-dir", args.report_dir,
            "--out-dir", args.html_dir,
        ])

    # 6. 캘린더용 index 갱신.
    run([
        sys.executable,
        "scripts/generate_report_index.py",
        "--reports-dir", args.html_dir,
        "--out", args.index_out,
    ])

    print("\n[OK] 기간 리포트 생성 완료")
    print("[OK] 생성 대상 날짜:", ", ".join(generated_dates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
