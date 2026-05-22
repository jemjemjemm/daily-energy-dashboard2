#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_report_index.py

docs/reports/*.html을 읽어서
캘린더 대시보드가 사용할 docs/report-index.json을 생성합니다.

사용 예:
  python scripts/generate_report_index.py \
    --reports-dir docs/reports \
    --out docs/report-index.json

주의:
- 이 스크립트는 --date가 필요 없습니다.
- 이미 생성된 HTML 리포트 목록을 스캔해서 index를 만드는 역할입니다.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
TITLE_RE = re.compile(r"<title>\s*(.*?)\s*</title>", re.I | re.S)
HEADER_DATE_RE = re.compile(r'<div class="header-date">\s*(.*?)\s*</div>', re.I | re.S)


BAD_HTML_PHRASES = [
    "자동 추출된 일정 항목이 없습니다",
    "본문 구조 확인 및 수동 검수가 필요합니다",
    "세이프타임즈 '' 원문",
    "원문 자동 매칭 실패",
    "주요일정 원문 데이터 미확보",
    "원문 데이터 없음",
    "가격 데이터 중심 리포트",
    "Data 없음",
    "No data",
]


def is_valid_report_html(text: str) -> bool:
    if not text:
        return False
    if any(phrase in text for phrase in BAD_HTML_PHRASES):
        return False
    has_report_title = ("Daily Issue Report" in text) or ("Daily 유가 동향" in text)
    required = ["Summary", "유가 동향"]
    return has_report_title and all(token in text for token in required)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="캘린더 대시보드용 report-index.json 생성")
    parser.add_argument(
        "--reports-dir",
        default="docs/reports",
        help="HTML 리포트 폴더. 기본값 docs/reports",
    )
    parser.add_argument(
        "--out",
        default="docs/report-index.json",
        help="출력 JSON 파일. 기본값 docs/report-index.json",
    )
    return parser.parse_args()


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]*>", "", value or "")
    value = (
        value.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", value).strip()


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


def read_report_meta(html_path: Path) -> Dict[str, Any] | None:
    date_match = DATE_RE.search(html_path.name)
    if not date_match:
        return None

    date = date_match.group(1)
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    if not is_valid_report_html(text):
        return None

    title_match = TITLE_RE.search(text)
    header_date_match = HEADER_DATE_RE.search(text)

    title = "Daily Issue Report"
    display_date = strip_tags(header_date_match.group(1)) if header_date_match else date

    return {
        "date": date,
        "displayDate": display_date,
        "title": title,
        "url": f"reports/{html_path.name}",
        "status": "초안",
        "fileName": html_path.name,
        "exists": True,
    }


def main() -> int:
    args = parse_args()
    reports_dir = Path(args.reports_dir)
    out_path = Path(args.out)

    if not reports_dir.exists():
        print(f"[ERROR] reports 폴더가 없습니다: {reports_dir}")
        return 1

    reports: List[Dict[str, Any]] = []

    for html_path in sorted(reports_dir.glob("*.html")):
        item = read_report_meta(html_path)
        if item:
            reports.append(item)

    reports.sort(key=lambda item: item["date"], reverse=True)

    payload = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "count": len(reports),
        "latestDate": reports[0]["date"] if reports else "",
        "availableDates": sorted([item["date"] for item in reports]),
        "warnings": [],
        "reports": reports,
    }

    atomic_write_json(out_path, payload)

    print(f"[OK] report-index.json 생성 완료: {out_path}")
    print(f"[OK] 리포트 수: {len(reports)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
