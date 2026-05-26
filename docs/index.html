#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_news_candidates.py v2.0

정유·석유화학·LNG Daily Issue Report용 조간 기사 후보를 수집합니다.

운영 원칙
- 조간 기사 0건은 정상 상태가 아니라 수집 실패로 간주합니다.
- 0건이면 fallback 문구를 저장하고 통과시키지 않고, non-zero exit으로 workflow를 실패시킵니다.
- 기존에 정상 기사 JSON이 있으면 외부 RSS 일시 실패 시 기존 정상 JSON을 보존합니다.
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
from typing import Any, Dict, Iterable, List
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

KST = timezone(timedelta(hours=9))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

# 1차: 보고서 핵심 키워드. 2차/3차로 갈수록 넓게 잡되, 이후 점수/금지어 필터는 유지.
QUERY_TIERS = [
    (6, [
        "정유 OR 정유사 OR 유가 OR 원유 OR 석유제품 OR 주유소 OR 유류세 OR 휘발유 OR 경유",
        "석유화학 OR 나프타 OR 에틸렌 OR 프로필렌 OR 화학제품",
        "LNG OR 천연가스 OR 가스공사 OR 도시가스 OR 전력 OR 에너지 공급망",
        "최고가격제 OR 가격상한 OR 민생물가 OR 생산자물가 OR 석탄및석유제품",
        "중동 OR 호르무즈 OR 원유 수급 OR 에너지 안보 OR OPEC",
        "산업부 에너지 OR 기후에너지환경부 OR 공정위 석유 OR 국회 에너지",
    ]),
    (4, [
        "에너지 OR 유가 OR 석유 OR 물가 OR 전력 OR 가스",
        "산업부 OR 공정위 OR 기재부 OR 국회 OR 정부 에너지",
        "정유사 OR 주유소 OR 휘발유 OR 경유 OR 석유제품",
        "석유화학 OR 화학제품 OR 나프타 OR 배터리 OR 공급망",
    ]),
    (2, [
        "경제 에너지",
        "경제 유가",
        "산업 에너지",
        "물가 에너지",
        "정부 물가",
        "전력 가스",
    ]),
]

POSITIVE = {
    "정유":8,"정유사":9,"유가":8,"석유":8,"석유제품":9,"주유소":7,"유류세":7,"휘발유":7,"경유":7,"나프타":8,"항공유":6,
    "석유화학":9,"화학제품":5,"에틸렌":6,"프로필렌":6,"LNG":8,"천연가스":7,"가스":5,"전력":4,"원전":4,"에너지":5,
    "원유":8,"브렌트":6,"WTI":6,"두바이유":6,"OPEC":5,"중동":6,"호르무즈":8,"공급망":5,"수급":5,
    "물가":5,"생산자물가":7,"소비자물가":5,"최고가격제":10,"가격상한":8,"정부":2,"산업부":5,"기후부":4,"공정위":5,"국회":4,"기재부":4,
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
    ("정부·국회 에너지 정책", ["정부","산업부","기후부","공정위","국회","회의","브리핑"]),
]


def parse_args():
    p = argparse.ArgumentParser(description="조간 기사 후보 수집")
    p.add_argument("--date", required=True)
    p.add_argument("--out-dir", default="data/news")
    p.add_argument("--max-items", type=int, default=12)
    p.add_argument("--min-required", type=int, default=1, help="최소 필요 기사 수. 미달 시 실패")
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
    if any(k in text for k in ["정유", "석유", "유가", "LNG", "나프타", "주유소", "에너지"]):
        score += 4
    if any(k in text for k in ["정부", "국회", "산업부", "공정위", "기재부", "기후"]):
        score += 2
    return score


def fetch_google_news(query: str, target: datetime, min_score: int) -> list[dict[str, Any]]:
    after = target.strftime("%Y-%m-%d")
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
        out.append({
            "title": title,
            "press": source or "Google News",
            "url": link,
            "published_date": pub_date,
            "published_at_kst": pub_kst,
            "snippet": snippet,
            "score": score,
            "source_query": query,
        })
    return out


def is_same_day_morning(item: dict[str, Any], target_date: str) -> bool:
    pub = item.get("published_at_kst") or ""
    pub_date = item.get("published_date") or ""
    # Google RSS가 pubDate를 주지 않는 예외는 당일 검색어 after/before로 이미 제한됐으므로 후보 허용.
    if not pub and not pub_date:
        return True
    if pub_date and pub_date != target_date:
        return False
    if not pub:
        return pub_date == target_date
    if not pub.startswith(target_date):
        return False
    try:
        h, m = map(int, pub.split()[1].split(":"))
        return 0 <= h * 60 + m <= 11 * 60 + 30
    except Exception:
        return True


def dedupe(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for it in sorted(items, key=lambda x: int(x.get("score", 0)), reverse=True):
        title_key = re.sub(r"\s+", "", it.get("title", "").lower())[:90]
        domain = urlparse(it.get("url", "")).netloc.lower()
        key = (title_key, domain)
        if key in seen:
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
        return "주요 매체는 " + ", ".join(topics) + " 등을 중심으로 정유·석유화학·LNG 업계 관련 이슈를 다뤘습니다."
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

    for tier_idx, (min_score, queries) in enumerate(QUERY_TIERS, 1):
        for q in queries:
            try:
                collected.extend(fetch_google_news(q, target, min_score=min_score))
                time.sleep(0.2)
            except Exception as e:
                errors.append(f"tier{tier_idx} {q}: {e}")
        candidates = dedupe(collected)
        morning = [i for i in candidates if is_same_day_morning(i, a.date)]
        if len(morning) >= a.min_required:
            selected = morning[:a.max_items]
            used_tier = f"tier{tier_idx}"
            break

    if len(selected) < a.min_required:
        # 외부 RSS 일시 실패라면 기존 정상 데이터를 보존하고 통과. 없으면 실패시켜 잘못된 리포트 배포를 막음.
        if existing:
            print(f"[WARN] 새 뉴스 수집 실패. 기존 정상 뉴스 JSON 보존: {out_path} / articles={len(existing.get('articles', []))}")
            return 0
        payload = {
            "schema_version": "2.0",
            "date": a.date,
            "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
            "source": "Google News RSS",
            "queries": [q for _, qs in QUERY_TIERS for q in qs],
            "time_window": "00:00~11:30 KST",
            "summary": "",
            "topics": [],
            "articles": [],
            "errors": errors + [f"기사 후보 {len(selected)}건: 최소 {a.min_required}건 미달"],
            "success": False,
        }
        atomic_write_json(out_path, payload)
        print(f"[ERROR] 조간 기사 후보 수집 실패: {out_path} / articles=0")
        if errors:
            print("[ERROR]", " | ".join(errors[:5]))
        return 2

    topics = infer_topics(selected)
    payload = {
        "schema_version": "2.0",
        "date": a.date,
        "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
        "source": "Google News RSS",
        "queries": [q for _, qs in QUERY_TIERS for q in qs],
        "time_window": "00:00~11:30 KST",
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
        print("[WARN] 일부 검색 오류:", " | ".join(errors[:3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
