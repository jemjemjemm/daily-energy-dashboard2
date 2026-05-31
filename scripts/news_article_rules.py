#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared press and relevance rules for News Trend article candidates."""

from __future__ import annotations

import html
import re
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse, urlunparse

PORTAL_PRESS_NAMES = {"Daum News", "Naver News", "Google News", "출처 확인", ""}

A_GRADE_PRESS = {
    "연합뉴스", "한국경제", "매일경제", "서울경제", "이데일리", "머니투데이", "아시아경제", "파이낸셜뉴스",
    "중앙일보", "조선일보", "동아일보", "한겨레", "경향신문", "한국일보", "뉴스1", "뉴시스",
}
B_GRADE_PRESS = {
    "국민일보", "문화일보", "세계일보", "헤럴드경제", "이투데이", "아시아투데이", "전자신문", "비즈워치",
    "조세일보", "데일리안", "한스경제", "더구루", "신아일보", "국제신문", "에너지경제", "매일일보",
    "SBS", "KBS", "MBC", "YTN", "JTBC", "MBN", "채널A", "TV조선",
}

DOMAIN_PRESS = {
    "yna.co.kr": "연합뉴스",
    "hankyung.com": "한국경제",
    "mk.co.kr": "매일경제",
    "sedaily.com": "서울경제",
    "edaily.co.kr": "이데일리",
    "mt.co.kr": "머니투데이",
    "asiae.co.kr": "아시아경제",
    "fnnews.com": "파이낸셜뉴스",
    "joongang.co.kr": "중앙일보",
    "chosun.com": "조선일보",
    "donga.com": "동아일보",
    "hani.co.kr": "한겨레",
    "khan.co.kr": "경향신문",
    "hankookilbo.com": "한국일보",
    "news1.kr": "뉴스1",
    "newsis.com": "뉴시스",
    "heraldcorp.com": "헤럴드경제",
    "etoday.co.kr": "이투데이",
    "asiatoday.co.kr": "아시아투데이",
    "etnews.com": "전자신문",
    "bizwatch.co.kr": "비즈워치",
    "dailian.co.kr": "데일리안",
    "hansbiz.co.kr": "한스경제",
    "theguru.co.kr": "더구루",
    "shinailbo.co.kr": "신아일보",
    "kookje.co.kr": "국제신문",
    "ekn.kr": "에너지경제",
    "segye.com": "세계일보",
}

DIRECT_INDUSTRY_KEYWORDS = {
    "국제유가", "브렌트유", "두바이유", "WTI", "원유", "정유", "정유사", "석유제품", "석유화학", "나프타",
    "에틸렌", "프로필렌", "LNG", "천연가스", "유류세", "호르무즈", "휘발유", "경유", "주유소",
    "최고가격제", "가격상한", "정제마진", "석탄및석유제품",
}
BROAD_ONLY_KEYWORDS = {"에너지", "전력", "물가"}


def clean_text(value: Any) -> str:
    text = html.unescape("" if value is None else str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_press(value: Any) -> str:
    press = clean_text(value)
    press = re.sub(r"\s*언론사\s*(?:픽|선정)\s*", " ", press)
    press = re.sub(r"\s+", " ", press).strip(" -·|")
    aliases = {
        "다음뉴스": "Daum News",
        "네이버뉴스": "Naver News",
        "구글뉴스": "Google News",
    }
    return aliases.get(press.replace(" ", ""), press) or "출처 확인"


def is_forbidden_press(value: Any) -> bool:
    press = normalize_press(value)
    return press in PORTAL_PRESS_NAMES or "News Search" in press or "Google News RSS" in press


def infer_press_from_url(url: Any) -> str:
    hostname = (urlparse(clean_text(url)).hostname or "").lower()
    hostname = hostname.removeprefix("www.")
    for domain, press in DOMAIN_PRESS.items():
        if hostname == domain or hostname.endswith("." + domain):
            return press
    return ""


def infer_press_from_title(title: Any) -> str:
    match = re.search(r"\s+-\s+([^-]{2,24})\s*$", clean_text(title))
    return normalize_press(match.group(1)) if match else ""


def infer_press_from_snippet(snippet: Any) -> str:
    text = clean_text(snippet)
    match = re.match(
        r"^(.{2,30}?)(?:\s+언론사\s*픽)?\s+(?:개별문서메뉴|톡으로\s+바로\s+공유|공유하기)\b",
        text,
    )
    if not match:
        return ""
    press = normalize_press(match.group(1))
    if is_forbidden_press(press) or re.search(r"\d{1,2}\s*(?:시간|분)\s*전", press):
        return ""
    return press


def resolve_press(item: Mapping[str, Any], selector_press: Any = "") -> str:
    candidates = [
        selector_press,
        item.get("press"),
        item.get("source"),
        infer_press_from_url(item.get("url")),
        infer_press_from_title(item.get("title")),
        infer_press_from_snippet(item.get("snippet") or item.get("summary")),
    ]
    for candidate in candidates:
        press = normalize_press(candidate)
        if not is_forbidden_press(press):
            return press
    return "출처 확인"


def normalize_article_url(link: Any) -> str:
    url = clean_text(link)
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        for key in ("url", "redirect", "redirect_url", "target"):
            if query.get(key):
                candidate = unquote(query[key][0])
                if candidate.startswith(("http://", "https://")):
                    return candidate
        if parsed.hostname in {"v.daum.net", "news.v.daum.net"} and parsed.scheme == "http":
            return urlunparse(parsed._replace(scheme="https"))
    except Exception:
        return url
    return url


def press_grade(value: Any) -> str:
    press = normalize_press(value)
    if is_forbidden_press(press):
        return "X"
    if press in A_GRADE_PRESS:
        return "A"
    if press in B_GRADE_PRESS:
        return "B"
    return "C"


def industry_relevance_score(title: Any, snippet: Any = "") -> int:
    title_text = clean_text(title).lower()
    body_text = clean_text(snippet).lower()
    title_matches = {key for key in DIRECT_INDUSTRY_KEYWORDS if key.lower() in title_text}
    body_matches = {key for key in DIRECT_INDUSTRY_KEYWORDS if key.lower() in body_text}
    if title_matches:
        return min(5, 3 + len(title_matches))
    if body_matches:
        return min(3, len(body_matches))
    if any(key in title_text or key in body_text for key in BROAD_ONLY_KEYWORDS):
        return 0
    return -1


def is_original_source_url(url: Any) -> bool:
    hostname = (urlparse(clean_text(url)).hostname or "").lower()
    return hostname not in {"v.daum.net", "news.v.daum.net", "news.naver.com", "news.google.com"}
