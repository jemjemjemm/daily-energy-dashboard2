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
    "세이프타임즈",
    "원문 자동 매칭 실패",
    "주요일정 원문 데이터 미확보",
    "원문 데이터 없음",
    "데이터 없음",
    "가격 데이터 중심 리포트",
    "가격 중심 자동생성",
    "Data 없음",
    "No data",
    "정유·석유화학·LNG 관련 조간 기사 후보를 찾지 못했습니다",
    "조간 기사 후보를 찾지 못했습니다",
    "자동 수집된 대표 기사 없음",
    "대표 기사 데이터가 아직 없습니다",
    "대표 기사 미확인",
    "기준일 조간 기준 주요 보도 없음",
    "기준일 조간 기준 정유·석유화학·LNG 관련 대표 기사 미확인",
    "일정 관련성 평가는",
    "A 직접",
    "B 간접",
    "C 참고",
]


def is_valid_report_html(text: str) -> bool:
    if not text:
        return False
    if any(phrase in text for phrase in BAD_HTML_PHRASES):
        return False
    required = ["Daily Issue Report", "Summary", "유가 동향"]
    return all(token in text for token in required)


def infer_report_json_path(html_path: Path) -> Path:
    date_match = DATE_RE.search(html_path.name)
    date = date_match.group(1) if date_match else html_path.stem
    return Path("data/reports") / f"{date}.report.json"


def report_json_allows_index(html_path: Path) -> bool:
    """HTML만 보고 index를 만들면 과거 구양식/가격-only 리포트가 되살아날 수 있음."""
    json_path = infer_report_json_path(html_path)
    if not json_path.exists():
        return False
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    auto = data.get("automation", {}) if isinstance(data.get("automation"), dict) else {}
    safetimes = auto.get("safetimes", {}) if isinstance(auto.get("safetimes"), dict) else {}
    today_src = safetimes.get("today_source_file_date")
    prev_src = safetimes.get("previous_source_file_date")
    date_match = DATE_RE.search(html_path.name)
    target = date_match.group(1) if date_match else ""
    if not target or today_src != target or not prev_src or prev_src == today_src:
        return False

    news = data.get("news_trend", {}) if isinstance(data.get("news_trend"), dict) else {}
    articles = news.get("articles", []) if isinstance(news.get("articles"), list) else []
    valid_articles = [a for a in articles if isinstance(a, dict) and a.get("title") and a.get("url")]
    # 조간 신문 트렌드는 매일 존재해야 하는 필수 섹션으로 본다.
    # 기사 0건 리포트는 index에 올리지 않는다.
    if not valid_articles:
        return False

    issues = data.get("issues", []) if isinstance(data.get("issues"), list) else []
    schedules = data.get("schedules", []) if isinstance(data.get("schedules"), list) else []
    return bool(issues or schedules or valid_articles)


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
    if not report_json_allows_index(html_path):
        return None

    title_match = TITLE_RE.search(text)
    header_date_match = HEADER_DATE_RE.search(text)

    title = strip_tags(title_match.group(1)) if title_match else f"Daily 유가 동향 — {date}"
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
