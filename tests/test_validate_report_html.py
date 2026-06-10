#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.validate_report_html import validate_html_file


def report_html(date_text: str, morning_title: str, evening_title: str) -> str:
    sections = []
    for num in range(1, 5):
        sections.append(
            f'<section><div class="section-header"><span class="section-num">{num}</span>'
            f'<span class="section-title">Section {num}</span></div><div>ok</div></section>'
        )
    sections.append(
        '<section><div class="section-header"><span class="section-num">5</span>'
        '<span class="section-title">Schedules</span></div>'
        '<div class="schedule-list"><div class="schedule-row">ok</div></div></section>'
    )
    sections.append(
        '<section><div class="section-header"><span class="section-num">6</span>'
        f'<span class="section-title">{morning_title}</span></div>'
        '<div class="news-body">ok</div></section>'
    )
    sections.append(
        '<section><div class="section-header"><span class="section-num">7</span>'
        f'<span class="section-title">{evening_title}</span></div>'
        '<div class="news-body">ok</div></section>'
    )
    return f"<!doctype html><html><body><h1>{date_text}</h1>{''.join(sections)}</body></html>"


class ValidateReportHtmlTest(unittest.TestCase):
    def validate_text(self, date_text: str, morning_title: str, evening_title: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{date_text}.html"
            path.write_text(report_html(date_text, morning_title, evening_title), encoding="utf-8")
            return validate_html_file(path, "2026-05-01", False)

    def test_legacy_may_reports_allow_09_news_window(self) -> None:
        errors = self.validate_text(
            "2026-05-29",
            "News Trend - Morning (5/28 17:00 - 5/29 09:00)",
            "News Trend - Evening (5/29 09:00 - 17:00)",
        )

        self.assertEqual(errors, [])

    def test_june_reports_require_08_news_window(self) -> None:
        errors = self.validate_text(
            "2026-06-11",
            "News Trend - Morning (6/10 17:00 - 6/11 09:00)",
            "News Trend - Evening (6/11 09:00 - 17:00)",
        )

        self.assertTrue(any("expected news section titles" in error for error in errors))

    def test_june_reports_accept_08_news_window(self) -> None:
        errors = self.validate_text(
            "2026-06-11",
            "News Trend - Morning (6/10 17:00 - 6/11 08:00)",
            "News Trend - Evening (6/11 08:00 - 17:00)",
        )

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
