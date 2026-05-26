#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build report-index.json for the dashboard calendar.

The index validator must accept both the old template and the new mobile template.
It rejects only true fallback/broken reports, not normal source labels.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
TITLE_RE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title>", re.I | re.S)
HEADER_DATE_RE = re.compile(r'<div[^>]*class=["\'][^"\']*header-date[^"\']*["\'][^>]*>\s*(.*?)\s*</div>', re.I | re.S)

BAD_HTML_PHRASES = [
    "자동 추출된 일정 항목이 없습니다",
    "본문 구조 확인 및 수동 검수가 필요합니다",
    "원문 자동 매칭 실패",
    "주요일정 원문 데이터 미확보",
    "원문 데이터 없음",
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
]


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]*>", "", value or "")
    value = (
        value.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", value).strip()


def is_valid_report_html(text: str) -> bool:
    if not text:
        return False
    if any(phrase in text for phrase in BAD_HTML_PHRASES):
        return False

    has_title = (
        "Daily Issue Report" in text
        or "Daily 유가 동향" in text
        or "Daily_유가_동향" in text
    )
    has_sections = (
        "Summary" in text
        and "유가 동향" in text
        and "조간 신문 트렌드" in text
    )
    has_news = (
        "news-item" in text
        or "news-link" in text
        or "대표 기사" in text
    )
    has_layout = (
        "report-section" in text
        or "section" in text
        or "container" in text
    )
    return has_title and has_sections and has_news and has_layout


def infer_report_json_path(html_path: Path) -> Path:
    date_match = DATE_RE.search(html_path.name)
    date = date_match.group(1) if date_match else html_path.stem
    return Path("data/reports") / f"{date}.report.json"


def report_json_allows_index(html_path: Path) -> bool:
    """Prevent price-only/fallback reports from being listed."""
    json_path = infer_report_json_path(html_path)
    if not json_path.exists():
        # Keep dashboard usable if only docs/ was deployed. HTML structure validation still applies.
        return True
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

    if today_src and target and today_src != target:
        return False
    if today_src and prev_src and today_src == prev_src:
        return False

    news = data.get("news_trend", {}) if isinstance(data.get("news_trend"), dict) else {}
    articles = news.get("articles", []) if isinstance(news.get("articles"), list) else []
    valid_articles = [a for a in articles if isinstance(a, dict) and a.get("title") and a.get("url")]
    if not valid_articles:
        return False

    issues = data.get("issues", []) if isinstance(data.get("issues"), list) else []
    schedules = data.get("schedules", []) if isinstance(data.get("schedules"), list) else []
    return bool(issues or schedules or valid_articles)


def read_report_meta(html_path: Path) -> dict[str, Any] | None:
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


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, prefix=f".{path.name}.", suffix=".tmp") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="캘린더 대시보드용 report-index.json 생성")
    parser.add_argument("--reports-dir", default="docs/reports", help="HTML 리포트 폴더")
    parser.add_argument("--out", default="docs/report-index.json", help="출력 JSON 파일")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reports_dir = Path(args.reports_dir)
    out_path = Path(args.out)
    if not reports_dir.exists():
        print(f"[ERROR] reports 폴더가 없습니다: {reports_dir}")
        return 1

    reports: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for html_path in sorted(reports_dir.glob("*.html")):
        item = read_report_meta(html_path)
        if item:
            reports.append(item)
        else:
            warnings.append({"fileName": html_path.name, "reason": "missing_required_structure"})

    reports.sort(key=lambda item: item["date"], reverse=True)
    payload = {
        "schemaVersion": "1.1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "count": len(reports),
        "latestDate": reports[0]["date"] if reports else "",
        "availableDates": sorted([item["date"] for item in reports]),
        "warnings": warnings,
        "reports": reports,
    }
    atomic_write_json(out_path, payload)
    print(f"[OK] report-index.json 생성 완료: {out_path}")
    print(f"[OK] 리포트 수: {len(reports)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
