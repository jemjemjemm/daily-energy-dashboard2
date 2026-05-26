#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_html_report.py

리포트 JSON(data/reports/YYYY-MM-DD.report.json)을 모바일 대시보드용 HTML로 변환합니다.

운영 원칙:
- 정상 보고서 문구(세이프타임즈, 데이터 없음, A 직접/B 간접/C 참고, 대표 기사 미확인 등)를 금지어로 삭제하지 않습니다.
- 조간 신문 트렌드 대표 기사는 매일 1건 이상 있어야 합니다.
- '오늘의 주요일정'처럼 단순 일정 기사만 대표 기사로 들어가는 것은 제외합니다.
- 본문 문체는 보고서체/명사형 종결을 최대한 유지합니다.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

CRUDE_COLORS = {"Brent": "#1A6FD4", "WTI": "#E24B4A", "Dubai": "#1D9E75"}
PRODUCT_COLORS = {"Gasoline": "#1A6FD4", "Diesel": "#E24B4A", "Naphtha": "#1D9E75"}
PRODUCT_DISPLAY = {"Gasoline": "Gasoline", "Diesel": "Diesel", "Naphtha": "Naphtha"}

# 실제 미완성/오류 문구만 제거합니다.
# 정상 운영 문구인 "세이프타임즈", "데이터 없음", "A 직접", "B 간접", "C 참고"는 넣지 않습니다.
BAD_REPORT_PHRASES = [
    "자동 추출된 일정 항목이 없습니다",
    "본문 구조 확인 및 수동 검수가 필요합니다",
    "원문 자동 매칭 실패",
    "주요일정 원문 데이터 미확보",
    "원문 데이터 없음",
    "가격 데이터 중심 리포트",
    "가격 중심 자동생성",
    "자동 수집된 대표 기사 없음",
    "대표 기사 데이터가 아직 없습니다",
]

FORMAL_REPLACEMENTS = [
    ("필요합니다.", "필요함."),
    ("가능합니다.", "가능함."),
    ("확인됩니다.", "확인됨."),
    ("확인했습니다.", "확인함."),
    ("했습니다.", "함."),
    ("하였습니다.", "함."),
    ("입니다.", "임."),
    ("됩니다.", "됨."),
    ("보입니다.", "보임."),
    ("있습니다.", "있음."),
    ("없습니다.", "없음."),
    ("예상됩니다.", "예상됨."),
    ("전망됩니다.", "전망됨."),
    ("보도했습니다.", "보도함."),
    ("분석했습니다.", "분석함."),
    ("전망했습니다.", "전망함."),
    ("지적했습니다.", "지적함."),
    ("강조했습니다.", "강조함."),
    ("밝혔습니다.", "밝힘."),
]

SCHEDULE_ONLY_TITLE_PATTERNS = [
    "오늘의 주요일정",
    "주요일정]",
    "주요 일정]",
    "오늘의 일정",
]


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt(value: Any) -> str:
    try:
        n = float(value)
    except Exception:
        return "-"
    if not math.isfinite(n) or n == 0:
        return "-"
    return f"{n:.2f}"


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def has_bad_phrase(value: Any) -> bool:
    text = "" if value is None else str(value)
    return any(phrase in text for phrase in BAD_REPORT_PHRASES)


def strip_bad_phrases(text: str) -> str:
    for phrase in BAD_REPORT_PHRASES:
        text = text.replace(phrase, "")
    return text.strip()


def clean_text(value: Any, *, keep_html: bool = False) -> str:
    text = "" if value is None else str(value)
    text = strip_bad_phrases(text)
    if not keep_html:
        text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    for old, new in FORMAL_REPLACEMENTS:
        text = text.replace(old, new)
    return text.strip()


def clean_items(items: Sequence[Mapping[str, Any]] | None, title_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        blob = " ".join(str(v) for v in item.values())
        if has_bad_phrase(blob):
            continue
        copied = dict(item)
        for key in ["title", "text", "description", "summary", "relevance", "press", "category", "org", "time"]:
            if key in copied:
                copied[key] = clean_text(copied[key])
        if any(str(copied.get(k, "")).strip() for k in title_keys):
            cleaned.append(copied)
    return cleaned


def is_schedule_only_article(title: str) -> bool:
    return any(pattern in title for pattern in SCHEDULE_ONLY_TITLE_PATTERNS)


def sanitize_report(report: Dict[str, Any]) -> Dict[str, Any]:
    report = dict(report)
    report["summary"] = clean_items(report.get("summary", []) or [], title_keys=("text",))
    report["issues"] = clean_items(report.get("issues", []) or [], title_keys=("title",))
    report["schedules"] = clean_items(report.get("schedules", []) or [], title_keys=("title",))

    news = dict(report.get("news_trend", {}) or {})
    summary_html = news.get("summary_html")
    if summary_html and not has_bad_phrase(summary_html):
        news["summary_html"] = clean_text(summary_html, keep_html=True)
    else:
        news["summary"] = clean_text(news.get("summary", ""))
        news["summary_html"] = ""

    articles = []
    for article in clean_items(news.get("articles", []) or [], title_keys=("title",)):
        title = clean_text(article.get("title", ""))
        url = str(article.get("url", "") or "").strip()
        if not title or not url:
            continue
        if is_schedule_only_article(title):
            continue
        article["title"] = title
        article["url"] = url
        articles.append(article)
    news["articles"] = articles[:3]

    news["trend_paragraphs"] = [
        clean_text(p) for p in news.get("trend_paragraphs", []) or [] if clean_text(p) and not has_bad_phrase(p)
    ][:3]
    report["news_trend"] = news

    # 내부 품질 메모·출처 원자료는 본문 노출 금지
    report["quality_control"] = {"sources": []}
    return report


def has_valid_report_content(report: Mapping[str, Any]) -> bool:
    issues = clean_items(report.get("issues", []) or [], title_keys=("title",))
    schedules = clean_items(report.get("schedules", []) or [], title_keys=("title",))
    news = report.get("news_trend", {}) or {}
    articles = clean_items(news.get("articles", []) or [], title_keys=("title",))
    valid_articles = [a for a in articles if a.get("title") and a.get("url") and not is_schedule_only_article(str(a.get("title", "")))]
    return bool(issues or schedules or valid_articles)


def section(num: str, title: str, body: str) -> str:
    return f'<section class="section"><h2><span>{esc(num)}</span>{esc(title)}</h2>{body}</section>'


def render_summary(items: Sequence[Mapping[str, Any]]) -> str:
    rows: list[str] = []
    for item in items or []:
        text = clean_text(item.get("text", "")) if isinstance(item, Mapping) else ""
        if not text or has_bad_phrase(text):
            continue
        rows.append(f'<div class="summary-item"><div class="summary-dot"></div><div>{esc(text)}</div></div>')
        if len(rows) >= 3:
            break
    if not rows:
        rows.append('<div class="summary-item"><div class="summary-dot"></div><div>기준일 주요 요약 없음</div></div>')
    return '<div class="summary-body">' + "\n".join(rows) + '</div>'


def render_cards(cards: Sequence[Mapping[str, Any]]) -> str:
    if not cards:
        return '<div class="price-grid"><div class="price-card"><div class="price-label">-</div><div class="price-value">-</div></div></div>'
    rows: list[str] = []
    for c in cards:
        direction = str(c.get("direction", "flat"))
        cls = {"up": "up", "down": "down", "flat": "flat"}.get(direction, "flat")
        symbol = {"up": "▲", "down": "▼", "flat": "－"}.get(direction, "－")
        try:
            change = abs(float(c.get("change", 0)))
        except Exception:
            change = 0.0
        change_text = "-" if fmt(c.get("value")) == "-" else f"{symbol} {fmt(change)}"
        rows.append(
            '<div class="price-card">'
            f'<div class="price-label">{esc(c.get("label", ""))}</div>'
            f'<div class="price-value">{fmt(c.get("value"))}</div>'
            f'<div class="price-unit">{esc(c.get("unit", "$/Bbl"))}</div>'
            f'<div class="price-change {cls}">{esc(change_text)}</div>'
            '</div>'
        )
    return '<div class="price-grid">' + "\n".join(rows) + '</div>'


def render_price_section(prices: Mapping[str, Any]) -> str:
    crude = prices.get("crude", {}) or {}
    products = prices.get("products", {}) or {}
    note = clean_text(prices.get("price_data_note", ""))
    return (
        f'<h3>원유 ($/Bbl) — {esc(crude.get("base_label", ""))} 기준</h3>'
        f'{render_cards(crude.get("cards", []) or [])}'
        f'<h3>석유제품 ($/Bbl) — {esc(products.get("base_label", ""))} 기준</h3>'
        f'{render_cards(products.get("cards", []) or [])}'
        + (f'<p class="note">{esc(note)}</p>' if note else '')
    )


def date_label(date_text: str) -> str:
    try:
        return f"{int(date_text[5:7])}/{int(date_text[8:10])}"
    except Exception:
        return date_text


def get_dates(series: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[str]:
    return sorted({str(p.get("date")) for pts in series.values() for p in pts if p.get("date")})


def get_values(series: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[float]:
    vals: list[float] = []
    for pts in series.values():
        for p in pts:
            try:
                v = float(p.get("value"))
            except Exception:
                continue
            if math.isfinite(v) and v != 0:
                vals.append(v)
    return vals


def render_chart_svg(series: Mapping[str, Sequence[Mapping[str, Any]]], colors: Mapping[str, str]) -> str:
    dates = get_dates(series)
    vals = get_values(series)
    if not dates or not vals:
        return '<div class="empty-chart">표시 가능한 그래프 데이터 없음</div>'

    lo, hi = min(vals), max(vals)
    if lo == hi:
        lo -= 1
        hi += 1
    pad = max((hi - lo) * 0.12, 1)
    lo = max(0, lo - pad)
    hi += pad

    width, height = 440, 230
    left, right, top, bottom = 38, 430, 12, 198
    date_idx = {d: i for i, d in enumerate(dates)}

    def x(idx: int) -> float:
        return (left + right) / 2 if len(dates) <= 1 else left + (right - left) * idx / (len(dates) - 1)

    def y(value: float) -> float:
        return bottom - ((value - lo) / (hi - lo)) * (bottom - top)

    parts: list[str] = [f'<svg viewBox="0 0 {width} {height}" class="chart-svg" role="img">']
    for i in range(6):
        yy = bottom - (bottom - top) * i / 5
        label = lo + (hi - lo) * i / 5
        parts.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" class="grid" />')
        parts.append(f'<text x="4" y="{yy + 4:.1f}" class="axis-label">{label:.0f}</text>')

    tick_idxs = sorted({0, len(dates) - 1, max(0, len(dates) // 3), max(0, (len(dates) * 2) // 3)})
    for i in tick_idxs:
        parts.append(f'<text x="{x(i):.1f}" y="222" class="axis-label" text-anchor="middle">{esc(date_label(dates[i]))}</text>')

    for name, pts in series.items():
        poly: list[str] = []
        for p in pts or []:
            d = str(p.get("date", ""))
            if d not in date_idx:
                continue
            try:
                v = float(p.get("value"))
            except Exception:
                continue
            if not math.isfinite(v) or v == 0:
                continue
            poly.append(f'{x(date_idx[d]):.1f},{y(v):.1f}')
        if poly:
            color = colors.get(name, "#333333")
            parts.append(f'<polyline points="{" ".join(poly)}" fill="none" stroke="{esc(color)}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />')
    parts.append('</svg>')
    return '<div class="chart-wrap">' + "\n".join(parts) + '</div>'


def render_legend(names: Sequence[str], colors: Mapping[str, str], display: Mapping[str, str] | None = None) -> str:
    rows = []
    for name in names:
        label = (display or {}).get(name, name)
        rows.append(f'<span class="legend"><i style="background:{esc(colors.get(name, "#333"))}"></i>{esc(label)}</span>')
    return '<div class="legend-wrap">' + "".join(rows) + '</div>'


def render_chart_section(num: str, title: str, series: Mapping[str, Sequence[Mapping[str, Any]]], colors: Mapping[str, str], keys: Sequence[str], display: Mapping[str, str] | None = None) -> str:
    ordered_series = {key: series.get(key, []) or [] for key in keys}
    body = render_legend(keys, colors, display) + render_chart_svg(ordered_series, colors)
    return section(num, title, body)


def render_issues(items: Sequence[Mapping[str, Any]]) -> str:
    rows: list[str] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        title = clean_text(item.get("title", ""))
        desc = clean_text(item.get("description", ""))
        category = clean_text(item.get("category", "")) or "정책"
        if not title or has_bad_phrase(title + " " + desc + " " + category):
            continue
        links = item.get("links", []) or item.get("related_links", []) or []
        link_rows: list[str] = []
        if isinstance(links, list):
            for link in links[:3]:
                if not isinstance(link, Mapping):
                    continue
                url = str(link.get("url", "") or "").strip()
                label = clean_text(link.get("label") or link.get("title") or "관련 자료")
                if url and label and not has_bad_phrase(label + " " + url):
                    link_rows.append(f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(label)}</a>')
        link_html = '<div class="links">관련 링크 ' + " ".join(link_rows) + '</div>' if link_rows else ""
        rows.append(
            '<div class="issue-card">'
            f'<div class="issue-tag">{esc(category)}</div>'
            f'<div class="issue-title">{esc(title)}</div>'
            f'<div class="issue-desc">{esc(desc)}</div>'
            f'{link_html}'
            '</div>'
        )
    if not rows:
        rows.append('<div class="issue-card"><div class="issue-title">주요 이해관계자 동향 없음</div></div>')
    return '<div class="issue-list">' + "\n".join(rows) + '</div>'


def render_schedules(items: Sequence[Mapping[str, Any]]) -> str:
    rows: list[str] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        time = clean_text(item.get("time", ""))
        org = clean_text(item.get("org", ""))
        title = clean_text(item.get("title", ""))
        rel = clean_text(item.get("relevance", ""))
        if not title or has_bad_phrase(title + " " + rel):
            continue
        rows.append(
            '<div class="schedule-row">'
            f'<div class="schedule-time">{esc(time)}</div>'
            f'<div class="schedule-org">{esc(org)}</div>'
            '<div class="schedule-main">'
            f'<div>{esc(title)}</div>'
            + (f'<div class="schedule-rel">{esc(rel)}</div>' if rel else '')
            + '</div></div>'
        )
    if not rows:
        rows.append('<div class="schedule-row"><div class="schedule-main"><div>금일 주요 일정 데이터 없음</div></div></div>')
    return '<div class="schedule-list">' + "\n".join(rows) + '</div>'


def render_news(report: Mapping[str, Any]) -> str:
    news = report.get("news_trend", {}) or {}
    articles: list[dict[str, Any]] = []
    for article in news.get("articles", []) or []:
        if not isinstance(article, Mapping):
            continue
        title = clean_text(article.get("title", ""))
        url = str(article.get("url", "") or "").strip()
        if not title or not url or has_bad_phrase(title + " " + url) or is_schedule_only_article(title):
            continue
        copied = dict(article)
        copied["title"] = title
        copied["summary"] = clean_text(copied.get("summary", ""))
        copied["press"] = clean_text(copied.get("press", ""))
        copied["published_at_kst"] = clean_text(copied.get("published_at_kst", ""))
        articles.append(copied)
    articles = articles[:3]

    if not articles:
        raise ValueError("조간 신문 트렌드 대표 기사 0건: HTML을 생성하지 않습니다.")

    raw_summary = clean_text(news.get("summary_html") or news.get("summary", ""), keep_html=True)
    if not raw_summary:
        titles = [clean_text(a.get("title", "")) for a in articles[:3]]
        raw_summary = "주요 매체가 " + " ".join("△" + title for title in titles if title) + " 등을 중심으로 보도."

    trend_paras = [clean_text(p) for p in news.get("trend_paragraphs", []) or [] if clean_text(p)]
    if not trend_paras:
        for article in articles:
            press = clean_text(article.get("press", "")) or "해당 매체"
            desc = clean_text(article.get("summary", "")) or clean_text(article.get("title", ""))
            if desc and not desc.endswith("."):
                desc += "."
            trend_paras.append(f"{press}는 {desc}")

    trend_html = '<div class="trend-summary">' + esc(raw_summary).replace("&lt;br/&gt;", "<br/>").replace("&lt;br&gt;", "<br/>")
    for para in trend_paras[:3]:
        match = re.match(r"([^는]{2,20})는\s+(.+)", para)
        if match:
            trend_html += f'<p><b>{esc(match.group(1))}</b>는 {esc(match.group(2))}</p>'
        else:
            trend_html += f'<p>{esc(para)}</p>'
    trend_html += '</div>'

    rows: list[str] = []
    for article in articles:
        rows.append(
            '<a class="article-card" '
            f'href="{esc(article.get("url", ""))}" target="_blank" rel="noopener">'
            f'<div class="article-title">{esc(article.get("title", ""))}</div>'
            f'<div class="article-meta">{esc(article.get("press", ""))} {esc(article.get("published_at_kst", ""))}</div>'
            + (f'<div class="article-summary">{esc(article.get("summary", ""))}</div>' if article.get("summary") else '')
            + '</a>'
        )

    return (
        trend_html
        + '<h3>대표 기사</h3>'
        + '<div class="article-list">'
        + "\n".join(rows)
        + '</div>'
        + '<p class="note">※ 조간 트렌드는 웹 확인 가능한 기준일 오전 보도 중 정유·석유화학·LNG 업계 관련성이 높은 기사 중심 작성. 기사 내용 밖의 업계 영향 평가는 작성자 해석.</p>'
    )


def css() -> str:
    return """
:root{--bg:#f5f6f8;--card:#fff;--text:#1f2937;--muted:#6b7280;--line:#e5e7eb;--blue:#1A6FD4;--red:#E24B4A;--green:#1D9E75;--shadow:0 8px 24px rgba(15,23,42,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",Arial,sans-serif;line-height:1.55}.page{max-width:920px;margin:0 auto;padding:20px 14px 56px}.hero{background:linear-gradient(135deg,#12376b,#1A6FD4);color:#fff;border-radius:24px;padding:24px;box-shadow:var(--shadow)}.eyebrow{font-size:13px;opacity:.85;margin-bottom:4px}.hero h1{font-size:26px;line-height:1.25;margin:0}.header-date{margin-top:10px;font-size:14px;opacity:.9}.section{background:var(--card);border-radius:22px;margin-top:16px;padding:20px;box-shadow:var(--shadow)}h2{display:flex;gap:10px;align-items:center;margin:0 0 16px;font-size:20px}h2 span{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:50%;background:#e8f1ff;color:var(--blue);font-size:14px}h3{font-size:16px;margin:18px 0 10px}.summary-body{display:grid;gap:10px}.summary-item{display:flex;gap:10px;background:#f9fafb;border:1px solid var(--line);border-radius:14px;padding:13px}.summary-dot{width:8px;height:8px;border-radius:50%;background:var(--blue);margin-top:8px;flex:0 0 8px}.price-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.price-card{border:1px solid var(--line);border-radius:16px;padding:14px;background:#fbfdff}.price-label{font-size:13px;color:var(--muted)}.price-value{font-size:24px;font-weight:800;margin-top:4px}.price-unit,.price-change{font-size:12px;color:var(--muted)}.price-change.up{color:var(--red)}.price-change.down{color:var(--blue)}.price-change.flat{color:var(--muted)}.legend-wrap{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px}.legend{font-size:13px;color:var(--muted);display:inline-flex;align-items:center;gap:5px}.legend i{display:inline-block;width:10px;height:10px;border-radius:50%}.chart-wrap{overflow-x:auto}.chart-svg{width:100%;min-width:420px}.grid{stroke:#e5e7eb;stroke-width:1}.axis-label{font-size:11px;fill:#6b7280}.empty-chart{border:1px dashed var(--line);border-radius:16px;padding:28px;text-align:center;color:var(--muted)}.issue-list,.schedule-list,.article-list{display:grid;gap:10px}.issue-card,.schedule-row,.article-card{border:1px solid var(--line);border-radius:16px;padding:14px;background:#fff;text-decoration:none;color:inherit}.issue-tag{display:inline-block;font-size:12px;color:var(--blue);background:#e8f1ff;border-radius:999px;padding:3px 8px;margin-bottom:8px}.issue-title,.article-title{font-weight:800}.issue-desc,.article-summary,.schedule-rel{margin-top:6px;color:#4b5563;font-size:14px}.links{margin-top:10px;font-size:13px}.links a{margin-right:8px;color:var(--blue)}.schedule-row{display:grid;grid-template-columns:76px 96px 1fr;gap:10px}.schedule-time,.schedule-org,.article-meta{color:var(--muted);font-size:13px}.trend-summary{border:1px solid var(--line);border-radius:16px;padding:14px;background:#f9fafb;margin-bottom:14px}.trend-summary p{margin:8px 0 0}.note{font-size:12px;color:var(--muted);margin:12px 0 0}.footer{color:var(--muted);font-size:12px;text-align:center;margin-top:20px}@media(max-width:640px){.page{padding:12px 10px 40px}.hero{border-radius:20px}.hero h1{font-size:22px}.section{padding:16px;border-radius:18px}.price-grid{grid-template-columns:1fr}.schedule-row{grid-template-columns:1fr}.schedule-time,.schedule-org{font-weight:700}.article-card{display:block}}
"""


def render_html(report: Mapping[str, Any]) -> str:
    date = clean_text(report.get("date") or report.get("base_date") or "")
    title_date = clean_text(report.get("display_date") or report.get("date_label") or date)
    report_title = clean_text(report.get("title") or "Daily Issue Report")
    prices = report.get("prices", {}) or report.get("price", {}) or {}
    crude_series = (prices.get("crude", {}) or {}).get("series", {}) or report.get("crude_series", {}) or {}
    product_series = (prices.get("products", {}) or {}).get("series", {}) or report.get("product_series", {}) or {}

    body = "\n".join(
        [
            '<!doctype html>',
            '<html lang="ko">',
            '<head>',
            '<meta charset="utf-8"/>',
            '<meta name="viewport" content="width=device-width, initial-scale=1"/>',
            f'<title>{esc(report_title)} — {esc(title_date)}</title>',
            f'<style>{css()}</style>',
            '</head>',
            '<body>',
            '<main class="page">',
            '<header class="hero">',
            '<div class="eyebrow">정유·석유화학·LNG Daily Monitoring</div>',
            f'<h1>{esc(report_title)}</h1>',
            f'<div class="header-date">{esc(title_date)}</div>',
            '</header>',
            section("1", "Summary", render_summary(report.get("summary", []) or [])),
            section("2", "유가 동향", render_price_section(prices)),
            render_chart_section("3", "원유 가격 추이", crude_series, CRUDE_COLORS, ["Brent", "WTI", "Dubai"]),
            render_chart_section("4", "석유제품 가격 추이", product_series, PRODUCT_COLORS, ["Gasoline", "Diesel", "Naphtha"], PRODUCT_DISPLAY),
            section("5", "전일 주요 이슈", render_issues(report.get("issues", []) or [])),
            section("6", "금일 주요 일정", render_schedules(report.get("schedules", []) or [])),
            section("7", "기준일 조간 신문 트렌드", render_news(report)),
            f'<div class="footer">Generated report file for {esc(date)}</div>',
            '</main>',
            '</body>',
            '</html>',
        ]
    )
    return body


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily Issue Report HTML 생성")
    parser.add_argument("--input", "-i", help="입력 report JSON 경로")
    parser.add_argument("--output", "-o", help="출력 HTML 경로")
    parser.add_argument("--date", help="YYYY-MM-DD. --input/--output 생략 시 data/reports 및 docs/reports 경로에 사용")
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.input and args.output:
        return Path(args.input), Path(args.output)
    if not args.date:
        raise ValueError("--date 또는 --input/--output을 지정해야 합니다.")
    date = args.date
    return Path("data/reports") / f"{date}.report.json", Path("docs/reports") / f"{date}.html"


def main() -> int:
    args = parse_args()
    input_path, output_path = resolve_paths(args)
    report = sanitize_report(read_json(input_path))

    if not has_valid_report_content(report):
        raise ValueError("유효한 이슈/일정/조간 기사 데이터가 없어 HTML을 생성하지 않습니다.")

    html_text = render_html(report)
    if any(phrase in html_text for phrase in BAD_REPORT_PHRASES):
        raise ValueError("미완성/오류 문구가 HTML에 남아 있어 생성을 중단합니다.")

    atomic_write(output_path, html_text)
    print(f"[OK] HTML 생성 완료: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
