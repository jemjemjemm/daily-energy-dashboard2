#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
build_report_draft_from_schedule.py

세이프타임즈 수집 JSON을 리포트용 JSON 초안에 반영하는 변환 스크립트 v1.0

역할
- data/schedules/YYYY-MM-DD.json 파일을 읽는다.
- report_sample.json 또는 지정한 base report JSON을 복사해 리포트 초안으로 사용한다.
- 세이프타임즈 본문에서 시간/기관/일정명을 최대한 추출해 schedules 영역에 넣는다.
- Summary 2번 항목을 '금일 주요 일정 요약'으로 갱신한다.
- quality_control.sources에 세이프타임즈 원문 링크를 추가한다.
- data/reports/YYYY-MM-DD.report.json 파일로 저장한다.

기본 사용법
    python scripts/build_report_draft_from_schedule.py --date 2026-05-20

입력
    data/schedules/2026-05-20.json
    report_sample.json

출력
    data/reports/2026-05-20.report.json

주의
- 이 스크립트는 '초안' 생성용입니다.
- 세이프타임즈 원문은 기사 본문 형식이 매일 조금씩 다를 수 있으므로, 추출 결과는 사람이 한 번 확인하는 것이 좋습니다.
- 일정 관련성 문구는 보수적으로 '확인 필요' 중심으로 생성합니다.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class DraftBuildError(RuntimeError):
    """리포트 초안 생성 중단이 필요한 오류."""


TIME_PATTERNS = [
    # 10:00, 10：00
    re.compile(r"(?P<time>\b\d{1,2}[:：]\d{2}\b)"),
    # 오전 10시 30분 / 오후 2시
    re.compile(r"(?P<ampm>오전|오후)\s*(?P<hour>\d{1,2})시(?:\s*(?P<minute>\d{1,2})분)?"),
    # 10시 30분 / 14시
    re.compile(r"(?P<hour>\d{1,2})시(?:\s*(?P<minute>\d{1,2})분)?"),
]

ORG_KEYWORDS = [
    "대통령", "국무총리", "총리", "재경부", "기재부", "산업부", "기후부", "환경부", "국토부",
    "외교부", "해수부", "공정위", "금융위", "금감원", "국회", "산중위", "기재위", "정무위",
    "대한상의", "무역협회", "한은", "한국은행", "정부", "여당", "야당", "국제", "미국", "중국", "일본"
]

DEFAULT_RELEVANCE = ""
NO_RELATED_LINK = {"label": "관련 기사 없음", "url": ""}

# 리포트에 올릴 일정은 정유·석유화학·LNG 및 정책/물가/공급망 인접 이슈만 남긴다.
# 선거 유세, 문화·스포츠, 일반 지자체 행사는 제외한다.
RELEVANT_KEYWORDS = [
    "석유", "정유", "유가", "주유소", "유류세", "최고가격", "휘발유", "경유", "나프타",
    "LNG", "가스", "에너지", "전력", "원전", "수소", "ESS", "기후", "탄소", "배출권",
    "산업부", "산업통상", "기후에너지", "기후부", "공정위", "재경부", "기재부",
    "물가", "공급망", "비상경제", "중동", "호르무즈", "수급", "통상", "관세",
    "산중위", "산업통상자원", "정무위", "에너지위원회", "통상추진",
]

EXCLUDE_KEYWORDS = [
    "지원유세", "후보", "선거", "시장 방문", "체육", "야구", "농구", "테니스", "골프",
    "문화", "축제", "공연", "전시", "스승의날", "어린이", "도박문제", "한센인의 날",
    "부동산관계장관회의", "계란 수급", "양파 수급",
]


BAD_INTERNAL_PHRASES = [
    "자동 추출된 일정 항목이 없습니다",
    "본문 구조 확인 및 수동 검수가 필요합니다",
    "원문 자동 매칭 실패",
    "원문 데이터 없음",
    "가격 데이터 중심",
]


def has_bad_phrase(value: str) -> bool:
    return any(phrase in (value or "") for phrase in BAD_INTERNAL_PHRASES)


def clean_title(value: str) -> str:
    value = normalize_line(value)
    value = value.replace("세이프타임즈", "").strip()
    value = re.sub(r"^[▲△▶▷□■◇◆○●\s]+", "", value).strip()
    return value


def is_section_header_only(value: str) -> bool:
    value = clean_title(value)
    if not value:
        return True
    if re.fullmatch(r"\[?[가-힣A-Za-z·ㆍ/ ]{2,20}\]?", value):
        # [기후에너지환경부], 국회, 외교부 같은 섹션 헤더는 일정이 아니다.
        if not any(word in value for word in ["회의", "간담회", "브리핑", "토론회", "방문", "발표", "점검", "법안", "위원회"]):
            return True
    return False


def source_url(schedule_data: Dict[str, Any]) -> str:
    return schedule_data.get("article_url") or schedule_data.get("url") or ""


def source_body(schedule_data: Dict[str, Any]) -> str:
    return schedule_data.get("raw_text") or schedule_data.get("body") or ""


def normalize_schedule_item(item: Dict[str, Any]) -> Optional[Dict[str, str]]:
    text_blob = " ".join(str(item.get(k, "")) for k in ("time", "org", "title", "text", "relevance"))
    if has_bad_phrase(text_blob):
        return None

    raw_title = str(item.get("title") or item.get("text") or "").strip()
    title = clean_title(raw_title)
    if not title or is_section_header_only(title):
        return None

    time_text = str(item.get("time") or "").strip()
    org = str(item.get("org") or "").strip()

    # schema_version 2.0처럼 text만 있는 과거 JSON은 여기서 시간/기관을 다시 분리한다.
    # 단, 화면에 보이는 일정명은 원문 문구를 최대한 보존한다.
    if not time_text or time_text == "-" or not org:
        parsed_time, without_time = extract_time(title)
        parsed_org, _parsed_title = extract_org(without_time)
        if (not time_text or time_text == "-") and parsed_time:
            time_text = parsed_time
        if not org or org in {"확인", "정치", "경제"}:
            org = parsed_org

    if not title or is_section_header_only(title):
        return None

    return {
        "time": time_text or "시간미정",
        "org": org or "확인",
        "title": title,
        "relevance": "",  # 금일 주요 일정에는 영향도/관련성 설명을 노출하지 않음
    }


def is_relevant_schedule_item(item: Dict[str, str]) -> bool:
    combined = f"{item.get('org','')} {item.get('title','')} {item.get('relevance','')}"
    # 선거·농축산물·부동산 등은 단어상 '수급/전력/시장'이 섞여도 본 보고서 대상에서 제외
    hard_exclude = ["지원유세", "후보", "선거", "전력노조", "계란 수급", "양파 수급", "부동산관계장관회의"]
    if any(word in combined for word in hard_exclude):
        return False
    if any(word in combined for word in EXCLUDE_KEYWORDS) and not any(word in combined for word in ["석유", "정유", "석유화학", "LNG", "가스", "에너지", "전력기자재", "유가", "유류세"]):
        return False
    return any(word in combined for word in RELEVANT_KEYWORDS)


def filter_relevant_items(items: List[Dict[str, str]], max_items: int) -> List[Dict[str, str]]:
    filtered = [item for item in items if is_relevant_schedule_item(item)]
    return sort_schedule_items(filtered[:max_items])


def split_title_time_location(title: str) -> Tuple[str, str, str]:
    title = clean_title(title)
    parsed_time = ""
    location = ""
    while True:
        match = re.search(r"\(([^()]*)\)\s*$", title)
        if not match:
            break
        inner = normalize_line(match.group(1))
        inner_time_match = re.search(r"\b\d{1,2}[:：]\d{2}\b", inner)
        if inner_time_match and not parsed_time:
            parsed_time = inner_time_match.group(0).replace("：", ":")
        inner_location = re.sub(r"\b\d{1,2}[:：]\d{2}\b", "", inner).strip()
        inner_location = normalize_line(inner_location)
        if inner_location:
            location = inner_location if not location else f"{inner_location} · {location}"
        title = normalize_line(title[:match.start()])
    leading_time = re.match(r"^\b\d{1,2}[:：]\d{2}\b", title)
    if leading_time and not parsed_time:
        parsed_time = leading_time.group(0).replace("：", ":")
    title = re.sub(r"^\b\d{1,2}[:：]\d{2}\b\s*", "", title).strip()
    # 일부 원문은 '10:00 참석자, 회의명' 형태로 들어온다.
    if "," in title:
        left, right = [part.strip() for part in title.split(",", 1)]
        if any(role in left for role in ["장관", "차관", "위원장", "의장", "지사", "시장", "대표", "원내대표"]) and right:
            title = right
    return title or clean_title(title), parsed_time, location


def issue_description(time: str, org: str, location: str) -> str:
    parts = []
    if time and time != "시간미정":
        parts.append(time)
    if org:
        parts.append(org)
    if location:
        parts.append(location)
    return " · ".join(parts)


def build_issue_cards_from_schedules(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    cards = []
    for item in items[:6]:
        org = item.get('org', '')
        raw_title = item.get('title', '')
        time = item.get('time', '')
        title, parsed_time, location = split_title_time_location(raw_title)
        if (not time or time == "시간미정") and parsed_time:
            time = parsed_time
        combined = f"{org} {raw_title} {title}"
        if any(k in combined for k in ["석유", "정유", "주유소", "유가", "유류세", "석유화학"]):
            category = "에너지·산업"
        elif any(k in combined for k in ["LNG", "가스", "에너지", "전력", "원전", "ESS", "기후"]):
            category = "에너지"
        elif any(k in combined for k in ["물가", "공급망", "비상경제", "재경부", "기재부", "공정위"]):
            category = "정책"
        elif any(k in combined for k in ["국회", "위원회"]):
            category = "국회"
        else:
            category = "정책"
        desc = issue_description(time, org, location)
        cards.append({
            "category": category,
            "category_class": "",
            "title": title,
            "description": desc,
            "time": time,
            "org": org,
            "location": location,
            "links": [dict(NO_RELATED_LINK)],
            "grade": "",
            "grade_class": "",
        })
    return cards


def schedule_items_from_json_or_body(schedule_data: Dict[str, Any], max_items: int) -> List[Dict[str, str]]:
    # 세이프타임즈 items는 text만 저장되는 경우가 많아 직전 기관 헤더(▲ 산업부 등)가 사라진다.
    # 따라서 원문 body를 우선 파싱해 기관 문맥을 살리고, body 파싱이 실패할 때만 items를 fallback으로 사용한다.
    parsed = parse_schedule_items(source_body(schedule_data), max_items=max_items * 30)
    if parsed:
        return filter_relevant_items(parsed, max_items=max_items)

    structured = []
    for raw_item in schedule_data.get("items") or []:
        if isinstance(raw_item, dict):
            normalized = normalize_schedule_item(raw_item)
            if normalized:
                structured.append(normalized)

    return filter_relevant_items(structured, max_items=max_items)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="세이프타임즈 일정 JSON을 리포트용 JSON 초안에 반영")
    parser.add_argument("--date", required=True, help="기준일 YYYY-MM-DD")
    parser.add_argument(
        "--schedule-dir",
        default="data/schedules",
        help="세이프타임즈 수집 JSON 폴더. 기본값 data/schedules",
    )
    parser.add_argument(
        "--previous-date",
        default="",
        help="전일/직전 영업일 일정 기준 날짜 YYYY-MM-DD. 비우면 기준일 전일을 사용",
    )
    parser.add_argument(
        "--previous-schedule-dir",
        default="",
        help="전일/직전 영업일 일정 JSON 폴더. 비우면 --schedule-dir 사용",
    )
    parser.add_argument(
        "--base-report",
        default="report_sample.json",
        help="기준 리포트 JSON. 기본값 report_sample.json",
    )
    parser.add_argument(
        "--out-dir",
        default="data/reports",
        help="리포트 초안 저장 폴더. 기본값 data/reports",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=12,
        help="리포트에 반영할 최대 일정 수. 기본값 12",
    )
    return parser.parse_args()


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise DraftBuildError(f"파일을 찾을 수 없습니다: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DraftBuildError(f"JSON 파일을 읽을 수 없습니다: {path} / {exc}") from exc


def read_json_optional(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def parse_date(date_text: str) -> datetime:
    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError as exc:
        raise DraftBuildError("--date는 YYYY-MM-DD 형식이어야 합니다.") from exc


def weekday_ko(dt: datetime) -> str:
    return "월화수목금토일"[dt.weekday()]


def short_date_label(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}"


def display_date(dt: datetime) -> str:
    return f"{dt.year}년 {dt.month}월 {dt.day}일 ({weekday_ko(dt)})"


def normalize_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line or "").strip()
    line = re.sub(r"^[·ㆍ•\-\*\s]+", "", line)
    return line.strip()


def split_body_lines(body: str) -> List[str]:
    raw_lines = []
    for line in (body or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = normalize_line(line)
        if not line:
            continue

        # 기사 제목/기자명/저작권성 문구 제거
        drop_patterns = [
            "오늘의 주요일정",
            "세이프타임즈",
            "저작권자",
            "무단전재",
            "SNS 기사보내기",
            "댓글",
        ]
        if any(pattern in line for pattern in drop_patterns):
            continue

        raw_lines.append(line)

    # 너무 짧은 단독 라인은 일정 제목이 아닐 가능성이 높아 제거
    return [line for line in raw_lines if len(line) >= 4]


def normalize_time_from_match(match: re.Match) -> str:
    if "time" in match.groupdict() and match.group("time"):
        return match.group("time").replace("：", ":")

    groupdict = match.groupdict()
    hour = int(groupdict.get("hour") or 0)
    minute = int(groupdict.get("minute") or 0)
    ampm = groupdict.get("ampm")

    if ampm == "오후" and hour < 12:
        hour += 12
    if ampm == "오전" and hour == 12:
        hour = 0

    return f"{hour:02d}:{minute:02d}"


def extract_time(line: str) -> Tuple[str, str]:
    """
    반환: (time, line_without_time)
    """
    for pattern in TIME_PATTERNS:
        match = pattern.search(line)
        if match:
            time_text = normalize_time_from_match(match)
            cleaned = (line[:match.start()] + " " + line[match.end():]).strip()
            cleaned = normalize_line(cleaned)
            return time_text, cleaned

    # '현지시간', '현지'가 있으면 시간 대신 현지로 표시
    if "현지" in line:
        return "현지", normalize_line(line.replace("현지시간", "").replace("현지", ""))

    return "", line


def extract_org(line: str) -> Tuple[str, str]:
    for keyword in ORG_KEYWORDS:
        if keyword in line:
            # 기관명이 괄호나 앞부분에 있는 경우를 우선 처리
            cleaned = line.replace(keyword, "", 1)
            cleaned = normalize_line(cleaned)
            return keyword, cleaned or line

    # 괄호 안 기관명 예: (국회) 전체회의
    match = re.match(r"^\(?([가-힣A-Za-z0-9·ㆍ]{2,12})\)?\s+(.+)$", line)
    if match:
        possible_org = match.group(1)
        title = normalize_line(match.group(2))
        if len(possible_org) <= 8 and title:
            return possible_org, title

    return "확인", line


def guess_relevance(org: str, title: str) -> str:
    combined = f"{org} {title}"

    if any(word in combined for word in ["유가", "석유", "주유소", "정유", "기름", "유류세"]):
        return "석유제품 가격·정유업계 현안과 직접 연결 가능. 실제 발언·자료 확인 후 정책 리스크 점검 필요."

    if any(word in combined for word in ["산업", "에너지", "전력", "LNG", "가스", "수소", "ESS", "기후"]):
        return "에너지·산업 정책 관련 일정. 정유·석화·LNG 업계 영향은 구체 발언 및 후속 자료 확인 필요."

    if any(word in combined for word in ["국회", "위원회", "소위", "전체회의", "법안"]):
        return "국회 일정. 에너지 비용, 산업 지원, 석유제품 가격 관련 질의 시 업계 모니터링 필요."

    if any(word in combined for word in ["금리", "환율", "공급망", "재정", "경제", "비상경제"]):
        return "거시경제·공급망 관련 일정. 원유 도입비용, 환율, 물가 대응과의 간접 관련성 확인 필요."

    return DEFAULT_RELEVANCE


def normalize_context_org(value: str) -> str:
    value = clean_title(value)
    if not value:
        return "확인"
    if "대통령" in value:
        return "대통령"
    if "국무총리" in value or value == "총리":
        return "국무총리"
    aliases = {
        "공정거래위원회": "공정위",
        "기획재정부": "기재부",
        "재정경제부": "재경부",
        "기획예산처": "기획처",
        "기후에너지환경부": "기후부",
        "산업통상부": "산업부",
        "산업통상자원부": "산업부",
    }
    for k, v in aliases.items():
        if k in value:
            return v
    return value[:14]


def parse_schedule_items(body: str, max_items: int) -> List[Dict[str, str]]:
    lines = split_body_lines(body)
    items: List[Dict[str, str]] = []
    current_org = ""

    for line in lines:
        clean_line = normalize_line(line)
        if not clean_line:
            continue

        # 분야 헤더는 제외
        if re.fullmatch(r"\[.+\]", clean_line):
            continue

        # 세이프타임즈 원문은 '▲ 산업부' 다음 줄들에 일정이 이어지는 구조가 많다.
        # 이 문맥을 저장해야 '정치/경제/확인/제23회' 같은 잘못된 기관명이 줄어든다.
        if clean_line.startswith("▲"):
            current_org = normalize_context_org(clean_line)
            continue

        has_time = any(pattern.search(clean_line) for pattern in TIME_PATTERNS)
        has_org = any(keyword in clean_line for keyword in ORG_KEYWORDS)
        has_schedule_word = any(word in clean_line for word in ["회의", "간담회", "브리핑", "토론회", "방문", "행사", "면담", "발표", "공개", "점검"])
        if not (has_time or has_org or has_schedule_word):
            continue

        time_text, without_time = extract_time(clean_line)
        if current_org:
            org = current_org
            title = clean_line
        else:
            org, title = extract_org(without_time)

        title = clean_title(title)
        if not title or is_section_header_only(title):
            continue
        if len(title) > 110:
            title = title[:107] + "..."

        items.append({
            "time": time_text or "시간미정",
            "org": org or "확인",
            "title": title,
            "relevance": "",
        })

        if len(items) >= max_items:
            break

    # 중복 제거: 기관·표기가 달라도 같은 회의가 반복되는 경우가 많아 회의명 중심으로 제거
    def dedupe_key(item: Dict[str, str]) -> tuple[str, str]:
        title = re.sub(r"\s+", "", item.get("title", ""))
        title = re.sub(r"^(기획처|재정경제부|복지부|중기부|행안부|공정거래위원회|공정위|산업부|기후부|노동부|농식품부|대통령실|국무총리),?", "", title)
        title = re.sub(r"(참석|주재|개최|브리핑|모두발언|현장방문)$", "", title)
        if "민생물가" in title and "관계장관" in title and "TF" in title.upper():
            title = "민생물가특별관리관계장관TF"
        elif "국무회의" in title and "비상경제" in title:
            title = "국무회의겸비상경제점검회의"
        elif "국무회의" in title:
            title = "국무회의"
        elif "비상경제본부" in title and "경제관계장관회의" in title:
            title = "비상경제본부회의겸경제관계장관회의"
        elif "경제관계장관회의" in title:
            title = "경제관계장관회의"
        # 같은 회의가 여러 기관 일정에 중복 기재되는 경우 시간 차이가 있어도 1건만 노출
        no_time_topics = ("민생물가특별관리관계장관TF", "국무회의", "국무회의겸비상경제점검회의", "경제관계장관회의")
        if title in no_time_topics:
            return ("", title)
        return (item.get("time", ""), title[:70])

    seen = set()
    deduped = []
    for item in items:
        key = dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return sort_schedule_items(deduped)


def sort_schedule_items(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    def sort_key(item: Dict[str, str]) -> Tuple[int, str]:
        time_text = item.get("time", "")
        match = re.match(r"^(\d{2}):(\d{2})$", time_text)
        if match:
            return (int(match.group(1)) * 60 + int(match.group(2)), item.get("title", ""))
        if time_text == "현지":
            return (24 * 60 + 1, item.get("title", ""))
        return (24 * 60 + 2, item.get("title", ""))

    return sorted(items, key=sort_key)


def update_summary(
    base_report: Dict[str, Any],
    previous_items: List[Dict[str, str]],
    today_items: List[Dict[str, str]],
    target_dt: datetime,
    previous_label: str,
) -> None:
    # 중요: 주요 이해관계자 동향/이슈는 기준일 전일(또는 직전 영업일) 일정에서,
    # 금일 주요 일정은 기준일 일정에서 각각 만든다. 같은 데이터를 양쪽에 복사하지 않는다.
    if previous_items:
        previous_titles = ", ".join(item["title"] for item in previous_items[:3])
        stakeholder_text = f"주요 이해관계자 동향: {previous_label} 기준 {previous_titles}."
    else:
        stakeholder_text = f"주요 이해관계자 동향: {previous_label} 기준 관련 자료 찾지 못함."

    if today_items:
        today_titles = ", ".join(item["title"] for item in today_items[:4])
        today_text = f"금일 주요 일정: {today_titles}."
    else:
        today_text = "금일 주요 일정: 관련 자료 찾지 못함."

    news = base_report.get("news_trend", {}) if isinstance(base_report.get("news_trend"), dict) else {}
    articles = news.get("articles", []) if isinstance(news.get("articles"), list) else []
    valid_articles = [a for a in articles if isinstance(a, dict) and a.get("title") and a.get("url")]

    summary_rows = [
        {"type": "stakeholder", "text": stakeholder_text},
        {"type": "today", "text": today_text},
    ]
    # 조간 기사 후보가 실제로 있을 때만 Summary에 조간 보도 항목을 둔다.
    # 기사 0건인 날짜에는 '대표 기사 미확인'류 fallback 문구를 남기지 않는다.
    if valid_articles:
        news_titles = ", ".join(a.get("title", "") for a in valid_articles[:3])
        summary_rows.append({"type": "news_trend", "text": f"조간 보도: {news_titles}."})

    base_report["summary"] = summary_rows


def update_report_meta(base_report: Dict[str, Any], target_dt: datetime) -> None:
    report = base_report.setdefault("report", {})
    date_text = target_dt.strftime("%Y-%m-%d")

    report["report_date"] = date_text
    report["display_date"] = display_date(target_dt)
    report["previous_day_label"] = short_date_label(target_dt - timedelta(days=1))
    report["today_label"] = short_date_label(target_dt)
    report["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M KST")
    report["review_status"] = "초안"
    report["report_version"] = "draft-from-safetimes-v2.0"
    report["report_title"] = "Daily Issue Report"
    report["header_title"] = "Daily Issue Report"
    report["report_badge"] = report.get("report_badge") or "정유 · 석유화학 · LNG"


def update_sources(base_report: Dict[str, Any], schedule_data: Dict[str, Any]) -> None:
    quality = base_report.setdefault("quality_control", {})
    sources = quality.setdefault("sources", [])

    schedule_url = source_url(schedule_data)
    schedule_title = schedule_data.get("title", "오늘의 주요일정")

    # 기존 세이프타임즈 출처 제거 후 최신으로 추가
    sources = [
        source for source in sources
        if not (source.get("type") == "schedule")
    ]

    sources.insert(0, {
        "name": "오늘의 주요일정",
        "type": "schedule",
        "url": schedule_url,
    })

    quality["sources"] = sources

    notes = quality.setdefault("quality_notes", [])
    notes.append("일정은 자동 추출 결과이므로 시간·기관·일정명 확인 필요.")


def build_report_draft(
    schedule_data: Dict[str, Any],
    base_report: Dict[str, Any],
    target_dt: datetime,
    max_items: int,
    previous_schedule_data: Dict[str, Any] | None = None,
    previous_dt: datetime | None = None,
) -> Dict[str, Any]:
    report = copy.deepcopy(base_report)

    # report_sample.json은 특정 일자의 예시 콘텐츠를 담고 있을 수 있으므로
    # 날짜별 자동 생성 시에는 이전 날짜 Summary/이슈/기사 내용을 반드시 제거한다.
    report["summary"] = []
    report["issues"] = []
    report["schedules"] = []
    # 조간 기사는 apply_news_to_report.py에서 실제 기사 후보가 있을 때만 채운다.
    # 기사 0건인 경우 fallback 문구를 JSON에 남기지 않는다.
    report["news_trend"] = {"summary": "", "articles": []}

    today_items = schedule_items_from_json_or_body(schedule_data, max_items=max_items)
    previous_items: List[Dict[str, str]] = []
    if previous_schedule_data and previous_schedule_data.get("success", True):
        previous_items = schedule_items_from_json_or_body(previous_schedule_data, max_items=max_items)

    previous_label = short_date_label(previous_dt) if previous_dt else "전일"

    update_report_meta(report, target_dt)
    report.setdefault("report", {})["previous_day_label"] = previous_label
    report.setdefault("report", {})["previous_source_date"] = previous_dt.strftime("%Y-%m-%d") if previous_dt else ""

    # 금일 주요 일정은 기준일 일정만 사용한다.
    report["schedules"] = today_items

    # 주요 이해관계자 동향/이슈는 기준일 전일 또는 직전 영업일 일정만 사용한다.
    # 이 구분이 없으면 5/12처럼 기준일/전일 일정이 동일하게 노출된다.
    report["issues"] = build_issue_cards_from_schedules(previous_items)

    update_summary(report, previous_items, today_items, target_dt, previous_label)
    update_sources(report, schedule_data)

    # 자동화 이력 저장
    report.setdefault("automation", {})
    report["automation"]["safetimes"] = {
        "today_source_file_date": target_dt.strftime("%Y-%m-%d"),
        "today_source_title": schedule_data.get("title", ""),
        "today_source_url": source_url(schedule_data),
        "today_source_published_at": schedule_data.get("approved_date", "") or schedule_data.get("published_at", ""),
        "today_parsed_schedule_count": len(today_items),
        "previous_source_file_date": previous_dt.strftime("%Y-%m-%d") if previous_dt else "",
        "previous_source_title": previous_schedule_data.get("title", "") if previous_schedule_data else "",
        "previous_source_url": source_url(previous_schedule_data) if previous_schedule_data else "",
        "previous_parsed_schedule_count": len(previous_items),
        "parser_version": "build_report_draft_from_schedule.py v2.1-prevday-separated",
        "needs_review": True,
    }

    if not today_items:
        report.setdefault("automation", {}).setdefault("validation", {})["today_schedule_parse_failed"] = True
    if previous_schedule_data is None or not previous_items:
        report.setdefault("automation", {}).setdefault("validation", {})["previous_schedule_parse_failed"] = True

    return report


def main() -> int:
    args = parse_args()
    target_dt = parse_date(args.date)

    schedule_path = Path(args.schedule_dir) / f"{args.date}.json"
    base_report_path = Path(args.base_report)
    out_path = Path(args.out_dir) / f"{args.date}.report.json"

    previous_date_text = args.previous_date or (target_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    previous_dt = parse_date(previous_date_text)
    previous_schedule_dir = Path(args.previous_schedule_dir or args.schedule_dir)
    previous_schedule_path = previous_schedule_dir / f"{previous_date_text}.json"

    schedule_data = read_json(schedule_path)
    previous_schedule_data = read_json_optional(previous_schedule_path)
    base_report = read_json(base_report_path)

    if not schedule_data.get("success", True):
        raise DraftBuildError(f"세이프타임즈 수집 실패 JSON입니다: {schedule_path}")

    if previous_schedule_data is None:
        print(f"[WARN] 전일/직전 영업일 일정 JSON이 없습니다. 이슈 섹션은 비워 둡니다: {previous_schedule_path}")

    draft = build_report_draft(
        schedule_data=schedule_data,
        previous_schedule_data=previous_schedule_data,
        base_report=base_report,
        target_dt=target_dt,
        previous_dt=previous_dt,
        max_items=args.max_items,
    )

    write_json(out_path, draft)

    schedule_count = len(draft.get("schedules", []))
    print(f"[OK] 리포트 초안 생성 완료: {out_path}")
    issue_count = len(draft.get("issues", []))
    print(f"[OK] 금일 일정 반영 수: {schedule_count}")
    print(f"[OK] 전일/직전 영업일 이슈 반영 수: {issue_count}")
    print(f"[OK] 금일 원문 제목: {schedule_data.get('title', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
