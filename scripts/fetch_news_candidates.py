#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_news_candidates.py v2.3

정유·석유화학·LNG Daily Issue Report용 조간 기사 후보를 수집합니다.

운영 원칙
- 조간 기사 0건은 정상 상태가 아니라 수집 실패입니다.
- 조간은 기준일 당일 00:00~오전 기사뿐 아니라 전일 저녁 온라인 선공개 기사를 포함할 수 있으므로
  기본 검색창은 전일 18:00 KST ~ 기준일 11:30 KST로 봅니다.
- Google News RSS만 의존하지 않고, Naver/Daum 뉴스 검색 HTML도 보조 수집원으로 사용합니다.
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
    (6, [
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
    (2, [
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

POSITIVE = {
    "정유":8,"정유사":9,"유가":8,"국제유가":10,"석유":8,"석유제품":9,"주유소":7,"유류세":7,"휘발유":7,"경유":7,"나프타":8,"항공유":6,
    "석유화학":9,"화학제품":5,"에틸렌":6,"프로필렌":6,"LNG":8,"천연가스":7,"가스":5,"전력":4,"전기요금":6,"원전":4,"에너지":5,
    "원유":8,"브렌트":6,"브렌트유":7,"WTI":6,"두바이유":6,"OPEC":5,"중동":6,"호르무즈":8,"공급망":5,"수급":5,
    "물가":5,"생산자물가":7,"소비자물가":5,"수입물가":5,"최고가격제":10,"가격상한":8,"정부":2,"산업부":5,"산업통상부":5,"기후부":4,"공정위":5,"국회":4,"기재부":4,
    "SK이노베이션":6,"SK에너지":6,"GS칼텍스":6,"에쓰오일":6,"S-OIL":6,"현대오일뱅크":6,"HD현대오일뱅크":6,
}
NEGATIVE = {
    "오늘의 주요일정":80,"주요일정":70,"인사":25,"부고":25,"동정":18,"특징주":12,
    "야구":20,"축구":20,"농구":20,"연예":20,"맛집":15,"여행":15,"공연":15,"전시":15,
    "복권":20,"로또":20,"운세":20,"날씨":10,
}
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


def score_article(title: str, snippet: str, source: str) -> int:
    text = f"{title} {snippet} {source}"
    low = text.lower()
    score = sum(w for k, w in POSITIVE.items() if k.lower() in low)
    score -= sum(w for k, w in NEGATIVE.items() if k.lower() in low)
    if any(k in text for k in ["정유", "석유", "유가", "원유", "LNG", "나프타", "주유소", "에너지", "물가"]):
        score += 4
    if any(k in text for k in ["정부", "국회", "산업부", "산업통상부", "공정위", "기재부", "기후"]):
        score += 2
    return score


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
        source = clean_text(source_node.text if source_node is not None and source_node.text else "")
        snippet = clean_text(item.findtext("description", ""))
        if not title or not link:
            continue
        score = score_article(title, snippet, source)
        if score < min_score:
            continue
        out.append({"title": title, "press": source or "Google News", "url": link, "published_date": pub_date, "published_at_kst": pub_kst, "snippet": snippet, "score": score, "source_query": query, "collector": "google_news_rss"})
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
                press = clean_text(press_node.get_text(" ")).replace("언론사 선정", "").strip() or press
        if not title or not link:
            continue
        score = score_article(title, snippet, press)
        if score < min_score:
            continue
        out.append({"title": title, "press": press, "url": link, "published_date": target.strftime("%Y-%m-%d"), "published_at_kst": "", "snippet": snippet[:500], "score": score, "source_query": query, "collector": "naver_news_search"})
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
        if not title or not link or len(title) < 6:
            continue
        parent = a.find_parent("li") or a.find_parent("div")
        snippet = clean_text(parent.get_text(" ") if parent else "")
        press = "Daum News"
        score = score_article(title, snippet, press)
        if score < min_score:
            continue
        out.append({"title": title, "press": press, "url": link, "published_date": target.strftime("%Y-%m-%d"), "published_at_kst": "", "snippet": snippet[:500], "score": score, "source_query": query, "collector": "daum_news_search"})
    return out


def dedupe(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for it in sorted(items, key=lambda x: int(x.get("score", 0)), reverse=True):
        title_key = re.sub(r"\s+", "", it.get("title", "").lower())[:90]
        domain = urlparse(it.get("url", "")).netloc.lower()
        key = (title_key, domain)
        if not title_key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def infer_topics(items: list[dict[str, Any]]) -> list[str]:
    text = " ".join(f"{i.get('title','')} {i.get('snippet','')}" for i in items)
    topics = []
    for label, keys in TOPIC_RULES:
        if any(k in text for k in keys):
            topics.append(label)
    return topics[:4]


def build_summary(topics: list[str], items: list[dict[str, Any]]) -> str:
    if topics:
        return "주요 매체는 " + ", ".join(topics[:4]) + " 등을 중심으로 정유·석유화학·LNG 업계 관련 이슈를 다뤘습니다."
    titles = ", ".join(i.get("title", "") for i in items[:3])
    return f"정유·석유화학·LNG 관련 조간 기사 후보로 {titles} 등이 수집됐습니다."


def read_existing_valid(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    arts = data.get("articles", []) if isinstance(data.get("articles"), list) else []
    valid = [a for a in arts if isinstance(a, dict) and a.get("title") and a.get("url")]
    if valid:
        data["articles"] = valid
        return data
    return None


def main() -> int:
    a = parse_args()
    target = datetime.strptime(a.date, "%Y-%m-%d").replace(tzinfo=KST)
    out_path = Path(a.out_dir) / f"{a.date}.json"

    existing = read_existing_valid(out_path) if out_path.exists() else None
    if existing and not a.force_refresh:
        print(f"[OK] 기존 정상 뉴스 후보 JSON 재사용: {out_path} / articles={len(existing.get('articles', []))}")
        return 0

    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    selected: list[dict[str, Any]] = []
    used_tier = ""

    # 1) Google RSS: 가장 안정적인 구조화 소스
    for tier_idx, (min_score, queries) in enumerate(QUERY_TIERS, 1):
        for q in queries:
            try:
                collected.extend(fetch_google_news(q, target, min_score=min_score, lookback_hours=a.lookback_hours))
                time.sleep(0.15)
            except Exception as e:
                errors.append(f"google tier{tier_idx} {q}: {e}")
        candidates = dedupe(collected)
        windowed = [i for i in candidates if in_morning_issue_window(i, a.date, a.lookback_hours, a.cutoff_hour, a.cutoff_minute)]
        if len(windowed) >= a.min_required:
            selected = windowed[:a.max_items]
            used_tier = f"google_tier{tier_idx}"
            break

    # 2) 보조 수집원: Google RSS가 0건일 때만 사용
    if len(selected) < a.min_required:
        for collector_name, fn in [("naver", fetch_naver_news), ("daum", fetch_daum_news)]:
            for q in PLAIN_QUERIES:
                try:
                    collected.extend(fn(q, target, min_score=2, lookback_hours=a.lookback_hours))
                    time.sleep(0.2)
                except Exception as e:
                    errors.append(f"{collector_name} {q}: {e}")
            candidates = dedupe(collected)
            windowed = [i for i in candidates if in_morning_issue_window(i, a.date, a.lookback_hours, a.cutoff_hour, a.cutoff_minute)]
            if len(windowed) >= a.min_required:
                selected = windowed[:a.max_items]
                used_tier = f"{collector_name}_fallback"
                break

    if len(selected) < a.min_required:
        if existing:
            print(f"[WARN] 새 뉴스 수집 실패. 기존 정상 뉴스 JSON 보존: {out_path} / articles={len(existing.get('articles', []))}")
            return 0
        payload = {
            "schema_version": "2.3",
            "date": a.date,
            "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
            "source": "Google News RSS + Naver/Daum News Search",
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
        "source": "Google News RSS + Naver/Daum News Search",
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
