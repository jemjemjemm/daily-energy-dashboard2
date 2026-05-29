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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
import time

# 간단한 로컬 캐시: 국회 영상 조회 결과를 저장하여 반복 호출을 피합니다.
CACHE_DIR = Path(".cache")
CACHE_FILE = CACHE_DIR / "assembly_links.json"
try:
    from scripts.find_assembly_video import search_assembly_for_title
except Exception:
    # optional helper; network lookup may be unavailable in some environments
    def search_assembly_for_title(title: str, date: str | None = None) -> None:
        return None

BAD_TITLES = ["오늘의 주요일정", "주요일정", "대표 기사 데이터 없음", "자동 수집 미적용", "대표 기사 미확인"]
BAD_SUMMARY_PHRASES = [
    "자동 수집된 대표 기사 없음", "가격 데이터 중심", "원문 데이터", "fallback",
    "찾지 못했습니다", "미확인", "주요 보도 없음", "대표 기사 없음",
]
KST = timezone(timedelta(hours=9))

PRICE_SUMMARY_RE = re.compile(r"\s*가격 그래프는 기준일 전일 기준 과거 2개월\([^)]*\)만 표시하며, 값이 0인 가격은 제외\.?,?", re.U)


NOUN_ENDING_REPLACEMENTS = [
    ("다뤘습니다.", "다룸."), ("다뤘다.", "다룸."), ("다룸.", "다룸."),
    ("보도했습니다.", "보도."), ("보도했다.", "보도."),
    ("소개했습니다.", "소개."), ("소개했다.", "소개."),
    ("분석했습니다.", "분석."), ("분석했다.", "분석."),
    ("전망했습니다.", "전망."), ("전망했다.", "전망."),
    ("제시했습니다.", "제시."), ("제시했다.", "제시."),
    ("밝혔습니다.", "밝힘."), ("밝혔다.", "밝힘."),
    ("강조했습니다.", "강조."), ("강조했다.", "강조."),
    ("설명했습니다.", "설명."), ("설명했다.", "설명."),
    ("전했습니다.", "전달."), ("전했다.", "전달."),
    ("예상했습니다.", "예상."), ("예상했다.", "예상."),
    ("언급했습니다.", "언급."), ("언급했다.", "언급."),
    ("지적했습니다.", "지적."), ("지적했다.", "지적."),
    ("입니다.", "임."), ("입니다", "임."), ("했습니다.", "함."), ("했다.", "함."),
]

THEME_RULES = [
    ("석유화학 공급과잉 부담 지속", ["석유화학", "공급과잉", "나프타", "에틸렌", "화학제품"]),
    ("호르무즈·중동 정세에 따른 원유·LNG 수급 리스크", ["호르무즈", "중동", "이란", "원유", "LNG", "천연가스", "수급", "공급망"]),
    ("고유가와 SAF 부담에 따른 항공·정유업계 영향", ["SAF", "지속가능항공유", "항공유", "항공", "고유가", "친환경 연료"]),
    ("석유제품 가격 안정 정책과 유류세 이슈", ["최고가격제", "유류세", "가격상한", "휘발유", "경유", "주유소"]),
    ("에너지 가격발 물가 부담", ["생산자물가", "소비자물가", "수입물가", "물가", "석탄및석유제품"]),
    ("정부·국회 에너지 정책 논의", ["정부", "산업부", "산업통상부", "공정위", "국회", "기재부", "기후부"]),
    ("정유사 실적과 재고평가손익 변동성", ["정유사", "정유", "실적", "재고평가", "정제마진"]),
]


def to_report_style(text: str) -> str:
    """조간 섹션 문장을 보고서형 명사 종결로 정리합니다."""
    t = clean(text)
    if not t:
        return ""
    t = re.sub(r"[\s\u00a0]+", " ", t).strip()
    t = re.sub(r"\s*[-–—]\s*[^\s]{2,12}\s*$", "", t).strip()
    # 기사 본문 조각이 너무 길면 한 문장 단위로 압축
    if len(t) > 170:
        t = t[:170].rsplit(" ", 1)[0].strip()
    for src, dst in NOUN_ENDING_REPLACEMENTS:
        if t.endswith(src):
            t = t[: -len(src)] + dst
            break
    else:
        if t.endswith("습니다"):
            t = t[:-3] + "음."
        elif t.endswith("니다"):
            t = t[:-2] + "음."
        elif not re.search(r"[.。!?]$", t):
            # 명사구·제목형은 그대로 마침표만 부여
            t += "."
    t = t.replace(" 다뤘음.", " 다룸.").replace(" 보도함.", " 보도.")
    return t


def infer_theme_labels(articles: List[Dict[str, str]], topics: List[str] | None = None) -> List[str]:
    text = " ".join((a.get("title", "") + " " + a.get("summary", "")) for a in articles)
    labels: List[str] = []
    for label, keys in THEME_RULES:
        if any(k.lower() in text.lower() for k in keys):
            labels.append(label)
    if not labels and topics:
        for topic in topics:
            topic = clean(topic)
            if topic and topic not in labels:
                labels.append(topic)
    if not labels:
        labels.append("정유·석유화학·LNG 업계 관련 이슈")
    return labels[:3]


def make_trend_headline(articles: List[Dict[str, str]], topics: List[str] | None = None) -> str:
    labels = infer_theme_labels(articles, topics)
    if len(labels) == 1:
        return f"주요 매체가 △{labels[0]} 등을 중심으로 보도."
    return "주요 매체가 " + " ".join(f"△{x}" for x in labels) + " 등을 중심으로 보도."


def _has_batchim(text: str) -> bool:
    """마지막 한글 음절의 받침 여부를 반환합니다."""
    t = clean(text)
    if not t:
        return False
    ch = t[-1]
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        return (code - 0xAC00) % 28 != 0
    # 영문·숫자·기호는 자연스러운 기본 조사로 처리
    return False


def topic_particle(text: str) -> str:
    return "은" if _has_batchim(text) else "는"


def strip_polite_endings(text: str) -> str:
    """공개 보고서에 남기지 않을 서술형 종결을 명사형/보고서형으로 정리합니다."""
    t = to_report_style(text)
    replacements = {
        "다뤘습니다.": "다룸.",
        "다뤘습니다": "다룸.",
        "보도했습니다.": "보도.",
        "보도했습니다": "보도.",
        "소개했습니다.": "소개.",
        "분석했습니다.": "분석.",
        "전망했습니다.": "전망.",
        "설명했습니다.": "설명.",
        "밝혔습니다.": "밝힘.",
    }
    for src, dst in replacements.items():
        if t.endswith(src):
            t = t[: -len(src)] + dst
            break
    t = t.replace(" 다뤘음.", " 다룸.").replace(" 보도함.", " 보도.")
    return t


def article_trend_sentence(article: Dict[str, str]) -> str:
    press = clean(article.get("press")) or "해당 매체"
    title = clean(article.get("title"))
    summary = strip_polite_endings(article.get("summary", ""))
    published = clean(article.get("published_at_kst"))
    time_text = ""
    if published:
        # YYYY-MM-DD HH:MM -> M/D HH:MM 입력 기사에서
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}:\d{2})", published)
        if m:
            time_text = f"{int(m.group(2))}/{int(m.group(3))} {m.group(4)} 입력 기사에서 "
    core = title
    core = re.sub(r"^\[[^\]]+\]\s*", "", core).strip()
    core = re.sub(r"\s+-\s+[^-]{2,12}$", "", core).strip()
    particle = topic_particle(press)
    if summary and summary not in {"원문 링크 기준으로 세부 내용 검수가 필요합니다.", "원문 링크 기준으로 세부 내용 검수가 필요함."}:
        if time_text:
            summary = re.sub(r"^\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}\s*입력\.?\s*", "", summary).strip()
        return f"{press}{particle} {time_text}{summary}"
    return f"{press}{particle} {time_text}{core} 관련 내용 보도."


def make_trend_paragraphs(articles: List[Dict[str, str]]) -> List[str]:
    return [article_trend_sentence(a) for a in articles[:3]]



def parse_args():
    p = argparse.ArgumentParser(description="뉴스 후보를 리포트 JSON에 반영")
    p.add_argument("--date", required=True)
    p.add_argument("--report-dir", default="data/reports")
    p.add_argument("--news-dir", default="data/news")
    p.add_argument("--max-articles", type=int, default=3)
    p.add_argument("--min-required", type=int, default=1)
    p.add_argument("--lookback-hours", type=int, default=18)
    p.add_argument("--cutoff-hour", type=int, default=11)
    p.add_argument("--cutoff-minute", type=int, default=30)
    return p.parse_args()


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    # 사용되는 JSON 파일이 BOM(utf-8-sig)을 포함할 수 있으므로 안전하게 처리
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, prefix=f".{path.name}.", suffix=".tmp") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def clean(v: Any) -> str:
    return re.sub(r"\s+", " ", "" if v is None else str(v)).strip()


def split_issue_title_time_location(title: str) -> tuple[str, str, str]:
    title = clean(title)
    parsed_time = ""
    location = ""
    while True:
        match = re.search(r"\(([^()]*)\)\s*$", title)
        if not match:
            break
        inner = clean(match.group(1))
        inner_time_match = re.search(r"\b\d{1,2}[:：]\d{2}\b", inner)
        if inner_time_match and not parsed_time:
            parsed_time = inner_time_match.group(0).replace("：", ":")
        inner_location = clean(re.sub(r"\b\d{1,2}[:：]\d{2}\b", "", inner))
        if inner_location:
            location = inner_location if not location else f"{inner_location} · {location}"
        title = clean(title[:match.start()])

    leading_time = re.match(r"^\b\d{1,2}[:：]\d{2}\b", title)
    if leading_time and not parsed_time:
        parsed_time = leading_time.group(0).replace("：", ":")
    title = re.sub(r"^\b\d{1,2}[:：]\d{2}\b\s*", "", title).strip()
    return title, parsed_time, location


def normalize_issue_fields(issue: Dict[str, Any]) -> None:
    raw_title = clean(issue.get("title") or issue.get("name") or "")
    title, parsed_time, parsed_location = split_issue_title_time_location(raw_title)
    if title:
        issue["title"] = title
    if parsed_time and clean(issue.get("time")) in {"", "시간미정", "-"}:
        issue["time"] = parsed_time
    if parsed_location and not clean(issue.get("location")):
        issue["location"] = parsed_location

    parts = []
    time_text = clean(issue.get("time"))
    org = clean(issue.get("org") or issue.get("organization") or issue.get("agency"))
    location = clean(issue.get("location"))
    if time_text and time_text not in {"시간미정", "-"}:
        parts.append(time_text)
    if org:
        parts.append(org)
    if location:
        parts.append(location)
    if parts:
        issue["description"] = " · ".join(parts)

    links = issue.get("links")
    if not isinstance(links, list) or not links:
        issue["links"] = [{"label": "관련 기사 없음", "url": ""}]


def strip_article_source_suffix(text: str, press: str = "") -> str:
    text = clean(text)
    press = clean(press)
    if press:
        text = re.sub(rf"\s*-\s*{re.escape(press)}\s*$", "", text).strip()
        text = re.sub(rf"\s+{re.escape(press)}\.?\s*$", "", text).strip()
    text = re.sub(r"\s*-\s*[^-]{2,24}\s*$", "", text).strip()
    return text


def normalize_article_text(text: str, press: str = "") -> str:
    text = strip_article_source_suffix(text, press)
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE).lower()


def is_repeated_article_desc(title: str, desc: str, press: str = "") -> bool:
    title_n = normalize_article_text(title, press)
    desc_n = normalize_article_text(desc, press)
    if not desc_n:
        return True
    return title_n and (desc_n in title_n or title_n in desc_n or title_n[:16] == desc_n[:16])


def fallback_article_summary(title: str) -> str:
    title = strip_article_source_suffix(title)
    title = re.sub(r"^\[[^\]]+\]\s*", "", title).strip()
    compact = re.sub(r"\s+", " ", title)

    if "공습" in compact and ("브렌트" in compact or "유가" in compact):
        return "美 이란 공습 여파로 브렌트유 4% 가까이 반등"
    if "호르무즈" in compact and "유가" in compact:
        return "호르무즈 개방 기대 변화가 원유 수급 안정성과 정유 수익성 압박을 함께 부각"
    if "이란 협상" in compact and "유가" in compact:
        return "이란 협상 진전 기대가 국제유가 하락 요인으로 작용"
    if "중동" in compact and "유가" in compact:
        return "중동 정세 변화가 국제유가와 원유 수급 리스크에 미치는 영향 보도"
    if "석유화학" in compact:
        return "석유화학 업황과 주요 기업·시장 변수 관련 쟁점 정리"
    if "정유" in compact and ("AI" in compact or "데이터센터" in compact or "액침냉각" in compact):
        return "액침냉각 등 정유사의 비석유 신사업 확대 흐름 조명"
    if "정유" in compact:
        return "정유업계 수익성·원가·시장 여건 변화를 중심으로 보도"
    if "LNG" in compact:
        return "LNG 수급·가격 변동이 에너지 시장에 미치는 영향 보도"
    if "유가" in compact or "원유" in compact or "석유" in compact:
        return "국제유가와 석유시장 변동 요인을 중심으로 정리"
    return "해당 이슈의 업계 관련성을 원문 기준으로 확인 필요"


def in_morning_issue_window(
    item: Dict[str, Any],
    target_date: str,
    lookback_hours: int,
    cutoff_hour: int,
    cutoff_minute: int,
) -> bool:
    """기사 발행일·시간이 기준일 조간 범위인지 최종 검증합니다.

    허용 범위: 전일 18:00 ~ 기준일 11:30 KST.
    published_at_kst가 있으면 시간까지 엄격히 검증하고, published_date만 있으면
    전일/기준일 날짜까지만 허용합니다. 발행 정보가 없는 보조 검색 후보는
    fetch 단계의 기간 필터를 신뢰하되, 기존 보존 기사에는 적용하지 않습니다.
    """
    target = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=KST)
    start = target - timedelta(hours=lookback_hours)
    end = target.replace(hour=cutoff_hour, minute=cutoff_minute, second=59)
    published_at = clean(item.get("published_at_kst"))
    published_date = clean(item.get("published_date"))
    if published_at:
        try:
            dt = datetime.strptime(published_at[:16], "%Y-%m-%d %H:%M").replace(tzinfo=KST)
            return start <= dt <= end
        except Exception:
            return False
    if published_date:
        return published_date in {start.strftime("%Y-%m-%d"), target.strftime("%Y-%m-%d")}
    return True


def valid_article(
    item: Dict[str, Any],
    target_date: str | None = None,
    lookback_hours: int = 18,
    cutoff_hour: int = 11,
    cutoff_minute: int = 30,
) -> bool:
    title = clean(item.get("title"))
    url = clean(item.get("url"))
    if not title or not url:
        return False
    if any(b in title for b in BAD_TITLES):
        return False
    if any(b in url for b in ["safetimes.co.kr/news/articleView"]):
        return False
    if target_date and not in_morning_issue_window(item, target_date, lookback_hours, cutoff_hour, cutoff_minute):
        return False
    return True


def normalize_article(item: Dict[str, Any]) -> Dict[str, str]:
    title = clean(item.get("title"))
    press = clean(item.get("press") or item.get("source")) or "Google News"
    snippet = clean(item.get("summary") or item.get("snippet"))
    if snippet:
        snippet = strip_article_source_suffix(snippet, press)
        snippet = re.sub(r" - [^ ]+(?:\s|$)", " ", snippet)
        snippet = re.sub(r"\s+", " ", snippet).strip()
        summary = snippet[:147] + "..." if len(snippet) > 150 else snippet
        summary = strip_polite_endings(summary)
    else:
        summary = fallback_article_summary(title)
    if is_repeated_article_desc(title, summary, press):
        summary = fallback_article_summary(title)
    return {
        "title": title,
        "press": press,
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
    provided = clean(news.get("summary"))
    if provided and not any(x in provided for x in BAD_SUMMARY_PHRASES) and not any(x in provided for x in ["다뤘습니다", "보도했습니다", "수집됐습니다"]):
        return strip_polite_endings(provided)
    return make_trend_headline(articles, topics)

def update_summary(report: Dict[str, Any], news_summary: str) -> None:
    existing = report.get("summary", []) if isinstance(report.get("summary"), list) else []
    cleaned = []
    for item in existing:
        if not isinstance(item, dict) or item.get("type") == "news_trend":
            continue
        text = PRICE_SUMMARY_RE.sub("", clean(item.get("text"))).strip()
        text = strip_polite_endings(text)
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
    # load assembly lookup cache
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if CACHE_FILE.exists():
            with CACHE_FILE.open("r", encoding="utf-8") as fh:
                _assembly_cache: Dict[str, str] = json.load(fh)
        else:
            _assembly_cache = {}
    except Exception:
        _assembly_cache = {}
    report_path = Path(a.report_dir) / f"{a.date}.report.json"
    news_path = Path(a.news_dir) / f"{a.date}.json"
    report = read_json(report_path)
    if not report:
        print(f"[ERROR] 리포트 JSON이 없습니다: {report_path}")
        return 1

    news = read_json(news_path)
    raw_articles = news.get("articles", []) if isinstance(news.get("articles"), list) else []
    new_articles = [
        normalize_article(i) for i in raw_articles
        if isinstance(i, dict) and valid_article(i, a.date, a.lookback_hours, a.cutoff_hour, a.cutoff_minute)
    ][:a.max_articles]
    old_articles = [
        normalize_article(i) for i in existing_valid_articles(report)
        if isinstance(i, dict) and valid_article(i, a.date, a.lookback_hours, a.cutoff_hour, a.cutoff_minute)
    ][:a.max_articles]

    if new_articles:
        articles = new_articles
        news_summary = build_news_summary(news, articles)
        source = clean(news.get("source")) or "Naver News Search HTML + Daum News Search HTML + Google News RSS"
        used_tier = clean(news.get("used_tier"))
        if used_tier:
            source = f"{source} ({used_tier})"
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

    report["news_trend"] = {"summary": news_summary, "trend_paragraphs": make_trend_paragraphs(articles), "articles": articles, "source": source, "needs_review": True}
    update_summary(report, news_summary)
    report.setdefault("automation", {})["news"] = {
        "source_file": str(news_path),
        "article_count": len(articles),
        "source": source,
        "status": status,
        "needs_review": True,
    }
    # 이슈 항목에 관련 기사 링크 매칭: 제목 유사도 기반으로 articles에서 링크를 찾아 붙임
    def _norm_for_compare(text: str) -> str:
        t = re.sub(r"\([^)]*\)", "", clean(text or ""))
        return re.sub(r"[\s\W_]+", "", t, flags=re.U).lower()

    related_default = {"label": "관련 기사 없음", "url": ""}
    target_date = a.date
    issue_list = report.get("issues", []) if isinstance(report.get("issues"), list) else []
    for issue in issue_list:
        try:
            normalize_issue_fields(issue)
            it_title = clean(issue.get("title") or issue.get("name") or "")
            it_n = _norm_for_compare(it_title)
            candidates = []
            for article in articles:
                a_title = clean(article.get("title") or "")
                a_url = clean(article.get("url") or "")
                if not a_url:
                    continue
                a_n = _norm_for_compare(a_title)
                if (it_n and a_n and (a_n in it_n or it_n in a_n)) or (a_title and it_title and (a_title in it_title or it_title in a_title)) or (a_n and it_n and a_n[:16] == it_n[:16]):
                    candidates.append(article)
            chosen = None
            # 국회 회의는 의회 영상 회의록 링크 우선 탐색
            for c in candidates:
                url = clean(c.get("url") or "")
                if "assembly.go.kr" in url or "w3.assembly.go.kr" in url:
                    chosen = c
                    break
            if not chosen and candidates:
                chosen = candidates[0]
            # 추가: 국회 영상회의록 자동 조회 통합
            assembly_link = None
            try:
                # 캐시 우선 조회: 키는 정규화된 제목 문자열
                key = _norm_for_compare(it_title) or clean(it_title)
                cached = _assembly_cache.get(key)
                if cached is not None:
                    assembly_link = cached or None
                else:
                    # search_assembly_for_title은 네트워크 호출을 수행할 수 있음
                    assembly_link = search_assembly_for_title(it_title, target_date)
                    # rate limit: 사이트 부담을 줄이기 위해 소량 sleep
                    time.sleep(0.4)
                    _assembly_cache[key] = assembly_link or ""
            except Exception:
                assembly_link = None

            if chosen:
                links = [{"label": clean(chosen.get("press") or "관련 자료"), "url": clean(chosen.get("url") or "")}]
                # 후보가 assembly 링크가 아닐 경우, 자동 검색으로 assembly 링크가 발견되면 우선 추가
                if assembly_link and "assembly.go.kr" in assembly_link:
                    links.insert(0, {"label": "국회 영상회의록", "url": assembly_link})
                issue["links"] = links
            else:
                if assembly_link and "assembly.go.kr" in assembly_link:
                    issue["links"] = [{"label": "국회 영상회의록", "url": assembly_link}]
                else:
                    issue["links"] = [related_default]
        except Exception:
            issue.setdefault("links", [related_default])
        normalize_issue_fields(issue)
    atomic_write_json(report_path, report)
    # 캐시 저장(있으면)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with CACHE_FILE.open("w", encoding="utf-8") as fh:
            json.dump(_assembly_cache, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass
    print(f"[OK] 뉴스 후보 반영 완료: {report_path} / status={status} / articles={len(articles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
