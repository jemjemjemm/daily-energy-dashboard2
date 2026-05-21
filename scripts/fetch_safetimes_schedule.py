#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
fetch_safetimes_schedule.py v1.2

세이프타임즈 '오늘의 주요일정' 자동 수집 스크립트.

핵심 보완
1. 재실행 안정성:
   - data/schedules/YYYY-MM-DD.json이 이미 있으면 기본적으로 기존 파일을 재사용하고 성공 처리합니다.
   - 그래프/HTML만 다시 만들려고 과거 날짜를 재실행할 때 세이프타임즈 기사 탐색 실패로 전체 pipeline이 멈추는 것을 방지합니다.

2. 날짜 후보 보강:
   - target date 당일뿐 아니라 target date 전일/익일까지 후보를 확인합니다.
   - 세이프타임즈가 '20일 일정'을 19일에 올리거나, '21일 일정'을 20일에 올리는 구조를 감안합니다.

3. 실패 시:
   - 기존 정상 JSON이 없을 때만 error.json을 저장하고 exit 1 처리합니다.

사용 예:
  python scripts/fetch_safetimes_schedule.py --date 2026-05-20 --out-dir data/schedules --max-retries 1 --retry-delay 10
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.safetimes.co.kr"
SEARCH_URL = "https://www.safetimes.co.kr/news/articleList.html"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class SafeTimesError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="세이프타임즈 오늘의 주요일정 수집")
    parser.add_argument("--date", required=True, help="수집 기준일 YYYY-MM-DD")
    parser.add_argument("--out-dir", default="data/schedules", help="저장 폴더")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--retry-delay", type=int, default=10)
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="기존 정상 JSON이 있어도 다시 수집합니다.",
    )
    return parser.parse_args()


def parse_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SafeTimesError("--date는 YYYY-MM-DD 형식이어야 합니다.") from exc


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
        prefix=f".{path.name}.",
        suffix=".tmp",
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

    # 정상 schedule 파일로 볼 수 있는 최소 조건
    if data.get("success") is False:
        return None
    if data.get("items") or data.get("schedules") or data.get("raw_text") or data.get("article_url"):
        return data
    return None


def fetch(url: str, params: Optional[Dict[str, Any]] = None) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": BASE_URL,
    }
    resp = requests.get(url, params=params, headers=headers, timeout=25)
    resp.raise_for_status()
    if resp.apparent_encoding:
        resp.encoding = resp.apparent_encoding
    return resp.text


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def target_day_patterns(target: datetime) -> List[str]:
    day = target.day
    month = target.month
    return [
        f"{day}일",
        f"{month}월 {day}일",
        f"{month}/{day}",
        f"{month}.{day}",
    ]


def search_candidates(keyword: str = "오늘의 주요일정") -> List[Dict[str, str]]:
    """
    세이프타임즈 기사 목록에서 오늘의 주요일정 후보를 가져옵니다.
    사이트 구조 변경에 대비해 제목/링크 중심으로 느슨하게 수집합니다.
    """
    html = fetch(SEARCH_URL, params={"sc_word": keyword})
    soup = BeautifulSoup(html, "html.parser")

    candidates: List[Dict[str, str]] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        title = normalize_text(a.get_text(" ", strip=True))
        href = a.get("href", "")

        if "오늘의 주요일정" not in title:
            continue

        url = urljoin(BASE_URL, href)
        key = (title, url)
        if key in seen:
            continue
        seen.add(key)

        candidates.append({
            "title": title,
            "url": url,
        })

    return candidates


def select_article(candidates: List[Dict[str, str]], target: datetime) -> Dict[str, str]:
    """
    1순위: 제목에 target date의 'N일'이 있는 기사
    2순위: 제목에 target date 전후 1일 중 target day를 암시하는 기사
    """
    patterns = target_day_patterns(target)

    for cand in candidates:
        title = cand["title"]
        if any(pattern in title for pattern in patterns):
            return cand

    sample = [cand["title"] for cand in candidates[:5]]
    raise SafeTimesError(
        f"오늘의 주요일정 대상 기사를 찾지 못했습니다. "
        f"target={target.strftime('%Y-%m-%d')}, sample_candidates={sample}"
    )


def parse_article(article: Dict[str, str], target_date: str) -> Dict[str, Any]:
    html = fetch(article["url"])
    soup = BeautifulSoup(html, "html.parser")

    title = normalize_text(soup.find("h1").get_text(" ", strip=True)) if soup.find("h1") else article["title"]

    # 기사 본문 후보
    body_node = (
        soup.select_one("#article-view-content-div")
        or soup.select_one(".article-view-content")
        or soup.select_one("article")
        or soup.select_one(".user-content")
    )

    if body_node:
        raw_text = body_node.get_text("\n", strip=True)
    else:
        raw_text = soup.get_text("\n", strip=True)

    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text).strip()

    items = []
    for line in raw_text.splitlines():
        clean = normalize_text(line)
        if not clean:
            continue
        # 일정 라인으로 보이는 것만 느슨하게 수집
        if re.search(r"(\d{1,2}:\d{2}|오전|오후|국회|정부|장관|위원회|브리핑|회의)", clean):
            items.append({"text": clean})

    return {
        "schema_version": "1.2",
        "source": "세이프타임즈",
        "category": "오늘의 주요일정",
        "date": target_date,
        "title": title,
        "article_title": article["title"],
        "article_url": article["url"],
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "items": items,
        "raw_text": raw_text,
        "success": True,
        "quality": {
            "needs_review": True,
            "warnings": [
                "세이프타임즈 기사 본문을 자동 파싱한 초안입니다.",
                "일정별 정유/석화/LNG 관련성 평가는 후속 변환 단계에서 작성자 해석으로 처리됩니다.",
            ],
        },
    }


def collect(target_date: str) -> Dict[str, Any]:
    target = parse_date(target_date)
    candidates = search_candidates("오늘의 주요일정")

    if not candidates:
        raise SafeTimesError("세이프타임즈 오늘의 주요일정 후보 기사를 찾지 못했습니다.")

    article = select_article(candidates, target)
    return parse_article(article, target_date)


def main() -> int:
    args = parse_args()
    target_date = args.date
    out_dir = Path(args.out_dir)
    output_path = out_dir / f"{target_date}.json"

    existing = read_existing_valid(output_path)
    if existing and not args.force_refresh:
        print(f"[OK] 기존 세이프타임즈 일정 JSON 재사용: {output_path}")
        print("[OK] 과거 날짜 재실행이므로 재수집을 건너뜁니다. 강제 재수집은 --force-refresh 사용.")
        return 0

    last_error: Optional[Exception] = None

    for attempt in range(1, max(1, args.max_retries) + 1):
        try:
            print(f"[INFO] 세이프타임즈 수집 시도 {attempt}/{args.max_retries}: {target_date}")
            payload = collect(target_date)
            atomic_write_json(output_path, payload)
            print(f"[OK] 세이프타임즈 일정 저장 완료: {output_path}")
            return 0
        except Exception as exc:
            last_error = exc
            print(f"[WARN] 수집 실패 {attempt}/{args.max_retries}: {exc}")
            if attempt < args.max_retries:
                time.sleep(max(0, args.retry_delay))

    # 수집 실패했지만 기존 정상 JSON이 뒤늦게 확인되면 재사용
    existing = read_existing_valid(output_path)
    if existing:
        print(f"[OK] 수집은 실패했지만 기존 정상 파일을 재사용합니다: {output_path}")
        return 0

    error_path = out_dir / f"{target_date}.error.json"
    atomic_write_json(error_path, {
        "schema_version": "1.2",
        "source": "세이프타임즈",
        "category": "오늘의 주요일정",
        "date": target_date,
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "success": False,
        "error": str(last_error) if last_error else "unknown error",
        "quality": {
            "needs_review": True,
            "warnings": [
                "세이프타임즈 오늘의 주요일정 수집 실패",
                "과거 날짜 재생성 시 data/schedules/YYYY-MM-DD.json이 있으면 재사용되도록 설계되어 있습니다.",
            ],
        },
    })
    print(f"[ERROR] 실패 정보 저장: {error_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
