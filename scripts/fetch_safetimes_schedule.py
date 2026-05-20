#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
fetch_safetimes_schedule.py

세이프타임즈 '오늘의 주요일정' 자동 수집 스크립트 v1.0

역할
- 시스템 날짜 또는 지정 날짜 기준으로 세이프타임즈 '[오늘의 주요일정·{일}일]' 기사를 찾는다.
- 기사 제목, URL, 발행정보, 본문 텍스트를 추출한다.
- data/schedules/YYYY-MM-DD.json 으로 저장한다.
- 실패 시 data/schedules/YYYY-MM-DD.error.json 을 저장해 원인 추적이 가능하게 한다.

기본 사용법
    python scripts/fetch_safetimes_schedule.py

특정 날짜 테스트
    python scripts/fetch_safetimes_schedule.py --date 2026-05-20

GitHub Actions 권장
    TZ=Asia/Seoul python scripts/fetch_safetimes_schedule.py

출력 예
    data/schedules/2026-05-20.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.safetimes.co.kr"
MAIN_URL = BASE_URL + "/"
LIST_URL = BASE_URL + "/news/articleList.html"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

TIMEOUT = 20
DEFAULT_OUTPUT_DIR = Path("data/schedules")


@dataclass
class CandidateArticle:
    title: str
    url: str
    source: str


class SafeTimesScraperError(RuntimeError):
    """수집 중단이 필요한 오류."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="세이프타임즈 오늘의 주요일정 자동 수집")
    parser.add_argument(
        "--date",
        default="",
        help="기준일 YYYY-MM-DD. 미지정 시 시스템 날짜 사용",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="JSON 저장 폴더. 기본값 data/schedules",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="기사 미발견 또는 네트워크 오류 시 재시도 횟수",
    )
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=300,
        help="재시도 간격(초). 기본 300초",
    )
    parser.add_argument(
        "--no-error-file",
        action="store_true",
        help="실패 시 error.json 저장하지 않음",
    )
    return parser.parse_args()


def parse_target_date(value: str) -> date:
    if value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise SafeTimesScraperError("--date는 YYYY-MM-DD 형식이어야 합니다.") from exc
    return datetime.now().date()


def request_html(url: str, params: Optional[Dict[str, str]] = None) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()

    # requests가 인코딩을 잘못 추정하는 경우 대비
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"

    return response.text


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_body_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in value.split("\n")]
    lines = [line for line in lines if line]

    # 기사 하단 공유/저작권/광고성 문구 일부 제거
    drop_patterns = [
        "SNS 기사보내기",
        "이 기사를 공유합니다",
        "저작권자",
        "무단전재",
        "세이프타임즈 모든 콘텐츠",
        "댓글",
        "바로가기",
    ]

    cleaned: List[str] = []
    for line in lines:
        if any(pattern in line for pattern in drop_patterns):
            continue
        cleaned.append(line)

    return "\n".join(cleaned).strip()


def make_search_keywords(target: date) -> List[str]:
    day = target.day
    return [
        f"오늘의 주요일정·{day}일",
        f"[오늘의 주요일정·{day}일]",
        "오늘의 주요일정",
    ]


def title_matches_target(title: str, target: date) -> bool:
    day = target.day
    title = normalize_space(title)

    # 핵심 조건: 오늘의 주요일정 + 해당 일자
    if "오늘의 주요일정" not in title:
        return False

    # '20일' 또는 '·20일' 또는 'ㆍ20일' 등 허용
    day_patterns = [
        rf"·\s*{day}일",
        rf"ㆍ\s*{day}일",
        rf"\[\s*오늘의 주요일정\s*[·ㆍ]\s*{day}일\s*\]",
        rf"오늘의 주요일정\s*[·ㆍ]\s*{day}일",
    ]
    return any(re.search(pattern, title) for pattern in day_patterns)


def extract_candidates_from_html(html: str, source: str) -> List[CandidateArticle]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: List[CandidateArticle] = []

    # 가장 보수적인 방식: 모든 a 태그 중 제목 패턴을 포함하는 링크를 후보로 수집
    for link in soup.find_all("a", href=True):
        title = normalize_space(link.get_text(" ", strip=True))
        if "오늘의 주요일정" not in title:
            continue

        url = urljoin(BASE_URL, link["href"])
        candidates.append(CandidateArticle(title=title, url=url, source=source))

    # 중복 제거
    dedup: Dict[str, CandidateArticle] = {}
    for item in candidates:
        key = item.url
        if key not in dedup:
            dedup[key] = item

    return list(dedup.values())


def fetch_candidates_from_main_and_list(target: date) -> List[CandidateArticle]:
    candidates: List[CandidateArticle] = []

    # 1) 메인 페이지: 오늘의 주요일정 섹션이 노출되는 경우가 많음
    try:
        main_html = request_html(MAIN_URL)
        candidates.extend(extract_candidates_from_html(main_html, "main"))
    except Exception as exc:
        print(f"[WARN] 메인 페이지 후보 수집 실패: {exc}", file=sys.stderr)

    # 2) 기사목록 일반 페이지
    try:
        list_html = request_html(LIST_URL)
        candidates.extend(extract_candidates_from_html(list_html, "articleList"))
    except Exception as exc:
        print(f"[WARN] 기사목록 후보 수집 실패: {exc}", file=sys.stderr)

    # 3) 검색 파라미터 기반 후보 수집
    for keyword in make_search_keywords(target):
        try:
            search_html = request_html(
                LIST_URL,
                params={
                    "sc_word": keyword,
                    "sc_area": "A",
                    "view_type": "sm",
                },
            )
            candidates.extend(extract_candidates_from_html(search_html, f"search:{keyword}"))
        except Exception as exc:
            print(f"[WARN] 검색 후보 수집 실패({keyword}): {exc}", file=sys.stderr)

    # 중복 제거
    dedup: Dict[str, CandidateArticle] = {}
    for item in candidates:
        if item.url not in dedup:
            dedup[item.url] = item

    return list(dedup.values())


def pick_target_article(candidates: Iterable[CandidateArticle], target: date) -> CandidateArticle:
    matched = [item for item in candidates if title_matches_target(item.title, target)]

    if not matched:
        sample_titles = [item.title for item in list(candidates)[:10]]
        raise SafeTimesScraperError(
            "오늘의 주요일정 대상 기사를 찾지 못했습니다. "
            f"target={target.isoformat()}, sample_candidates={sample_titles}"
        )

    # 같은 날짜 후보가 여러 개면 URL idxno가 큰 것 또는 검색/메인에서 먼저 온 것을 우선
    def score(item: CandidateArticle) -> tuple:
        idx_match = re.search(r"idxno=(\d+)", item.url)
        idxno = int(idx_match.group(1)) if idx_match else 0
        source_score = 2 if item.source.startswith("search:") else 1
        return (source_score, idxno)

    return sorted(matched, key=score, reverse=True)[0]


def extract_article_detail(article: CandidateArticle) -> Dict[str, Any]:
    html = request_html(article.url)
    soup = BeautifulSoup(html, "html.parser")

    title = article.title
    h1 = soup.find(["h1", "h2"], class_=re.compile("title|heading", re.I)) if soup else None
    if h1:
        title = normalize_space(h1.get_text(" ", strip=True))

    # 기사 본문 후보 selector. 사이트 개편 대비로 여러 방식 지원.
    body_selectors = [
        "#article-view-content-div",
        "div#article-view-content-div",
        ".article-view-content",
        ".article-body",
        "#articleBody",
        "article",
    ]

    body_node = None
    for selector in body_selectors:
        body_node = soup.select_one(selector)
        if body_node:
            break

    if not body_node:
        # fallback: 본문 텍스트가 가장 긴 div를 사용
        divs = soup.find_all("div")
        body_node = max(divs, key=lambda div: len(div.get_text(" ", strip=True)), default=None)

    body_text = clean_body_text(body_node.get_text("\n", strip=True)) if body_node else ""

    if not body_text or len(body_text) < 100:
        raise SafeTimesScraperError(
            f"기사 본문 추출 실패 또는 본문이 너무 짧습니다. url={article.url}, length={len(body_text)}"
        )

    published_at = extract_published_at(soup)

    return {
        "title": title,
        "url": article.url,
        "source": article.source,
        "published_at": published_at,
        "body": body_text,
        "body_length": len(body_text),
    }


def extract_published_at(soup: BeautifulSoup) -> str:
    # 사이트별 meta/article info 대응
    meta_candidates = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "article:published_time"}),
        ("meta", {"name": "date"}),
        ("meta", {"property": "og:regDate"}),
    ]

    for tag_name, attrs in meta_candidates:
        node = soup.find(tag_name, attrs=attrs)
        if node and node.get("content"):
            return normalize_space(node.get("content", ""))

    text = soup.get_text(" ", strip=True)
    patterns = [
        r"승인\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2})",
        r"입력\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2})",
        r"(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return ""


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def build_success_payload(target: date, detail: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "date": target.isoformat(),
        "source_site": "세이프타임즈",
        "category": "오늘의 주요일정",
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "title": detail["title"],
        "url": detail["url"],
        "published_at": detail.get("published_at", ""),
        "body": detail["body"],
        "body_length": detail.get("body_length", len(detail["body"])),
        "raw": {
            "candidate_source": detail.get("source", ""),
        },
        "quality": {
            "title_matched": True,
            "body_extracted": bool(detail.get("body")),
            "needs_review": False,
            "warnings": [],
        },
    }


def build_error_payload(target: date, error: Exception) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "date": target.isoformat(),
        "source_site": "세이프타임즈",
        "category": "오늘의 주요일정",
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "success": False,
        "error": str(error),
        "quality": {
            "needs_review": True,
            "warnings": [
                "세이프타임즈 오늘의 주요일정 수집 실패",
                "기사 업로드 지연, 사이트 구조 변경, 네트워크 오류 가능성 확인 필요",
            ],
        },
    }


def fetch_once(target: date) -> Dict[str, Any]:
    candidates = fetch_candidates_from_main_and_list(target)
    article = pick_target_article(candidates, target)
    detail = extract_article_detail(article)
    return build_success_payload(target, detail)


def main() -> int:
    args = parse_args()
    target = parse_target_date(args.date)
    out_dir = Path(args.out_dir)
    output_path = out_dir / f"{target.isoformat()}.json"
    error_path = out_dir / f"{target.isoformat()}.error.json"

    last_error: Optional[Exception] = None

    for attempt in range(1, args.max_retries + 1):
        try:
            print(f"[INFO] 세이프타임즈 수집 시도 {attempt}/{args.max_retries}: {target.isoformat()}")
            payload = fetch_once(target)
            payload["success"] = True
            save_json(output_path, payload)

            # 성공하면 과거 error 파일 제거
            if error_path.exists():
                error_path.unlink()

            print(f"[OK] 저장 완료: {output_path}")
            print(f"[OK] 제목: {payload['title']}")
            print(f"[OK] URL: {payload['url']}")
            return 0

        except Exception as exc:
            last_error = exc
            print(f"[WARN] 수집 실패 {attempt}/{args.max_retries}: {exc}", file=sys.stderr)

            if attempt < args.max_retries:
                time.sleep(max(args.retry_delay, 0))

    if last_error is None:
        last_error = SafeTimesScraperError("알 수 없는 오류")

    if not args.no_error_file:
        save_json(error_path, build_error_payload(target, last_error))
        print(f"[ERROR] 실패 정보 저장: {error_path}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
