#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_report_index.py

Build docs/report-index.json from docs/reports/*.html for the dashboard.

핵심 수정
- docs/reports/YYYY-MM-DD.html 파일이 실제로 존재하면 기본적으로 인덱스에 포함한다.
- 본문에 '데이터 확인 필요' 같은 문구가 일부 포함되어도 전체 리포트를 제외하지 않는다.
- 기존 대시보드 호환을 위해 schemaVersion/count/latestDate/availableDates/reports 구조를 유지한다.
- docs/report-index.json 생성 시 public/report-index.json도 함께 동기화한다.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
TITLE_RE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title>", re.I | re.S)
HEADER_DATE_RE = re.compile(
    r"class=[\"'][^\"']*header-date[^\"']*[\"'][^>]*>\s*(.*?)\s*</",
    re.I | re.S,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="캘린더 대시보드용 report-index.json 생성",
        allow_abbrev=False,
    )
    parser.add_argument("--reports-dir", default="docs/reports", help="HTML 리포트 폴더")
    parser.add_argument("--out", default="docs/report-index.json", help="출력 JSON 파일")
    # 기존 workflow 호환용. 더 이상 인덱스 제외 조건으로 쓰지 않음.
    parser.add_argument("--strict-json", action="store_true", help="호환 옵션: 현재는 HTML 존재 여부 중심으로 인덱싱")
    return parser.parse_args()


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", "", value or "", flags=re.I | re.S)
    value = re.sub(r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>", "", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]*>", " ", value)
    value = (
        value.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", value).strip()


def now_kst_text() -> str:
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), delete=False,
        prefix=f".{path.name}.", suffix=".tmp",
    ) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def display_date_from_file(date_text: str, html_text: str) -> str:
    header_match = HEADER_DATE_RE.search(html_text)
    if header_match:
        header_date = strip_tags(header_match.group(1))
        if header_date:
            return header_date
    try:
        d = datetime.strptime(date_text, "%Y-%m-%d")
        weekdays = "월화수목금토일"
        return f"{d.year}년 {d.month}월 {d.day}일 ({weekdays[d.weekday()]})"
    except ValueError:
        return date_text


def title_from_file(date_text: str, html_text: str) -> str:
    title_match = TITLE_RE.search(html_text)
    if title_match:
        title = strip_tags(title_match.group(1))
        if title:
            return title
    return f"Daily 유가 동향 — {date_text}"


def is_probably_report(html_text: str) -> bool:
    # 생성 템플릿이 몇 차례 바뀌었으므로 과도한 구조 검증을 하지 않는다.
    if not html_text or len(html_text.strip()) < 200:
        return False
    lowered = html_text.lower()
    has_html_shape = "<html" in lowered or "<section" in lowered or "class=\"section" in lowered or "class='section" in lowered
    has_report_word = any(token in html_text for token in ("Daily 유가 동향", "유가 동향", "조간 신문 트렌드", "Summary"))
    return has_html_shape or has_report_word


def read_report_meta(html_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    date_match = DATE_RE.search(html_path.name)
    if not date_match:
        return None, "missing_date_in_filename"

    date_text = date_match.group(1)
    try:
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return None, f"read_failed:{exc}"

    if not is_probably_report(html_text):
        return None, "not_report_html"

    return {
        "date": date_text,
        "displayDate": display_date_from_file(date_text, html_text),
        "title": title_from_file(date_text, html_text),
        "url": f"reports/{html_path.name}",
        "status": "발간",
        "fileName": html_path.name,
        "exists": True,
    }, None


def mirror_to_public_if_needed(out_path: Path, payload: dict[str, Any]) -> None:
    normalized = out_path.as_posix().replace("\\", "/")
    if normalized == "docs/report-index.json":
        public_path = Path("public/report-index.json")
        try:
            atomic_write_json(public_path, payload)
            print(f"[OK] public index 동기화 완료: {public_path}")
        except Exception as exc:
            print(f"[WARN] public index 동기화 실패: {exc}")


def main() -> int:
    args = parse_args()
    reports_dir = Path(args.reports_dir)
    out_path = Path(args.out)

    if not reports_dir.exists():
        payload = {
            "schemaVersion": "1.1",
            "generatedAt": now_kst_text(),
            "count": 0,
            "latestDate": "",
            "availableDates": [],
            "warnings": [{"fileName": str(reports_dir), "reason": "reports_dir_missing"}],
            "reports": [],
        }
        atomic_write_json(out_path, payload)
        mirror_to_public_if_needed(out_path, payload)
        print(f"[WARN] reports 폴더가 없습니다: {reports_dir}")
        return 0

    reports: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for html_path in sorted(reports_dir.glob("*.html")):
        item, reason = read_report_meta(html_path)
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
    mirror_to_public_if_needed(out_path, payload)

    print(f"[OK] report-index.json 생성 완료: {out_path}")
    print(f"[OK] 리포트 수: {len(reports)}")
    if warnings:
        print(f"[WARN] 제외 HTML 수: {len(warnings)}")
        for warning in warnings[:20]:
            print(f" - {warning['fileName']}: {warning['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
