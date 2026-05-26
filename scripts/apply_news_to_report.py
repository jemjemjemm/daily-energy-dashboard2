#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""뉴스 후보 JSON을 리포트 JSON의 조간 신문 트렌드와 Summary에 반영합니다.

운영 원칙
- 기사 후보 0건은 정상 상태가 아니라 수집 실패입니다.
- 0건일 때 fallback 문구를 넣거나 섹션을 숨기지 않고, non-zero exit으로 pipeline을 실패시킵니다.
- 기존 report.json에 정상 기사 1건 이상이 있으면 외부 수집 일시 실패 시 기존 기사를 보존합니다.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List

BAD_TITLES = ["오늘의 주요일정", "주요일정", "대표 기사 데이터 없음", "자동 수집 미적용", "대표 기사 미확인"]
BAD_SUMMARY_PHRASES = [
    "자동 수집된 대표 기사 없음", "가격 데이터 중심", "원문 데이터", "fallback",
    "찾지 못했습니다", "미확인", "주요 보도 없음", "대표 기사 없음",
]
PRICE_SUMMARY_RE = re.compile(r"\s*가격 그래프는 기준일 전일 기준 과거 2개월\([^)]*\)만 표시하며, 값이 0인 가격은 제외\.?,?", re.U)


def parse_args():
    p = argparse.ArgumentParser(description="뉴스 후보를 리포트 JSON에 반영")
    p.add_argument("--date", required=True)
    p.add_argument("--report-dir", default="data/reports")
    p.add_argument("--news-dir", default="data/news")
    p.add_argument("--max-articles", type=int, default=3)
    p.add_argument("--min-required", type=int, default=1)
    return p.parse_args()


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, prefix=f".{path.name}.", suffix=".tmp") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def clean(v: Any) -> str:
    return re.sub(r"\s+", " ", "" if v is None else str(v)).strip()


def valid_article(item: Dict[str, Any]) -> bool:
    title = clean(item.get("title"))
    url = clean(item.get("url"))
    if not title or not url:
        return False
    if any(b in title for b in BAD_TITLES):
        return False
    if any(b in url for b in ["safetimes.co.kr/news/articleView"]):
        return False
    return True


def normalize_article(item: Dict[str, Any]) -> Dict[str, str]:
    title = clean(item.get("title"))
    snippet = clean(item.get("summary") or item.get("snippet"))
    if snippet:
        snippet = re.sub(r" - [^ ]+(?:\s|$)", " ", snippet)
        snippet = re.sub(r"\s+", " ", snippet).strip()
        summary = snippet[:147] + "..." if len(snippet) > 150 else snippet
    else:
        summary = "원문 링크 기준으로 세부 내용 검수가 필요합니다."
    return {
        "title": title,
        "press": clean(item.get("press") or item.get("source")) or "Google News",
        "url": clean(item.get("url")),
        "summary": summary,
        "published_at_kst": clean(item.get("published_at_kst")),
    }


def existing_valid_articles(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    news = report.get("news_trend", {}) if isinstance(report.get("news_trend"), dict) else {}
    articles = news.get("articles", []) if isinstance(news.get("articles"), list) else []
    return [a for a in articles if isinstance(a, dict) and valid_article(a)]


def build_news_summary(news: Dict[str, Any], articles: List[Dict[str, Any]]) -> str:
    topics = [clean(t) for t in news.get("topics", []) if clean(t)]
    if topics:
        return "주요 매체는 " + ", ".join(topics[:4]) + " 등을 중심으로 정유·석유화학·LNG 업계 관련 이슈를 다뤘습니다."
    provided = clean(news.get("summary"))
    if provided and not any(x in provided for x in BAD_SUMMARY_PHRASES):
        return provided
    titles = ", ".join(a.get("title", "") for a in articles[:3])
    return f"정유·석유화학·LNG 관련 조간 기사 후보로 {titles} 등이 수집됐습니다."


def update_summary(report: Dict[str, Any], news_summary: str) -> None:
    existing = report.get("summary", []) if isinstance(report.get("summary"), list) else []
    cleaned = []
    for item in existing:
        if not isinstance(item, dict) or item.get("type") == "news_trend":
            continue
        text = PRICE_SUMMARY_RE.sub("", clean(item.get("text"))).strip()
        if not text:
            continue
        if any(x in text for x in BAD_SUMMARY_PHRASES):
            continue
        item = dict(item)
        item["text"] = text
        cleaned.append(item)
    while len(cleaned) < 2:
        typ = "stakeholder" if len(cleaned) == 0 else "today"
        label = "주요 이해관계자 동향" if typ == "stakeholder" else "금일 주요 일정"
        cleaned.append({"type": typ, "text": f"{label}: 관련 자료 검수 필요."})
    cleaned = cleaned[:2]
    cleaned.append({"type": "news_trend", "text": "조간 보도: " + news_summary})
    report["summary"] = cleaned


def main() -> int:
    a = parse_args()
    report_path = Path(a.report_dir) / f"{a.date}.report.json"
    news_path = Path(a.news_dir) / f"{a.date}.json"
    report = read_json(report_path)
    if not report:
        print(f"[ERROR] 리포트 JSON이 없습니다: {report_path}")
        return 1

    news = read_json(news_path)
    raw_articles = news.get("articles", []) if isinstance(news.get("articles"), list) else []
    new_articles = [normalize_article(i) for i in raw_articles if isinstance(i, dict) and valid_article(i)][:a.max_articles]
    old_articles = [normalize_article(i) for i in existing_valid_articles(report)][:a.max_articles]

    if new_articles:
        articles = new_articles
        news_summary = build_news_summary(news, articles)
        source = "Google News RSS"
        status = "updated"
    elif old_articles:
        articles = old_articles
        old_news = report.get("news_trend", {}) if isinstance(report.get("news_trend"), dict) else {}
        old_summary = clean(old_news.get("summary"))
        news_summary = old_summary if old_summary and not any(p in old_summary for p in BAD_SUMMARY_PHRASES) else build_news_summary({}, articles)
        source = clean(old_news.get("source")) or "existing report"
        status = "preserved_existing"
    else:
        print(f"[ERROR] 조간 기사 후보 0건: {news_path}. fallback 문구를 넣지 않고 workflow를 실패시킵니다.")
        return 2

    if len(articles) < a.min_required:
        print(f"[ERROR] 조간 기사 후보 {len(articles)}건: 최소 {a.min_required}건 미달")
        return 2

    report["news_trend"] = {"summary": news_summary, "articles": articles, "source": source, "needs_review": True}
    update_summary(report, news_summary)
    report.setdefault("automation", {})["news"] = {
        "source_file": str(news_path),
        "article_count": len(articles),
        "source": source,
        "status": status,
        "needs_review": True,
    }
    atomic_write_json(report_path, report)
    print(f"[OK] 뉴스 후보 반영 완료: {report_path} / status={status} / articles={len(articles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
