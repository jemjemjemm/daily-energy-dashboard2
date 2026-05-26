#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_report_index.py

docs/reports/*.html을 읽어서 캘린더 대시보드가 사용할 docs/report-index.json을 생성합니다.

사용 예:
  python scripts/generate_report_index.py \
    --reports-dir docs/reports \
    --out docs/report-index.json

운영 원칙:
- index 생성은 "이미 발간된 HTML 리포트를 대시보드에 노출할지" 판단하는 단계입니다.
- 정상 보고서에 포함될 수 있는 문구(세이프타임즈, 데이터 없음, A 직접/B 간접/C 참고 등)는 금지어로 보지 않습니다.
- 조간 기사 0건은 운영상 비정상으로 보고 index에서 제외합니다.
- 단, HTML 파일을 삭제하지는 않습니다. 삭제는 별도 수동 검토 대상입니다.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
TITLE_RE = re.compile(r"<title>\s*(.*?)\s*</title>", re.I | re.S)
HEADER_DATE_RE = re.compile(r'<div class="header-date">\s*(.*?)\s*</div>', re.I | re.S)

# 실제 오류·미완성 리포트를 식별하기 위한 문구만 유지합니다.
# 정상 운영 문구인 "세이프타임즈", "데이터 없음", "A 직접", "B 간접", "C 참고",
# "대표 기사 미확인" 등은 절대 넣지 않습니다.
BAD_HTML_PHRASES = [
    "자동 추출된 일정 항목이 없습니다",
    "본문 구조 확인 및 수동 검수가 필요합니다",
    "원문 자동 매칭 실패",
    "주요일정 원문 데이터 미확보",
    "원문 데이터 없음",
    "가격 데이터 중심 리포트",
    "가격 중심 자동생성",
    "자동 수집된 대표 기사 없음",
    "대표 기사 데이터가 아직 없습니다",
]

REQUIRED_HTML_TOKENS = ["Daily Issue Report", "Summary", "유가 동향"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="캘린더 대시보드용 report-index.json 생성")
    parser.add_argument("--reports-dir", default="docs/reports", help="HTML 리포트 폴더. 기본값 docs/reports")
    parser.add_argument("--out", default="docs/report-index.json", help="출력 JSON 파일. 기본값 docs/report-index.json")
    parser.add_argument(
        "--strict-json",
        action="store_true",
        help="data/reports/YYYY-MM-DD.report.json 검증까지 통과한 HTML만 index에 포함합니다.",
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


def now_kst_text() -> str:
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S KST")


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


def has_bad_phrase(text: str) -> bool:
    return any(phrase in text for phrase in BAD_HTML_PHRASES)


def has_required_structure(text: str) -> bool:
    return bool(text) and all(token in text for token in REQUIRED_HTML_TOKENS)


def has_morning_articles_in_html(text: str) -> bool:
    """조간 대표 기사 링크 존재 여부를 HTML 기준으로 방어적으로 확인합니다."""
    if "대표 기사" not in text and "조간" not in text:
        return False
    article_link_patterns = [
        r'<a\s+[^>]*href=["\']https?://[^"\']+["\'][^>]*>',
        r'class=["\'][^"\']*(?:article|news)[^"\']*["\']',
        r'출처\s*[:：]',
    ]
    return any(re.search(pattern, text, re.I | re.S) for pattern in article_link_patterns)


def infer_report_json_path(html_path: Path) -> Path:
    date_match = DATE_RE.search(html_path.name)
    date = date_match.group(1) if date_match else html_path.stem
    return Path("data/reports") / f"{date}.report.json"


def report_json_allows_index(html_path: Path) -> bool:
    """선택적 엄격 검증. 기본 index 복구 흐름에서는 사용하지 않습니다."""
    json_path = infer_report_json_path(html_path)
    if not json_path.exists():
        return False

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    date_match = DATE_RE.search(html_path.name)
    target = date_match.group(1) if date_match else ""
    if not target:
        return False

    auto = data.get("automation", {}) if isinstance(data.get("automation"), dict) else {}
    safetimes = auto.get("safetimes", {}) if isinstance(auto.get("safetimes"), dict) else {}
    today_src = safetimes.get("today_source_file_date")
    prev_src = safetimes.get("previous_source_file_date")

    # 일정 원문 날짜가 있는 경우에는 기준일/전일이 서로 달라야 합니다.
    if today_src and today_src != target:
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


def is_valid_report_html(text: str) -> tuple[bool, str]:
    if not text:
        return False, "empty_html"
    if has_bad_phrase(text):
        return False, "bad_phrase"
    if not has_required_structure(text):
        return False, "missing_required_structure"
    if not has_morning_articles_in_html(text):
        return False, "missing_morning_articles"
    return True, "ok"


def read_report_meta(html_path: Path, *, strict_json: bool = False) -> tuple[Dict[str, Any] | None, str | None]:
    date_match = DATE_RE.search(html_path.name)
    if not date_match:
        return None, "missing_date_in_filename"

    date = date_match.group(1)
    text = html_path.read_text(encoding="utf-8", errors="ignore")

    ok, reason = is_valid_report_html(text)
    if not ok:
        return None, reason

    if strict_json and not report_json_allows_index(html_path):
        return None, "report_json_validation_failed"

    title_match = TITLE_RE.search(text)
    header_date_match = HEADER_DATE_RE.search(text)
    title = strip_tags(title_match.group(1)) if title_match else f"Daily 유가 동향 — {date}"
    display_date = strip_tags(header_date_match.group(1)) if header_date_match else date

    return {
        "date": date,
        "displayDate": display_date,
        "title": title,
        "url": f"reports/{html_path.name}",
        "status": "발간",
        "fileName": html_path.name,
        "exists": True,
    }, None


def main() -> int:
    args = parse_args()
    reports_dir = Path(args.reports_dir)
    out_path = Path(args.out)

    if not reports_dir.exists():
        print(f"[ERROR] reports 폴더가 없습니다: {reports_dir}")
        return 1

    reports: List[Dict[str, Any]] = []
    warnings: List[Dict[str, str]] = []

    for html_path in sorted(reports_dir.glob("*.html")):
        item, reason = read_report_meta(html_path, strict_json=args.strict_json)
        if item:
            reports.append(item)
        else:
            warnings.append({"fileName": html_path.name, "reason": reason or "unknown"})

    reports.sort(key=lambda item: item["date"], reverse=True)

    payload = {
        "schemaVersion": "1.1",
        "generatedAt": now_kst_text(),
        "count": len(reports),
        "latestDate": reports[0]["date"] if reports else "",
        "availableDates": sorted([item["date"] for item in reports]),
        "warnings": warnings,
        "reports": reports,
    }

    atomic_write_json(out_path, payload)
    print(f"[OK] report-index.json 생성 완료: {out_path}")
    print(f"[OK] 리포트 수: {len(reports)}")
    if warnings:
        print(f"[WARN] 제외 HTML 수: {len(warnings)}")
        for warning in warnings[:20]:
            print(f"  - {warning['fileName']}: {warning['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
