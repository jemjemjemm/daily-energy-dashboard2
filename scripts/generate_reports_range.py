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
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 2026년 한국 공휴일/휴무일 중 대시보드 평일 백필에서 제외할 날짜
# 근로자의 날은 법정 공휴일은 아니지만 국내 업무일정 리포트 운영상 휴무일로 취급합니다.
KOREAN_HOLIDAYS_2026 = {
    "2026-01-01",
    "2026-02-16", "2026-02-17", "2026-02-18",
    "2026-03-02",
    "2026-05-01", "2026-05-05", "2026-05-25",
    "2026-06-03",
    "2026-08-17",
    "2026-09-24", "2026-09-25", "2026-09-28",
    "2026-10-05", "2026-10-09",
    "2026-12-25",
}


def parse_args():
    parser = argparse.ArgumentParser(description="기간별 평일 리포트 일괄 생성")
    parser.add_argument("--start", required=True, help="시작일 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="종료일 YYYY-MM-DD")
    parser.add_argument("--skip-weekends", action="store_true", default=True, help="토/일 제외")
    parser.add_argument("--skip-korean-holidays", action="store_true", default=True, help="한국 공휴일/휴무일 제외")
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


def is_report_workday(d, skip_weekends: bool, skip_holidays: bool) -> bool:
    if skip_weekends and d.weekday() >= 5:
        return False
    if skip_holidays and d.isoformat() in KOREAN_HOLIDAYS_2026:
        return False
    return True


def previous_report_workday(d, skip_weekends: bool, skip_holidays: bool):
    cur = d - timedelta(days=1)
    # 월요일 또는 연휴 다음 영업일에는 직전 리포트 영업일을 기준일 전일 이슈로 사용한다.
    for _ in range(14):
        if is_report_workday(cur, skip_weekends=skip_weekends, skip_holidays=skip_holidays):
            return cur
        cur -= timedelta(days=1)
    return d - timedelta(days=1)


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



def read_json_optional(path: str):
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: str, payload) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_source_metadata(report_path: str, date_text: str, previous_date_text: str, schedule_path: str, previous_schedule_path: str) -> None:
    """구버전 초안/보강 스크립트가 source metadata를 누락해도 Backfill 검증이 깨지지 않도록 보정합니다.

    이는 내용을 조작하는 것이 아니라, 기준일/직전영업일 분리 검증에 필요한 파일 기준일을 명시하는 단계입니다.
    """
    report = read_json_optional(report_path)
    if not report:
        return
    schedule_data = read_json_optional(schedule_path)
    prev_data = read_json_optional(previous_schedule_path)
    report_meta = report.setdefault("report", {})
    report_meta.setdefault("report_date", date_text)
    report_meta.setdefault("previous_source_date", previous_date_text)
    automation = report.setdefault("automation", {})
    safe = automation.setdefault("safetimes", {})
    safe["today_source_file_date"] = safe.get("today_source_file_date") or date_text
    safe["previous_source_file_date"] = safe.get("previous_source_file_date") or previous_date_text
    if schedule_data:
        safe["today_source_title"] = safe.get("today_source_title") or schedule_data.get("title", "")
        safe["today_source_url"] = safe.get("today_source_url") or schedule_data.get("article_url", "") or schedule_data.get("url", "")
    if prev_data:
        safe["previous_source_title"] = safe.get("previous_source_title") or prev_data.get("title", "")
        safe["previous_source_url"] = safe.get("previous_source_url") or prev_data.get("article_url", "") or prev_data.get("url", "")
    write_json(report_path, report)


def main() -> int:
    args = parse_args()

    required_files = [
        "scripts/fetch_safetimes_schedule.py",
        "scripts/build_report_draft_from_schedule.py",
        "scripts/ensure_report_draft.py",
        "scripts/merge_prices_into_report.py",
        "scripts/generate_html_report.py",
        "scripts/generate_schedule_detail_html.py",
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
        date_text = d.isoformat()

        if args.skip_weekends and d.weekday() >= 5:
            print(f"[SKIP] 주말 제외: {date_text}")
            continue

        if args.skip_korean_holidays and date_text in KOREAN_HOLIDAYS_2026:
            print(f"[SKIP] 공휴일/휴무일 제외: {date_text}")
            continue

        generated_dates.append(date_text)
        previous_d = previous_report_workday(d, skip_weekends=args.skip_weekends, skip_holidays=args.skip_korean_holidays)
        previous_date_text = previous_d.isoformat()

        print(f"\n=== {date_text} 리포트 생성 ===")
        print(f"[INFO] 기준일 일정={date_text}, 전일/직전 영업일 이슈 기준={previous_date_text}")

        schedule_path = f"{args.schedule_dir}/{date_text}.json"
        previous_schedule_path = f"{args.schedule_dir}/{previous_date_text}.json"
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

        # 1-1. 기준일 전일/직전 영업일 일정도 별도로 수집한다.
        # 주요 이해관계자 동향/이슈는 이 파일을 기준으로 만들며, 금일 일정과 절대 같은 데이터를 복사하지 않는다.
        if file_exists(previous_schedule_path):
            print(f"[OK] 기존 전일/직전 영업일 일정 JSON 사용: {previous_schedule_path}")
        else:
            run([
                sys.executable,
                "scripts/fetch_safetimes_schedule.py",
                "--date", previous_date_text,
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
                "--previous-date", previous_date_text,
                "--previous-schedule-dir", args.schedule_dir,
                "--base-report", args.base_report,
                "--out-dir", args.report_dir,
            ])
            normalize_source_metadata(report_path, date_text, previous_date_text, schedule_path, previous_schedule_path)
        else:
            raise RuntimeError(f"기준일 일정 JSON이 없어 유효한 리포트를 생성할 수 없습니다: {schedule_path}")

        # 3. 리포트가 없거나 빈/fallback이면 보강.
        run([
            sys.executable,
            "scripts/ensure_report_draft.py",
            "--date", date_text,
            "--out-dir", args.report_dir,
            "--base-report", args.base_report,
            "--refresh-fallback",
        ])
        normalize_source_metadata(report_path, date_text, previous_date_text, schedule_path, previous_schedule_path)

        # 3-1. 조간신문 트렌드 반영.
        # 기사 후보 0건은 정상 상태가 아니므로 백필도 실패시켜 검수하게 한다.
        if not Path("scripts/fetch_news_candidates.py").exists() or not Path("scripts/apply_news_to_report.py").exists():
            raise RuntimeError("뉴스 후보 수집/반영 스크립트가 없습니다.")
        run([
            sys.executable,
            "scripts/fetch_news_candidates.py",
            "--date", date_text,
            "--report-slot", "morning",
            "--out-dir", "data/news",
            "--min-required", "1",
            "--force-refresh",
        ])
        run([
            sys.executable,
            "scripts/apply_news_to_report.py",
            "--date", date_text,
            "--report-slot", "morning",
            "--news-dir", "data/news",
            "--report-dir", args.report_dir,
            "--min-required", "1",
        ])
        print(f"[INFO] News Trend slot 생성: {date_text} evening")
        run([
            sys.executable,
            "scripts/fetch_news_candidates.py",
            "--date", date_text,
            "--report-slot", "evening",
            "--out-dir", "data/news",
            "--min-required", "1",
            "--force-refresh",
        ])
        run([
            sys.executable,
            "scripts/apply_news_to_report.py",
            "--date", date_text,
            "--report-slot", "evening",
            "--news-dir", "data/news",
            "--report-dir", args.report_dir,
            "--min-required", "1",
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

        # 5. 전체 일정 상세 HTML 생성. 일정 원본이 없거나 상세 생성만 실패해도 리포트 생성은 계속 진행한다.
        schedule_detail_dir = str(Path(args.html_dir).parent / "schedules")
        if file_exists(schedule_path):
            run([
                sys.executable,
                "scripts/generate_schedule_detail_html.py",
                "--date", date_text,
                "--schedule-dir", args.schedule_dir,
                "--out-dir", schedule_detail_dir,
            ], allow_fail=True)
        else:
            print(f"[WARN] 일정 JSON이 없어 상세 HTML 생성을 건너뜁니다: {schedule_path}")

        # 6. HTML 리포트 생성.
        run([
            sys.executable,
            "scripts/generate_html_report.py",
            "--date", date_text,
            "--report-dir", args.report_dir,
            "--out-dir", args.html_dir,
        ])

    # 7. 캘린더용 index 갱신.
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
