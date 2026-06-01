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
        make_trend_paragraphs,
        read_json,
        update_summary,
    )
except ImportError:
    from apply_news_to_report import (  # type: ignore
        atomic_write_json,
        build_news_summary,
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
    articles = [article for article in articles if isinstance(article, dict)]
    if not articles:
        return ""
    summary = build_news_summary(news, articles)
    news["summary"] = summary
    news["trend_paragraphs"] = make_trend_paragraphs(articles)
    report[key] = news
    return summary


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
