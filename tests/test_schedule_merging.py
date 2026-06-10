#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.build_report_draft_from_schedule import schedule_items_from_json_or_body


class ScheduleMergingTest(unittest.TestCase):
    def test_2026_06_04_merges_repeated_events_and_prefers_named_attendees(self) -> None:
        schedule_data = json.loads(Path("data/schedules/2026-06-04.json").read_text(encoding="utf-8"))

        rows = schedule_items_from_json_or_body(schedule_data, max_items=20)
        by_title = {row["title"]: row for row in rows}

        emergency = by_title["비상경제본부회의"]
        self.assertEqual(emergency["time"], "09:00")
        self.assertIn("김민석 국무총리", emergency["attendees"])
        self.assertIn("구윤철 부총리 겸 재정경제부 장관", emergency["attendees"])
        self.assertIn("박윤주 외교부 1차관", emergency["attendees"])
        self.assertIn("오유경 식약처장", emergency["attendees"])
        self.assertEqual(emergency["attendees"].count("김영훈 노동부 장관"), 1)

        price_tf = by_title["민생물가 특별관리 관계장관 TF 회의"]
        self.assertEqual(price_tf["time"], "14:00")
        self.assertIn("남동일 공정위 부위원장", price_tf["attendees"])
        self.assertIn("김용재 식약차장", price_tf["attendees"])
        self.assertIn("이병권 중기부 2차관", price_tf["attendees"])

        defense = by_title["제12회 방위산업발전협의회"]
        self.assertEqual(defense["attendees"], "안규백 국방부 장관, 김정관 산업통상부 장관")

        drone = by_title["정부 드론·대드론 통합 TF 최종보고 회의"]
        self.assertEqual(drone["attendees"], "이두희 국방부 차관, 류제명 과기정통부 2차관")

        seminar = by_title["한미 관계 전망 세미나"]
        self.assertEqual(seminar["time"], "10:00 현지시간")
        self.assertEqual(seminar["attendees"], "KEI")


if __name__ == "__main__":
    unittest.main()
