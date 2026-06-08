#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild stored report news summaries from their displayed articles."""
from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict

try:
    from scripts.apply_news_to_report import (
        atomic_write_json,
        build_news_summary,
        is_previous_issue_summary,
        make_trend_paragraphs,
        read_json,
        update_summary,
    )
except ImportError:
    from apply_news_to_report import (  # type: ignore
        atomic_write_json,
        build_news_summary,
        is_previous_issue_summary,
        make_trend_paragraphs,
        read_json,
        update_summary,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Morning/Evening news summaries")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--report-dir", default="data/reports")
    return parser.parse_args()


def report_date(path: Path) -> date | None:
    try:
        return datetime.strptime(path.name.removesuffix(".report.json"), "%Y-%m-%d").date()
    except ValueError:
        return None


def rebuild_slot(report: Dict[str, Any], key: str) -> str:
    news = report.get(key, {}) if isinstance(report.get(key), dict) else {}
    articles = news.get("articles", []) if isinstance(news.get("articles"), list) else []
    articles = [
        article for article in articles
        if (
            isinstance(article, dict)
            and article.get("title")
            and article.get("url")
            and "데이터 없음" not in str(article.get("title"))
            and "데이터 대기" not in str(article.get("title"))
        )
    ]
    if not articles:
        if news:
            summary = "해당 시간대 주요 보도 확인 건 없음."
            news["summary"] = summary
            news["trend_paragraphs"] = []
            news["articles"] = []
            report[key] = news
            return summary
        return ""
    summary = build_news_summary(news, articles)
    news["summary"] = summary
    news["trend_paragraphs"] = make_trend_paragraphs(articles)
    report[key] = news
    return summary


def remove_previous_issue_summary(report: Dict[str, Any]) -> None:
    summary = report.get("summary", []) if isinstance(report.get("summary"), list) else []
    report["summary"] = [
        item for item in summary
        if not is_previous_issue_summary(item)
    ]


def main() -> int:
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    if start > end:
        raise SystemExit("[ERROR] --start must not be after --end")

    updated = 0
    for path in sorted(Path(args.report_dir).glob("*.report.json")):
        current = report_date(path)
        if current is None or current < start or current > end:
            continue
        report = read_json(path)
        remove_previous_issue_summary(report)
        morning_summary = rebuild_slot(report, "news_trend")
        evening_summary = rebuild_slot(report, "news_trend_afternoon")
        if morning_summary:
            update_summary(report, morning_summary, "morning")
        if evening_summary:
            update_summary(report, evening_summary, "evening")
        atomic_write_json(path, report)
        updated += 1
        print(f"[OK] rebuilt: {path}")

    print(f"[OK] rebuilt reports: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
