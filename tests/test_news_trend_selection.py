#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from scripts.apply_news_to_report import (
    build_news_summary,
    normalize_article,
    select_representative_articles,
    update_summary,
)
from scripts.fetch_news_candidates import PLAIN_QUERIES, daum_card_press, trusted_direct_count
from scripts.news_article_rules import is_forbidden_press, normalize_article_url, resolve_press


class NewsTrendSelectionTest(unittest.TestCase):
    def test_daum_press_falls_back_to_snippet_and_normalizes_portal_url(self) -> None:
        item = {
            "title": "미국산이 사우디 넘었다... 정유 업계 원유 조달 다변화",
            "press": "Daum News",
            "url": "http://v.daum.net/v/20260529060054788",
            "snippet": "파이낸셜뉴스 개별문서메뉴 톡으로 바로 공유 공유하기 기사 본문",
        }

        article = normalize_article(item)

        self.assertEqual(article["press"], "파이낸셜뉴스")
        self.assertEqual(article["press_grade"], "A")
        self.assertEqual(article["url"], "https://v.daum.net/v/20260529060054788")

    def test_daum_press_prefers_card_selector(self) -> None:
        soup = BeautifulSoup(
            '<li><span class="txt_info">연합뉴스 언론사 픽</span><a class="tit_main" href="#">국제유가 상승</a></li>',
            "html.parser",
        )

        press = daum_card_press(soup.li, "국제유가 상승", "https://v.daum.net/v/1", "")

        self.assertEqual(press, "연합뉴스")

    def test_original_url_query_is_unwrapped(self) -> None:
        link = "https://example.test/redirect?url=https%3A%2F%2Fwww.yna.co.kr%2Fview%2F1"

        self.assertEqual(normalize_article_url(link), "https://www.yna.co.kr/view/1")
        self.assertEqual(resolve_press({"url": normalize_article_url(link)}), "연합뉴스")

    def test_representatives_prioritize_trusted_press_and_limit_c_grade(self) -> None:
        candidates = [
            normalize_article({
                "title": "국제유가 급등과 원유 수급 경고",
                "press": "Daum News",
                "url": "https://v.daum.net/v/portal",
                "snippet": "국제유가 원유",
                "score": 99,
            }),
            normalize_article({
                "title": "국제유가 급등과 원유 수급 분석",
                "press": "연합뉴스",
                "url": "https://www.yna.co.kr/view/a",
                "snippet": "국제유가 원유",
                "score": 1,
            }),
            normalize_article({
                "title": "석유화학 나프타 공급망 진단",
                "press": "한스경제",
                "url": "https://www.hansbiz.co.kr/news/b",
                "snippet": "석유화학 나프타",
                "score": 1,
            }),
            normalize_article({
                "title": "LNG 수급 전망",
                "press": "지역매체A",
                "url": "https://local-a.test/c",
                "snippet": "LNG 수급",
                "score": 99,
            }),
            normalize_article({
                "title": "유류세 정책 변화",
                "press": "지역매체B",
                "url": "https://local-b.test/d",
                "snippet": "유류세",
                "score": 99,
            }),
        ]

        selected = select_representative_articles(candidates, max_articles=4, min_required=1)

        self.assertEqual([article["press"] for article in selected[:2]], ["연합뉴스", "한스경제"])
        self.assertLessEqual(sum(article["press_grade"] == "C" for article in selected), 1)
        self.assertNotIn("Daum News", {article["press"] for article in selected})

    def test_broad_single_queries_are_not_primary_queries(self) -> None:
        self.assertNotIn("에너지", PLAIN_QUERIES)
        self.assertNotIn("전력", PLAIN_QUERIES)
        self.assertNotIn("물가", PLAIN_QUERIES)

    def test_quality_count_only_accepts_direct_ab_press_candidates(self) -> None:
        candidates = [
            {"press": "연합뉴스", "title": "국제유가 급등", "snippet": ""},
            {"press": "지역매체", "title": "정유 업계 전망", "snippet": ""},
            {"press": "한국경제", "title": "물가 상승", "snippet": ""},
        ]

        self.assertEqual(trusted_direct_count(candidates), 1)
        self.assertTrue(is_forbidden_press("Naver News Search HTML + Google News RSS"))

    def test_representatives_fill_three_distinct_titles_after_topic_spread(self) -> None:
        candidates = [
            normalize_article({
                "title": title,
                "press": press,
                "url": f"https://example.test/{index}",
                "snippet": "국제유가 원유 수급",
            })
            for index, (press, title) in enumerate([
                ("연합뉴스", "호르무즈 봉쇄 뒤 원유 수급 경고"),
                ("한국경제", "중동산 원유 수입 감소, 공급선 다변화"),
                ("매일경제", "국제유가 상승에 정유업계 대응 확대"),
            ])
        ]

        selected = select_representative_articles(candidates, max_articles=3, min_required=1)

        self.assertEqual(len(selected), 3)

    def test_report_summary_is_rebuilt_from_representative_articles(self) -> None:
        articles = [{
            "title": "\uad6d\uc81c\uc720\uac00 \ud558\ub77d\uc73c\ub85c \uc6d0\uc720 \uc218\uae09 \ub9ac\uc2a4\ud06c \uc644\ud654",
            "summary": "\uc911\ub3d9 \uc815\uc138 \ubcc0\ud654\uac00 \uc6d0\uc720 \uc218\uae09\uc5d0 \ubbf8\uce58\ub294 \uc601\ud5a5 \ubcf4\ub3c4",
        }]

        summary = build_news_summary(
            {"summary": "\uc218\uc9d1 \ud6c4\ubcf4 \uc804\uccb4\uc758 \uacf5\ud1b5 \uc694\uc57d"},
            articles,
        )

        self.assertNotIn("\uc218\uc9d1 \ud6c4\ubcf4 \uc804\uccb4", summary)
        self.assertIn("\uc911\ub3d9", summary)

    def test_evening_summary_appends_without_replacing_morning(self) -> None:
        report = {
            "summary": [
                {"type": "stakeholder", "text": "\uc804\uc77c \uc8fc\uc694 \uc774\uc288: \uc694\uc57d."},
                {"type": "today", "text": "\uae08\uc77c \uc8fc\uc694 \uc77c\uc815: \uc694\uc57d."},
            ],
            "news_trend": {"summary": "\uc624\uc804 \ub274\uc2a4 \uc694\uc57d."},
        }

        update_summary(report, "\uc624\uc804 \ub274\uc2a4 \uc694\uc57d.", "morning")
        morning_rows = list(report["summary"])
        morning_news = report["news_trend"]
        report["news_trend_afternoon"] = {"summary": "\uc624\ud6c4 \ub274\uc2a4 \uc694\uc57d."}
        update_summary(report, "\uc624\ud6c4 \ub274\uc2a4 \uc694\uc57d.", "evening")

        self.assertEqual(report["summary"][:3], morning_rows)
        self.assertIs(report["summary"][2], morning_rows[2])
        self.assertIs(report["news_trend"], morning_news)
        self.assertEqual(
            report["summary"][3],
            {"type": "news_trend_afternoon", "text": "(Evening) \uc624\ud6c4 \ub274\uc2a4 \uc694\uc57d."},
        )


if __name__ == "__main__":
    unittest.main()
