#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
fetch_safetimes_schedule.py v2.0

세이프타임즈 '오늘의 주요일정' 기사를 날짜별로 수집합니다.

개선점
- 검색 결과 첫 페이지만 보지 않고 여러 페이지를 탐색합니다.
- 제목의 '·N일'만으로 판단하지 않고 기사 승인일(YYYY.MM.DD)을 함께 확인합니다.
- 과거 날짜도 수집 가능하도록 설계했습니다.
- 예: 2026-05-18 -> [오늘의 주요일정·18일] 기사 수집
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.safetimes.co.kr"
SEARCH_URL = "https://www.safetimes.co.kr/news/articleList.html"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class SafeTimesError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="세이프타임즈 오늘의 주요일정 수집")
    parser.add_argument("--date", required=True, help="수집 기준일 YYYY-MM-DD")
    parser.add_argument("--out-dir", default="data/schedules", help="저장 폴더")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--retry-delay", type=int, default=10)
    parser.add_argument("--force-refresh", action="store_true", help="기존 JSON이 있어도 재수집")
    parser.add_argument("--max-pages", type=int, default=80, help="세이프타임즈 검색 페이지 탐색 수")
    return parser.parse_args()


def target_datetime(date_text: str) -> datetime:
    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError as exc:
        raise SafeTimesError("--date는 YYYY-MM-DD 형식이어야 합니다.") from exc


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), delete=False,
        prefix=f".{path.name}.", suffix=".tmp"
    ) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def read_existing_valid(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("success") is False:
        return None
    if data.get("article_url") and (data.get("items") or data.get("raw_text")):
        return data
    return None


def fetch(url: str, params: Optional[Dict[str, Any]] = None) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": BASE_URL,
    }
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    if resp.apparent_encoding:
        resp.encoding = resp.apparent_encoding
    return resp.text


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def day_patterns(target: datetime) -> List[str]:
    day = target.day
    return [
        f"·{day}일",
        f"ㆍ{day}일",
        f"{day}일]",
        f"{target.month}월 {day}일",
    ]


def parse_approved_date_from_text(text: str) -> str:
    # 기사 본문 내 "승인 2026.05.18 07:03" 형식
    m = re.search(r"승인\s*(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # meta 등 느슨한 fallback
    m = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})\s+\d{1,2}:\d{2}", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    return ""


def collect_search_candidates(max_pages: int) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    seen = set()

    for page in range(1, max_pages + 1):
        html = fetch(SEARCH_URL, params={"page": page, "sc_word": "오늘의 주요일정"})
        soup = BeautifulSoup(html, "html.parser")
        page_added = 0

        for a in soup.find_all("a", href=True):
            title = normalize_text(a.get_text(" ", strip=True))
            href = a.get("href", "")

            if "오늘의 주요일정" not in title:
                continue
            if "articleView" not in href:
                continue

            url = urljoin(BASE_URL, href)
            key = (title, url)
            if key in seen:
                continue
            seen.add(key)

            candidates.append({"title": title, "url": url})
            page_added += 1

        # 너무 뒤 페이지까지 갈 필요가 없도록,
        # 일정 후보가 전혀 안 나오는 페이지가 연속되면 중단
        if page > 5 and page_added == 0:
            break

        time.sleep(0.15)

    return candidates


def parse_article_candidate(article: Dict[str, str]) -> Dict[str, Any]:
    html = fetch(article["url"])
    soup = BeautifulSoup(html, "html.parser")
    text_all = soup.get_text("\n", strip=True)

    h1 = soup.find("h1")
    title = normalize_text(h1.get_text(" ", strip=True)) if h1 else article["title"]

    body_node = (
        soup.select_one("#article-view-content-div")
        or soup.select_one(".article-view-content")
        or soup.select_one("article")
        or soup.select_one(".user-content")
    )

    if body_node:
        raw_text = body_node.get_text("\n", strip=True)
    else:
        # 세이프타임즈는 본문이 명확한 div로 안 잡히는 경우가 있어 전체 텍스트에서 본문영역을 사용
        raw_text = text_all

    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text).strip()
    approved_date = parse_approved_date_from_text(text_all)

    return {
        "title": title,
        "article_title": article["title"],
        "article_url": article["url"],
        "approved_date": approved_date,
        "raw_text": raw_text,
        "full_text": text_all,
    }


def select_article_for_date(candidates: List[Dict[str, str]], target_date: str) -> Dict[str, Any]:
    target = target_datetime(target_date)
    patterns = day_patterns(target)

    day_matched = [
        cand for cand in candidates
        if any(pattern in cand["title"] for pattern in patterns)
    ]

    parsed: List[Dict[str, Any]] = []
    for cand in day_matched:
        try:
            article = parse_article_candidate(cand)
            parsed.append(article)
            if article.get("approved_date") == target_date:
                return article
        except Exception:
            continue

    # 승인일 파싱이 실패하는 경우: 제목 day가 맞고 full_text에 target_date 점표기가 있으면 선택
    dot_date = target.strftime("%Y.%m.%d")
    for article in parsed:
        if dot_date in article.get("full_text", ""):
            return article

    sample = [cand["title"] for cand in candidates[:8]]
    matched_sample = [
        {"title": item.get("title", ""), "approved_date": item.get("approved_date", ""), "url": item.get("article_url", "")}
        for item in parsed[:8]
    ]
    raise SafeTimesError(
        f"오늘의 주요일정 대상 기사를 찾지 못했습니다. "
        f"target={target_date}, sample_candidates={sample}, day_matched={matched_sample}"
    )


def extract_items(raw_text: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    seen = set()

    for line in raw_text.splitlines():
        clean = normalize_text(line)
        if not clean:
            continue
        if clean in seen:
            continue

        # 기사 UI/메뉴성 문구 제외
        if any(skip in clean for skip in ["댓글", "SNS 기사", "본문 글씨", "저작권", "회원로그인", "바로가기"]):
            continue

        if re.search(r"(\d{1,2}:\d{2}|오전|오후|국회|정부|장관|위원회|브리핑|회의|산업부|기후|에너지|공정위|금융위)", clean):
            seen.add(clean)
            items.append({"text": clean})

    return items


def collect(target_date: str, max_pages: int) -> Dict[str, Any]:
    candidates = collect_search_candidates(max_pages=max_pages)
    if not candidates:
        raise SafeTimesError("세이프타임즈 오늘의 주요일정 후보 기사를 찾지 못했습니다.")

    article = select_article_for_date(candidates, target_date)
    items = extract_items(article["raw_text"])

    return {
        "schema_version": "2.0",
        "source": "세이프타임즈",
        "category": "오늘의 주요일정",
        "date": target_date,
        "title": article["title"],
        "article_title": article["article_title"],
        "article_url": article["article_url"],
        "approved_date": article.get("approved_date", ""),
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "items": items,
        "raw_text": article["raw_text"],
        "success": True,
        "quality": {
            "needs_review": True,
            "warnings": [
                "세이프타임즈 기사 본문을 자동 파싱한 초안입니다.",
                "기사 원문 기준 일정은 사실 데이터이며, 정유/석화/LNG 영향도는 후속 변환 단계의 해석입니다.",
            ],
        },
    }


def main() -> int:
    args = parse_args()
    output_path = Path(args.out_dir) / f"{args.date}.json"

    existing = read_existing_valid(output_path)
    if existing and not args.force_refresh:
        print(f"[OK] 기존 세이프타임즈 일정 JSON 재사용: {output_path}")
        return 0

    last_error: Optional[Exception] = None
    for attempt in range(1, max(1, args.max_retries) + 1):
        try:
            print(f"[INFO] 세이프타임즈 수집 시도 {attempt}/{args.max_retries}: {args.date}")
            payload = collect(args.date, max_pages=args.max_pages)
            atomic_write_json(output_path, payload)
            print(f"[OK] 세이프타임즈 일정 저장 완료: {output_path}")
            print(f"[OK] 기사: {payload.get('article_title')} / {payload.get('article_url')}")
            return 0
        except Exception as exc:
            last_error = exc
            print(f"[WARN] 수집 실패 {attempt}/{args.max_retries}: {exc}")
            if attempt < args.max_retries:
                time.sleep(max(0, args.retry_delay))

    error_path = Path(args.out_dir) / f"{args.date}.error.json"
    atomic_write_json(error_path, {
        "schema_version": "2.0",
        "source": "세이프타임즈",
        "category": "오늘의 주요일정",
        "date": args.date,
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "success": False,
        "error": str(last_error) if last_error else "unknown error",
    })
    print(f"[ERROR] 실패 정보 저장: {error_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
