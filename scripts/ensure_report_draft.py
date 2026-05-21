#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ensure_report_draft.py v1.2

리포트 JSON이 없거나 fallback 리포트를 보강해야 할 때 안전하게 생성합니다.

호환성 보강:
- --out-dir 지원
- --report-dir 지원
- --base-report 지원
- --refresh-fallback 지원

따라서 기존 workflow/generate_reports_range.py가 어떤 인자명을 써도 실패하지 않습니다.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict


def parse_args():
    parser = argparse.ArgumentParser(description="리포트 JSON 안전 생성")

    parser.add_argument("--date", required=True, help="리포트 기준일 YYYY-MM-DD")

    # 둘 다 지원: 과거 스크립트 호환용
    parser.add_argument("--out-dir", default="", help="리포트 JSON 저장 폴더")
    parser.add_argument("--report-dir", default="", help="리포트 JSON 저장 폴더. --out-dir와 동일")

    parser.add_argument("--base-report", default="report_sample.json", help="기본 리포트 샘플 JSON")
    parser.add_argument(
        "--refresh-fallback",
        action="store_true",
        help="기존 파일이 fallback 리포트이면 보강된 fallback 형식으로 갱신",
    )

    args = parser.parse_args()

    if not args.out_dir and args.report_dir:
        args.out_dir = args.report_dir

    if not args.out_dir:
        args.out_dir = "data/reports"

    return args


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def read_json_optional(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_fallback_report(report: Dict[str, Any]) -> bool:
    automation = report.get("automation", {}) if isinstance(report.get("automation"), dict) else {}
    report_meta = report.get("report", {}) if isinstance(report.get("report"), dict) else {}
    version = str(report_meta.get("report_version", ""))
    status = str(report_meta.get("review_status", ""))

    return bool(automation.get("fallback_report")) or "fallback" in version or "가격 중심" in status


def date_labels(date_text: str):
    d = datetime.strptime(date_text, "%Y-%m-%d").date()
    prev = d - timedelta(days=1)
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    display = f"{d.month}/{d.day}({weekdays[d.weekday()]})"
    prev_label = f"{prev.month}/{prev.day}({weekdays[prev.weekday()]})"
    today_label = display
    return display, prev_label, today_label


def build_minimal_report(date_text: str, base_report_path: Path) -> Dict[str, Any]:
    base = read_json_optional(base_report_path)
    display, prev_label, today_label = date_labels(date_text)

    report = base if isinstance(base, dict) and base else {}

    report["report"] = {
        **(report.get("report", {}) if isinstance(report.get("report"), dict) else {}),
        "report_title": "Daily Issue Report",
        "header_title": "Daily Issue Report",
        "report_badge": "정유 · 석유화학 · LNG",
        "report_date": date_text,
        "display_date": display,
        "previous_day_label": prev_label,
        "today_label": today_label,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "report_version": "fallback-price-report-v1.2",
        "review_status": "가격 중심 자동생성 초안",
    }

    report["summary"] = [
        {
            "type": "price_only",
            "text": "해당 날짜의 일정·기사 원문 데이터가 없어 가격 데이터 중심 리포트로 생성했습니다."
        },
        {
            "type": "price_only",
            "text": "유가 및 석유제품 가격 카드는 기준일 전일 이하의 최신 history.json 데이터를 기준으로 반영합니다."
        },
        {
            "type": "review_note",
            "text": "정책·일정·기사 요약은 원문 데이터가 확보되면 후속 보완이 필요합니다."
        }
    ]

    report["issues"] = [
        {
            "category": "데이터",
            "category_class": "data",
            "title": "전일 주요 이슈 원문 데이터 없음",
            "description": "세이프타임즈 일정 및 별도 기사 데이터가 없어 주요 이슈는 자동 작성하지 않았습니다. 본 리포트는 가격 데이터 중심으로 제공됩니다.",
            "grade": "C 참고"
        }
    ]

    report["schedules"] = [
        {
            "time": "-",
            "org": "데이터",
            "title": "금일 주요 일정 원문 데이터 없음",
            "relevance": "해당 날짜의 일정 원문을 확인하지 못해 일정 영향도 평가는 작성하지 않았습니다."
        }
    ]

    report["news_trend"] = {
        "summary": "해당 날짜의 조간 신문 트렌드 원문 데이터가 없어 자동 요약을 작성하지 않았습니다. 가격 데이터 중심 리포트로 제공됩니다.",
        "articles": [
            {
                "title": "대표 기사 데이터 없음",
                "press": "자동 수집 미적용",
                "url": ""
            }
        ]
    }

    report["quality_control"] = {
        "quality_notes": [
            "세이프타임즈 일정 또는 기사 데이터가 없어 가격 중심 기본 리포트를 생성했습니다.",
            "정책·일정·기사 관련 내용은 원문 확인 후 보완해야 합니다.",
            "가격 그래프와 가격 카드는 history.json 또는 오피넷 수집 데이터 기준으로 반영됩니다."
        ],
        "sources": [
            {
                "name": "장기 가격 이력 history.json",
                "type": "price-history",
                "url": ""
            },
            {
                "name": "오피넷 국제유가",
                "type": "price",
                "url": "https://www.opinet.co.kr/"
            }
        ]
    }

    report["automation"] = {
        **(report.get("automation", {}) if isinstance(report.get("automation"), dict) else {}),
        "fallback_report": {
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
            "reason": "missing schedule/news source data",
            "script": "ensure_report_draft.py v1.2",
            "scope": "price-centered report without fabricated issue/news content"
        }
    }

    return report


def main() -> int:
    args = parse_args()
    out_path = Path(args.out_dir) / f"{args.date}.report.json"

    existing = read_json_optional(out_path)

    if existing and not (args.refresh_fallback and is_fallback_report(existing)):
        print(f"[OK] 기존 리포트 JSON 사용: {out_path}")
        return 0

    if existing and args.refresh_fallback and is_fallback_report(existing):
        print(f"[INFO] 기존 fallback 리포트를 보강 형식으로 갱신합니다: {out_path}")

    report = build_minimal_report(args.date, Path(args.base_report))
    atomic_write_json(out_path, report)

    print(f"[OK] 가격 중심 기본 리포트 JSON 생성/갱신: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
