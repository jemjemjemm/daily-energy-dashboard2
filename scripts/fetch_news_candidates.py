#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_news_candidates.py v2.3

정유·석유화학·LNG Daily Issue Report용 조간 기사 후보를 수집합니다.

운영 원칙
- 조간 기사 0건은 정상 상태가 아니라 수집 실패입니다.
- 조간은 기준일 당일 00:00~오전 기사뿐 아니라 전일 저녁 온라인 선공개 기사를 포함할 수 있으므로
  기본 검색창은 전일 18:00 KST ~ 기준일 11:30 KST로 봅니다.
- News Trend 데이터는 Naver 뉴스 검색 HTML > Daum 뉴스 검색 HTML > Google News RSS 순서로 사용합니다.
- 0건이면 fallback 문구를 저장하고 통과시키지 않고, non-zero exit으로 workflow를 실패시킵니다.
- 기존에 정상 기사 JSON이 있으면 외부 검색 일시 실패 시 기존 정상 JSON을 보존합니다.
- 일정 공지·인사·부고·스포츠·연예성 기사는 제외합니다.
"""
from __future__ import annotations

import argparse
import email.utils
import html
import json
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover
    BeautifulSoup = None

KST = timezone(timedelta(hours=9))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

QUERY_TIERS: list[tuple[int, list[str]]] = [
    (5, [
        "국제유가 OR 유가 OR 원유 OR 브렌트유 OR WTI OR 두바이유",
        "정유 OR 정유사 OR 석유제품 OR 주유소 OR 유류세 OR 휘발유 OR 경유",
        "석유화학 OR 나프타 OR 에틸렌 OR 프로필렌 OR 화학제품",
        "LNG OR 천연가스 OR 가스공사 OR 도시가스 OR 전력 OR 전기요금",
        "최고가격제 OR 가격상한 OR 민생물가 OR 생산자물가 OR 석탄및석유제품",
        "중동 OR 호르무즈 OR 원유 수급 OR 에너지 안보 OR OPEC",
        "산업통상부 에너지 OR 산업부 석유 OR 공정위 석유 OR 국회 에너지",
    ]),
    (4, [
        "에너지 OR 유가 OR 석유 OR 물가 OR 전력 OR 가스",
        "산업부 OR 공정위 OR 기재부 OR 국회 OR 정부 에너지",
        "정유사 OR 주유소 OR 휘발유 OR 경유 OR 석유제품",
        "석유화학 OR 화학제품 OR 나프타 OR 배터리 OR 공급망",
        "생산자물가 OR 소비자물가 OR 수입물가 OR 에너지 가격",
    ]),
    (3, [
        "경제 에너지 OR 경제 유가 OR 산업 에너지",
        "물가 에너지 OR 정부 물가 OR 전력 가스",
        "산업부 OR 기재부 OR 공정위 OR 에너지",
        "석유 OR 가스 OR 전력 OR 화학",
    ]),
]

# 보조 검색원은 OR 구문보다 단일/복합 키워드가 안정적으로 동작합니다.
PLAIN_QUERIES = [
    "국제유가", "유가", "원유", "석유제품", "정유", "정유사", "주유소", "유류세", "휘발유", "경유",
    "석유화학", "나프타", "LNG", "천연가스", "전력", "에너지", "생산자물가", "민생물가", "최고가격제", "호르무즈",
]

KEYWORD_GROUPS = [
    (3, ["국제유가", "브렌트유", "두바이유", "WTI", "원유", "석유제품", "정유", "정유사", "석유화학", "나프타", "LNG", "천연가스", "호르무즈", "최고가격제"]),
    (2, ["유가", "석유", "주유소", "유류세", "휘발유", "경유", "에틸렌", "프로필렌", "가스", "전력", "전기요금", "공급망", "수급", "생산자물가", "가격상한"]),
    (1, ["에너지", "물가", "수입물가", "소비자물가", "정부", "산업부", "산업통상부", "기후부", "공정위", "국회", "기재부", "OPEC", "중동"]),
]
TITLE_IMPORTANCE_KEYWORDS = ["국제유가", "유가", "원유", "정유", "석유화학", "LNG", "나프타", "호르무즈", "최고가격제", "유류세"]
MARKET_ACTION_KEYWORDS = ["급등", "급락", "상승", "하락", "반등", "약세", "강세", "수급", "공급", "가격", "정책", "규제", "회의", "발표"]
ORIGINALITY_KEYWORDS = {
    "단독": 3, "속보": 2, "분석": 2, "전망": 2, "르포": 2, "인터뷰": 2,
    "해설": 1, "진단": 1, "업계": 1, "정부": 1, "자료": 1, "발표": 1,
}
LOW_QUALITY_KEYWORDS = {
    "오늘의 주요일정": 3, "주요일정": 3, "인사": 3, "부고": 3, "동정": 2, "특징주": 2,
    "야구": 3, "축구": 3, "농구": 3, "연예": 3, "맛집": 3, "여행": 3, "공연": 3, "전시": 3,
    "복권": 3, "로또": 3, "운세": 3, "날씨": 2,
}
TRUSTED_PRESS = {
    "연합뉴스", "한국경제", "매일경제", "서울경제", "이데일리", "머니투데이", "아시아경제", "파이낸셜뉴스",
    "중앙일보", "조선일보", "동아일보", "한겨레", "경향신문", "이투데이", "아시아투데이", "뉴스1", "뉴시스",
}
ECON_PRESS_HINTS = ["경제", "비즈", "투데이", "파이낸셜", "산업", "에너지", "석유", "화학"]
LOW_TRUST_PRESS_HINTS = ["블로그", "카페", "커뮤니티", "SNS", "유튜브"]
TOPIC_RULES = [
    ("석유 최고가격제·유류세 등 가격 안정 정책", ["최고가격제","유류세","가격상한","주유소","휘발유","경유"]),
    ("중동 정세와 원유·LNG 수급 리스크", ["중동","호르무즈","원유","LNG","가스","수급","공급망"]),
    ("정유·석유화학 업계 실적·원가·제품 가격", ["정유","정유사","석유화학","나프타","화학제품","원가"]),
    ("물가 지표와 에너지 비용 부담", ["물가","생산자물가","소비자물가","에너지","석유제품"]),
    ("정부·국회 에너지 정책", ["정부","산업부","산업통상부","기후부","공정위","국회","회의","브리핑"]),
]


def parse_args():
    p = argparse.ArgumentParser(description="조간 기사 후보 수집")
    p.add_argument("--date", required=True)
    p.add_argument("--out-dir", default="data/news")
    p.add_argument("--max-items", type=int, default=12)
    p.add_argument("--min-required", type=int, default=1, help="최소 필요 기사 수. 미달 시 실패")
    p.add_argument("--lookback-hours", type=int, default=18, help="전일 온라인 선공개 조간 기사 포함 범위")
    p.add_argument("--cutoff-hour", type=int, default=11)
    p.add_argument("--cutoff-minute", type=int, default=30)
    p.add_argument("--force-refresh", action="store_true")
    return p.parse_args()


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, prefix=f".{path.name}.", suffix=".tmp") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def clean_text(v: str) -> str:
    v = html.unescape(v or "")
    v = re.sub(r"<[^>]+>", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def normalize_press(value: str) -> str:
    press = clean_text(value)
    press = press.replace("언론사 선정", "").replace("네이버뉴스", "").replace("다음뉴스", "")
    press = re.sub(r"\s+", " ", press).strip(" -·|")
    return press or "출처 확인"


def original_url(link: str) -> str:
    try:
        qs = parse_qs(urlparse(link).query)
        if qs.get("url"):
            return unquote(qs["url"][0])
    except Exception:
        pass
    return link


def parse_pub_date(v: str) -> tuple[str, str]:
    if not v:
        return "", ""
    try:
        dt = email.utils.parsedate_to_datetime(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        k = dt.astimezone(KST)
        return k.strftime("%Y-%m-%d"), k.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "", ""


def keyword_score(title: str, snippet: str) -> int:
    text = f"{title} {snippet}".lower()
    raw = 0
    matched = set()
    for weight, keys in KEYWORD_GROUPS:
        for key in keys:
            if key.lower() in text and key not in matched:
                raw += weight
                matched.add(key)
    return min(5, raw)


def title_importance_score(title: str) -> int:
    score = 0
    if any(key.lower() in title.lower() for key in TITLE_IMPORTANCE_KEYWORDS):
        score += 2
    if any(key in title for key in MARKET_ACTION_KEYWORDS):
        score += 1
    if re.search(r"\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?\s*달러|최고|최저|급", title):
        score += 1
    return min(4, score)


def press_score(source: str) -> int:
    press = normalize_press(source)
    if press in TRUSTED_PRESS:
        return 3
    if any(hint in press for hint in ECON_PRESS_HINTS):
        return 1
    if any(hint.lower() in press.lower() for hint in LOW_TRUST_PRESS_HINTS):
        return -3
    if press in {"Google News", "Naver News", "Daum News", "출처 확인"}:
        return 0
    return 1


def originality_score(title: str, snippet: str) -> int:
    text = f"{title} {snippet}"
    return min(3, max((value for key, value in ORIGINALITY_KEYWORDS.items() if key in text), default=0))


def normalize_title_key(title: str, keep_press_suffix: bool = True) -> str:
    value = clean_text(title).lower()
    if not keep_press_suffix:
        value = re.sub(r"\s+-\s+[^-]{2,24}$", "", value).strip()
    value = re.sub(r"\[[^\]]+\]", " ", value)
    value = re.sub(r"\([^)]*\)", " ", value)
    return re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE)


def quality_penalty(title: str, snippet: str) -> int:
    text = f"{title} {snippet}"
    penalty = 0
    for key, value in LOW_QUALITY_KEYWORDS.items():
        if key in text:
            penalty = max(penalty, value)
    if len(clean_text(title)) < 8:
        penalty = max(penalty, 2)
    if len(clean_text(title)) > 120:
        penalty = max(penalty, 3)
    if normalize_title_key(title, keep_press_suffix=False) in {"", "뉴스", "경제"}:
        penalty = max(penalty, 3)
    return -min(3, penalty)


def score_article(title: str, snippet: str, source: str) -> tuple[int, dict[str, int]]:
    breakdown = {
        "keyword": keyword_score(title, snippet),
        "title_importance": title_importance_score(title),
        "press": press_score(source),
        "originality": originality_score(title, snippet),
        "duplicate_or_low_quality": quality_penalty(title, snippet),
    }
    return sum(breakdown.values()), breakdown


def in_morning_issue_window(item: dict[str, Any], target_date: str, lookback_hours: int, cutoff_hour: int, cutoff_minute: int) -> bool:
    target = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=KST)
    start = target - timedelta(hours=lookback_hours)
    end = target.replace(hour=cutoff_hour, minute=cutoff_minute, second=59)
    pub = item.get("published_at_kst") or ""
    pub_date = item.get("published_date") or ""
    if pub:
        try:
            dt = datetime.strptime(pub, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
            return start <= dt <= end
        except Exception:
            pass
    if pub_date:
        return pub_date in {start.strftime("%Y-%m-%d"), target.strftime("%Y-%m-%d")}
    # 보조 검색원에서 발행시각을 파싱하지 못한 경우, 검색 기간 조건으로 보정된 후보로 보고 허용합니다.
    return True


def fetch_google_news(query: str, target: datetime, min_score: int, lookback_hours: int) -> list[dict[str, Any]]:
    start = target - timedelta(hours=lookback_hours)
    after = start.strftime("%Y-%m-%d")
    before = (target + timedelta(days=1)).strftime("%Y-%m-%d")
    q = f"({query}) after:{after} before:{before}"
    url = "https://news.google.com/rss/search?q=" + quote_plus(q) + "&hl=ko&gl=KR&ceid=KR:ko"
    r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"}, timeout=25)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title", ""))
        link = original_url(clean_text(item.findtext("link", "")))
        pub_date, pub_kst = parse_pub_date(clean_text(item.findtext("pubDate", "")))
        source_node = item.find("source")
        source = normalize_press(source_node.text if source_node is not None and source_node.text else "")
        snippet = clean_text(item.findtext("description", ""))
        if not title or not link:
            continue
        score, score_breakdown = score_article(title, snippet, source)
        if score < min_score:
            continue
        out.append({"title": title, "press": source or "Google News", "url": link, "published_date": pub_date, "published_at_kst": pub_kst, "snippet": snippet, "score": score, "score_breakdown": score_breakdown, "source_query": query, "collector": "google_news_rss"})
    return out


def fetch_naver_news(query: str, target: datetime, min_score: int, lookback_hours: int) -> list[dict[str, Any]]:
    if BeautifulSoup is None:
        return []
    start = target - timedelta(hours=lookback_hours)
    ds = start.strftime("%Y.%m.%d")
    de = target.strftime("%Y.%m.%d")
    nso = f"so:r,p:from{start.strftime('%Y%m%d')}to{target.strftime('%Y%m%d')},a:all"
    url = (
        "https://search.naver.com/search.naver?where=news&sm=tab_opt&sort=1&photo=0&field=0&pd=3"
        f"&ds={quote_plus(ds)}&de={quote_plus(de)}&nso={quote_plus(nso)}&query={quote_plus(query)}"
    )
    r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"}, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out: list[dict[str, Any]] = []
    for a in soup.select("a.news_tit"):
        title = clean_text(a.get("title") or a.get_text(" "))
        link = clean_text(a.get("href") or "")
        parent = a.find_parent("li") or a.find_parent("div")
        snippet = clean_text(parent.get_text(" ") if parent else "")
        press = "Naver News"
        if parent:
            press_node = parent.select_one("a.info.press") or parent.select_one("span.info.press")
            if press_node:
                press = normalize_press(press_node.get_text(" ")) or press
        if not title or not link:
            continue
        score, score_breakdown = score_article(title, snippet, press)
        if score < min_score:
            continue
        out.append({"title": title, "press": normalize_press(press), "url": link, "published_date": target.strftime("%Y-%m-%d"), "published_at_kst": "", "snippet": snippet[:500], "score": score, "score_breakdown": score_breakdown, "source_query": query, "collector": "naver_news_search"})
    return out


def fetch_daum_news(query: str, target: datetime, min_score: int, lookback_hours: int) -> list[dict[str, Any]]:
    if BeautifulSoup is None:
        return []
    start = target - timedelta(hours=lookback_hours)
    sd = start.strftime("%Y%m%d%H%M%S")
    ed = target.replace(hour=23, minute=59, second=59).strftime("%Y%m%d%H%M%S")
    url = f"https://search.daum.net/search?w=news&q={quote_plus(query)}&period=u&sd={sd}&ed={ed}&sort=recency"
    r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"}, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out: list[dict[str, Any]] = []
    anchors = soup.select("a.tit_main, a.f_link_b, .item-title a, a[href*='news.v.daum.net'], a[href*='v.daum.net']")
    for a in anchors:
        title = clean_text(a.get("title") or a.get_text(" "))
        link = clean_text(a.get("href") or "")
        if not title or not link or len(title) < 6 or len(title) > 120:
            continue
        parent = a.find_parent("li") or a.find_parent("div")
        snippet = clean_text(parent.get_text(" ") if parent else "")
        press = "Daum News"
        score, score_breakdown = score_article(title, snippet, press)
        if score < min_score:
            continue
        out.append({"title": title, "press": press, "url": link, "published_date": target.strftime("%Y-%m-%d"), "published_at_kst": "", "snippet": snippet[:500], "score": score, "score_breakdown": score_breakdown, "source_query": query, "collector": "daum_news_search"})
    return out


def similar_title(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    a_tokens = {a[i:i + 2] for i in range(max(0, len(a) - 1))}
    b_tokens = {b[i:i + 2] for i in range(max(0, len(b) - 1))}
    if not a_tokens or not b_tokens:
        return False
    return len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens)) >= 0.72


def dedupe(items: Iterable[dict[str, Any]], min_keep: int = 0) -> list[dict[str, Any]]:
    seen = set()
    seen_urls = set()
    exact_out = []
    for it in sorted(items, key=lambda x: int(x.get("score", 0)), reverse=True):
        title_key = normalize_title_key(it.get("title", ""), keep_press_suffix=True)[:90]
        domain = urlparse(it.get("url", "")).netloc.lower()
        url_key = clean_text(it.get("url", "")).split("#", 1)[0]
        key = (title_key, domain)
        if not title_key or key in seen or (url_key and url_key in seen_urls):
            continue
        seen.add(key)
        if url_key:
            seen_urls.add(url_key)
        exact_out.append(it)

    clustered: list[dict[str, Any]] = []
    cluster_keys: list[str] = []
    for it in exact_out:
        title_key = normalize_title_key(it.get("title", ""), keep_press_suffix=False)[:90]
        if any(similar_title(title_key, existing) for existing in cluster_keys):
            continue
        cluster_keys.append(title_key)
        clustered.append(it)

    return clustered if len(clustered) >= min_keep else exact_out


def infer_topics(items: list[dict[str, Any]]) -> list[str]:
    text = " ".join(f"{i.get('title','')} {i.get('snippet','')}" for i in items)
    topics = []
    for label, keys in TOPIC_RULES:
        if any(k in text for k in keys):
            topics.append(label)
    return topics[:4]


def build_summary(topics: list[str], items: list[dict[str, Any]]) -> str:
    if topics:
        return "주요 매체가 " + " ".join(f"△{t}" for t in topics[:4]) + " 등을 중심으로 보도."
    titles = ", ".join(i.get("title", "") for i in items[:3])
    return f"정유·석유화학·LNG 관련 조간 기사 후보로 {titles} 등 수집."


def read_existing_valid(
    path: Path,
    target_date: str,
    lookback_hours: int,
    cutoff_hour: int,
    cutoff_minute: int,
) -> dict[str, Any] | None:
    """기존 뉴스 JSON도 기준일 조간 시간창을 통과한 기사만 유효로 본다.

    과거 백필에서 잘못 저장된 오후 기사·익일 기사가 계속 재사용되는 것을 막기 위한
    최종 방어선입니다. published_at_kst가 있는 기사는 시간창을 엄격히 검증하고,
    시간이 없더라도 published_date가 전일/기준일 범위를 벗어나면 폐기합니다.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    arts = data.get("articles", []) if isinstance(data.get("articles"), list) else []
    valid = [
        a for a in arts
        if isinstance(a, dict)
        and a.get("title")
        and a.get("url")
        and in_morning_issue_window(a, target_date, lookback_hours, cutoff_hour, cutoff_minute)
    ]
    if valid:
        data["articles"] = valid
        return data
    return None


def main() -> int:
    a = parse_args()
    target = datetime.strptime(a.date, "%Y-%m-%d").replace(tzinfo=KST)
    out_path = Path(a.out_dir) / f"{a.date}.json"

    existing = read_existing_valid(out_path, a.date, a.lookback_hours, a.cutoff_hour, a.cutoff_minute) if out_path.exists() else None
    if existing and not a.force_refresh:
        print(f"[OK] 기존 정상 뉴스 후보 JSON 재사용: {out_path} / articles={len(existing.get('articles', []))}")
        return 0

    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    selected: list[dict[str, Any]] = []
    used_tier = ""

    # 1) Naver 뉴스 검색 HTML
    for q in PLAIN_QUERIES:
        try:
            collected.extend(fetch_naver_news(q, target, min_score=4, lookback_hours=a.lookback_hours))
            time.sleep(0.2)
        except Exception as e:
            errors.append(f"naver {q}: {e}")
    candidates = dedupe(collected, min_keep=a.min_required)
    windowed = [i for i in candidates if in_morning_issue_window(i, a.date, a.lookback_hours, a.cutoff_hour, a.cutoff_minute)]
    if len(windowed) >= a.min_required:
        selected = windowed[:a.max_items]
        used_tier = "naver_html"

    # 2) Daum 뉴스 검색 HTML
    if len(selected) < a.min_required:
        for q in PLAIN_QUERIES:
            try:
                collected.extend(fetch_daum_news(q, target, min_score=4, lookback_hours=a.lookback_hours))
                time.sleep(0.2)
            except Exception as e:
                errors.append(f"daum {q}: {e}")
        candidates = dedupe(collected, min_keep=a.min_required)
        windowed = [i for i in candidates if in_morning_issue_window(i, a.date, a.lookback_hours, a.cutoff_hour, a.cutoff_minute)]
        if len(windowed) >= a.min_required:
            selected = windowed[:a.max_items]
            used_tier = "daum_html"

    # 3) Google News RSS
    if len(selected) < a.min_required:
        for tier_idx, (min_score, queries) in enumerate(QUERY_TIERS, 1):
            for q in queries:
                try:
                    collected.extend(fetch_google_news(q, target, min_score=min_score, lookback_hours=a.lookback_hours))
                    time.sleep(0.15)
                except Exception as e:
                    errors.append(f"google tier{tier_idx} {q}: {e}")
            candidates = dedupe(collected, min_keep=a.min_required)
            windowed = [i for i in candidates if in_morning_issue_window(i, a.date, a.lookback_hours, a.cutoff_hour, a.cutoff_minute)]
            if len(windowed) >= a.min_required:
                selected = windowed[:a.max_items]
                used_tier = f"google_tier{tier_idx}"
                break

    # 4) Threshold fallback: keep the same source order, but relax score filters
    # so a transiently sparse search result does not become a zero-article report.
    if len(selected) < a.min_required:
        relaxed: list[dict[str, Any]] = []
        for collector_name, fn in [("naver", fetch_naver_news), ("daum", fetch_daum_news)]:
            for q in PLAIN_QUERIES:
                try:
                    relaxed.extend(fn(q, target, min_score=2, lookback_hours=a.lookback_hours))
                    time.sleep(0.15)
                except Exception as e:
                    errors.append(f"{collector_name} relaxed {q}: {e}")
            candidates = dedupe(relaxed, min_keep=a.min_required)
            windowed = [i for i in candidates if in_morning_issue_window(i, a.date, a.lookback_hours, a.cutoff_hour, a.cutoff_minute)]
            if len(windowed) >= a.min_required:
                selected = windowed[:a.max_items]
                used_tier = f"{collector_name}_html_relaxed"
                break
        if len(selected) < a.min_required:
            for _tier_idx, (_min_score, queries) in enumerate(QUERY_TIERS, 1):
                for q in queries:
                    try:
                        relaxed.extend(fetch_google_news(q, target, min_score=2, lookback_hours=a.lookback_hours))
                        time.sleep(0.1)
                    except Exception as e:
                        errors.append(f"google relaxed {_tier_idx} {q}: {e}")
                candidates = dedupe(relaxed, min_keep=a.min_required)
                windowed = [i for i in candidates if in_morning_issue_window(i, a.date, a.lookback_hours, a.cutoff_hour, a.cutoff_minute)]
                if len(windowed) >= a.min_required:
                    selected = windowed[:a.max_items]
                    used_tier = f"google_tier{_tier_idx}_relaxed"
                    break

    if len(selected) < a.min_required:
        if existing and not a.force_refresh:
            print(f"[WARN] 새 뉴스 수집 실패. 기존 시간창 통과 뉴스 JSON 보존: {out_path} / articles={len(existing.get('articles', []))}")
            return 0
        payload = {
            "schema_version": "2.3",
            "date": a.date,
            "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
            "source": "Naver News Search HTML + Daum News Search HTML + Google News RSS",
            "queries": [q for _, qs in QUERY_TIERS for q in qs] + PLAIN_QUERIES,
            "time_window": f"전일 {24 - a.lookback_hours:02d}:00~기준일 {a.cutoff_hour:02d}:{a.cutoff_minute:02d} KST",
            "summary": "",
            "topics": [],
            "articles": [],
            "errors": errors + [f"기사 후보 {len(selected)}건: 최소 {a.min_required}건 미달"],
            "success": False,
        }
        atomic_write_json(out_path, payload)
        print(f"[ERROR] 조간 기사 후보 수집 실패: {out_path} / articles=0")
        if errors:
            print("[ERROR]", " | ".join(errors[:8]))
        return 2

    topics = infer_topics(selected)
    payload = {
        "schema_version": "2.3",
        "date": a.date,
        "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
        "source": "Naver News Search HTML + Daum News Search HTML + Google News RSS",
        "queries": [q for _, qs in QUERY_TIERS for q in qs] + PLAIN_QUERIES,
        "time_window": f"전일 {24 - a.lookback_hours:02d}:00~기준일 {a.cutoff_hour:02d}:{a.cutoff_minute:02d} KST",
        "summary": build_summary(topics, selected),
        "topics": topics,
        "articles": selected,
        "errors": errors,
        "success": True,
        "used_tier": used_tier,
    }
    atomic_write_json(out_path, payload)
    print(f"[OK] 뉴스 후보 저장 완료: {out_path} / articles={len(selected)} / {used_tier}")
    if errors:
        print("[WARN] 일부 검색 오류:", " | ".join(errors[:5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
