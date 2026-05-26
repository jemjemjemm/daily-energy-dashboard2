#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_html_report.py

리포트 JSON(data/reports/YYYY-MM-DD.report.json)을 모바일 대시보드용 HTML로 변환합니다.
- 보고서 생성/뉴스 수집/가격 병합 로직은 건드리지 않고, 최종 HTML 양식만 변경합니다.
- 과거 전체 레포트와 향후 자동 발간 레포트 모두 같은 템플릿으로 렌더링됩니다.
- 가격 카드/그래프, 일정, 이슈, 조간 기사 검증 구조는 유지합니다.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

CRUDE_COLORS = {"Brent": "#1A6FD4", "WTI": "#E24B4A", "Dubai": "#1D9E75"}
PRODUCT_COLORS = {"Gasoline": "#1A6FD4", "Diesel": "#E24B4A", "Naphtha": "#1D9E75"}
PRODUCT_DISPLAY = {"Gasoline": "Gasoline", "Diesel": "Diesel", "Naphtha": "Naphtha"}

BAD_REPORT_PHRASES = [
    "자동 추출된 일정 항목이 없습니다",
    "본문 구조 확인 및 수동 검수가 필요합니다",
    "세이프타임즈",
    "원문 자동 매칭 실패",
    "주요일정 원문 데이터 미확보",
    "원문 데이터 없음",
    "데이터 없음",
    "가격 데이터 중심 리포트",
    "가격 중심 자동생성",
    "Data 없음",
    "No data",
    "정유·석유화학·LNG 관련 조간 기사 후보를 찾지 못했습니다",
    "조간 기사 후보를 찾지 못했습니다",
    "자동 수집된 대표 기사 없음",
    "대표 기사 데이터가 아직 없습니다",
    "대표 기사 미확인",
    "기준일 조간 기준 주요 보도 없음",
    "기준일 조간 기준 정유·석유화학·LNG 관련 대표 기사 미확인",
    "일정 관련성 평가는",
    "A 직접",
    "B 간접",
    "C 참고",
]

FORMAL_REPLACEMENTS = [
    ("했습니다.", "함."),
    ("하였습니다.", "함."),
    ("입니다.", "임."),
    ("됩니다.", "됨."),
    ("필요합니다.", "필요"),
    ("가능합니다.", "가능"),
    ("확인됩니다.", "확인"),
    ("확인했습니다.", "확인"),
    ("보도했습니다.", "보도"),
    ("분석했습니다.", "분석"),
    ("전망했습니다.", "전망"),
    ("지적했습니다.", "지적"),
    ("강조했습니다.", "강조"),
    ("밝혔습니다.", "밝힘"),
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
        "w", encoding="utf-8", dir=str(path.parent), delete=False,
        prefix=f".{path.name}.", suffix=".tmp",
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
    text = re.sub(r"\s+", " ", text).strip()
    if not keep_html:
        text = re.sub(r"<[^>]+>", "", text).strip()
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
        for key in ["title", "text", "description", "summary", "relevance", "press", "category", "org"]:
            if key in copied:
                copied[key] = clean_text(copied[key])
        if any(str(copied.get(k, "")).strip() for k in title_keys):
            cleaned.append(copied)
    return cleaned


def sanitize_report(report: Dict[str, Any]) -> Dict[str, Any]:
    report = dict(report)
    report["summary"] = clean_items(report.get("summary", []) or [], title_keys=("text",))
    report["issues"] = clean_items(report.get("issues", []) or [], title_keys=("title",))
    report["schedules"] = clean_items(report.get("schedules", []) or [], title_keys=("title",))

    news = dict(report.get("news_trend", {}) or {})
    summary_html = news.get("summary_html")
    if summary_html and not has_bad_phrase(summary_html):
        news["summary_html"] = clean_text(summary_html, keep_html=True)
    elif has_bad_phrase(summary_html or news.get("summary", "")):
        news["summary"] = ""
        news["summary_html"] = ""
    else:
        news["summary"] = clean_text(news.get("summary", ""))

    news["articles"] = [
        a for a in clean_items(news.get("articles", []) or [], title_keys=("title",))
        if a.get("title") and a.get("url") and "오늘의 주요일정" not in str(a.get("title", ""))
    ][:3]
    news["trend_paragraphs"] = [
        clean_text(p) for p in news.get("trend_paragraphs", []) or []
        if clean_text(p) and not has_bad_phrase(p)
    ][:3]
    report["news_trend"] = news

    # 양식 변경 시 내부 품질 메모·출처 목록은 본문 노출 금지.
    report["quality_control"] = {"sources": []}
    return report


def has_valid_report_content(report: Mapping[str, Any]) -> bool:
    issues = clean_items(report.get("issues", []) or [], title_keys=("title",))
    schedules = clean_items(report.get("schedules", []) or [], title_keys=("title",))
    news = report.get("news_trend", {}) or {}
    articles = clean_items(news.get("articles", []) or [], title_keys=("title",))
    valid_articles = [a for a in articles if a.get("title") and a.get("url")]
    return bool(issues or schedules or valid_articles)


def section(num: str, title: str, body: str) -> str:
    return (
        f'<div class="section"><div class="section-header">'
        f'<span class="section-num">{esc(num)}</span><span class="section-title">{esc(title)}</span>'
        f'</div>{body}</div>'
    )


def render_summary(items: Sequence[Mapping[str, Any]]) -> str:
    rows: list[str] = []
    for item in items or []:
        text = clean_text(item.get("text", "")) if isinstance(item, Mapping) else ""
        if not text or has_bad_phrase(text):
            continue
        rows.append(
            '<div class="summary-item"><div class="summary-dot"></div>'
            f'<div>{esc(text)}</div></div>'
        )
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
            f'<div class="price-change"><span class="{cls}">{esc(change_text)}</span></div>'
            '</div>'
        )
    return '<div class="price-grid">' + "\n".join(rows) + '</div>'


def render_price_section(prices: Mapping[str, Any]) -> str:
    crude = prices.get("crude", {}) or {}
    products = prices.get("products", {}) or {}
    note = clean_text(prices.get("price_data_note", ""))
    return (
        f'<div class="price-section-label">원유 ($/Bbl) — {esc(crude.get("base_label", ""))} 기준</div>'
        f'{render_cards(crude.get("cards", []) or [])}'
        '<div class="divider"></div>'
        f'<div class="price-section-label">석유제품 ($/Bbl) — {esc(products.get("base_label", ""))} 기준</div>'
        f'{render_cards(products.get("cards", []) or [])}'
        + (f'<div class="note">{esc(note)}</div>' if note else '')
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


def chart_js_rows(series: Mapping[str, Sequence[Mapping[str, Any]]], keys: Sequence[str]) -> list[dict[str, Any]]:
    dates = get_dates(series)
    by_date: dict[str, dict[str, Any]] = {d: {"date": d, "label": date_label(d)} for d in dates}
    for key in keys:
        for p in series.get(key, []) or []:
            d = str(p.get("date", ""))
            if d not in by_date:
                continue
            try:
                v = float(p.get("value"))
            except Exception:
                v = None
            by_date[d][key] = v if v and math.isfinite(v) else None
    for d in dates:
        for key in keys:
            by_date[d].setdefault(key, None)
    return [by_date[d] for d in dates]


def render_chart_svg(series: Mapping[str, Sequence[Mapping[str, Any]]], colors: Mapping[str, str], chart_id: str, line_id: str) -> str:
    dates = get_dates(series)
    vals = get_values(series)
    if not dates or not vals:
        return '<div class="chart-box"><div class="note">표시 가능한 그래프 데이터 없음</div></div>'

    lo, hi = min(vals), max(vals)
    if lo == hi:
        lo -= 1
        hi += 1
    pad = max((hi - lo) * 0.12, 1)
    lo = max(0, lo - pad)
    hi += pad

    W, H = 440, 230
    L, R, T, B = 38, 430, 12, 198
    date_idx = {d: i for i, d in enumerate(dates)}

    def x(idx: int) -> float:
        return (L + R) / 2 if len(dates) <= 1 else L + (R - L) * idx / (len(dates) - 1)

    def y(v: float) -> float:
        return B - ((v - lo) / (hi - lo)) * (B - T)

    parts: list[str] = [
        f'<svg aria-label="가격 추이 그래프" class="chart-svg" preserveAspectRatio="xMidYMid meet" role="img" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">'
    ]
    for i in range(6):
        yy = B - (B - T) * i / 5
        label = lo + (hi - lo) * i / 5
        parts.append(f'<line stroke="rgba(0,0,0,0.07)" stroke-width="1" x1="{L}" x2="{R}" y1="{yy:.1f}" y2="{yy:.1f}"></line>')
        parts.append(f'<text fill="#888" font-size="9" text-anchor="end" x="34" y="{yy+3:.1f}">{label:.0f}</text>')

    tick_idxs = sorted({0, len(dates)-1, max(0, len(dates)//3), max(0, (len(dates)*2)//3)})
    for i in tick_idxs:
        parts.append(f'<text fill="#888" font-size="9" text-anchor="middle" x="{x(i):.1f}" y="221">{esc(date_label(dates[i]))}</text>')

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
            parts.append(
                f'<polyline points="{" ".join(poly)}" fill="none" stroke="{colors.get(name, "#1A6FD4")}" '
                'stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></polyline>'
            )

    parts.append(f'<line id="{esc(line_id)}" opacity="0" stroke="#0A2444" stroke-width="1" x1="{L}" x2="{L}" y1="{T}" y2="{B}"></line>')
    parts.append(f'<rect fill="transparent" height="{B-T}" width="{R-L}" x="{L}" y="{T}"></rect>')
    parts.append('</svg>')
    return f'<div class="chart-box" id="{esc(chart_id)}">' + "\n".join(parts) + f'<div class="tooltip" id="{esc(chart_id)}Tip"></div></div>'


def render_legend(names: Sequence[str], colors: Mapping[str, str], display: Mapping[str, str] | None = None) -> str:
    rows = []
    for n in names:
        label = (display or {}).get(n, n)
        rows.append(f'<div class="legend-item"><div class="legend-dot" style="background:{colors.get(n, "#1A6FD4")}"></div>{esc(label)}</div>')
    return '<div class="chart-legend">' + "".join(rows) + '</div>'


def render_chart_section(num: str, title: str, series: Mapping[str, Sequence[Mapping[str, Any]]], colors: Mapping[str, str], keys: Sequence[str], display: Mapping[str, str] | None, chart_id: str, line_id: str) -> str:
    body = (
        '<div class="chart-wrap">'
        + render_legend(keys, colors, display)
        + render_chart_svg(series, colors, chart_id, line_id)
        + '</div>'
    )
    return section(num, title, body)


def render_issues(items: Sequence[Mapping[str, Any]]) -> str:
    rows: list[str] = []
    for i in items or []:
        if not isinstance(i, Mapping):
            continue
        title = clean_text(i.get("title", ""))
        desc = clean_text(i.get("description", ""))
        category = clean_text(i.get("category", "")) or "정책"
        if not title or has_bad_phrase(title + " " + desc + " " + category):
            continue
        links = i.get("links", []) or i.get("related_links", []) or []
        link_rows: list[str] = []
        if isinstance(links, list):
            for link in links[:3]:
                if not isinstance(link, Mapping):
                    continue
                url = str(link.get("url", "") or "").strip()
                label = clean_text(link.get("label") or link.get("title") or "관련 자료")
                if url and label and not has_bad_phrase(label + " " + url):
                    link_rows.append(f'<a href="{esc(url)}" rel="noopener" target="_blank">{esc(label)}</a>')
        link_html = ''
        if link_rows:
            link_html = '<div class="issue-links"><span>관련 링크</span>' + "".join(link_rows) + '</div>'
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
    for i in items or []:
        if not isinstance(i, Mapping):
            continue
        time = clean_text(i.get("time", ""))
        org = clean_text(i.get("org", ""))
        title = clean_text(i.get("title", ""))
        rel = clean_text(i.get("relevance", ""))
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
    for a in news.get("articles", []) or []:
        if not isinstance(a, Mapping):
            continue
        title = clean_text(a.get("title", ""))
        url = str(a.get("url", "") or "").strip()
        if title and url and not has_bad_phrase(title + " " + url):
            copied = dict(a)
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
        raw_summary = "주요 매체가 " + " ".join("△" + t for t in titles if t) + " 등을 중심으로 보도."

    trend_paras = [clean_text(p) for p in news.get("trend_paragraphs", []) or [] if clean_text(p)]
    if not trend_paras:
        for a in articles:
            press = clean_text(a.get("press", "")) or "해당 매체"
            desc = clean_text(a.get("summary", "")) or clean_text(a.get("title", ""))
            if desc and not desc.endswith("."):
                desc += "."
            trend_paras.append(f"{press}는 {desc}")

    trend_html = '<div class="news-trend">' + esc(raw_summary).replace("&lt;br/&gt;", "<br/>").replace("&lt;br&gt;", "<br/>")
    for para in trend_paras[:3]:
        m = re.match(r"([^는]{2,20})는\s+(.+)", para)
        if m:
            trend_html += f'<br/><br/><strong>{esc(m.group(1))}</strong>는 {esc(m.group(2))}'
        else:
            trend_html += f'<br/><br/>{esc(para)}'
    trend_html += '</div>'

    rows: list[str] = []
    for a in articles:
        url = str(a.get("url", "") or "")
        title = esc(a.get("title", ""))
        press = esc(a.get("press", ""))
        summary = esc(a.get("summary", ""))
        rows.append(
            f'<a class="news-link" href="{esc(url)}" rel="noopener" target="_blank">'
            f'<div class="news-link-title">{title}</div>'
            f'<div class="news-link-press">{press}</div>'
            + (f'<div class="news-link-desc">{summary}</div>' if summary else '')
            + f'<div class="news-url">{esc(url)}</div>'
            '</a>'
        )

    return (
        '<div class="news-body">'
        + trend_html
        + '<div class="news-separator"></div><div class="news-links-title">대표 기사</div>'
        + "\n".join(rows)
        + '</div>'
        + '<div class="fact-note">※ 조간 트렌드는 웹 확인 가능한 기준일 오전 보도 중 정유·석유화학·LNG 업계 관련성이 높은 기사 중심 작성. 기사 내용 밖의 업계 영향 평가는 작성자 해석</div>'
    )


def css() -> str:
    return """
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
*{box-sizing:border-box}body{margin:0;padding:16px;background:#F4F5F7;color:#1A1A1A;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;font-size:14px;line-height:1.6;word-break:keep-all;overflow-wrap:anywhere}.container{max-width:480px;margin:0 auto}.header{background:#0A2444;color:#fff;padding:18px 16px 14px;border-radius:12px 12px 0 0}.header-top{display:flex;justify-content:space-between;gap:12px}.header-title{font-size:20px;font-weight:700}.header-date{font-size:12px;color:rgba(255,255,255,.58);margin-top:3px}.header-badge{font-size:11px;background:rgba(255,255,255,.12);border-radius:20px;padding:4px 10px;height:fit-content;white-space:nowrap}.section{background:#fff;border:1px solid #E5E7EB;border-radius:12px;margin:10px 0;overflow:hidden}.section-header{display:flex;align-items:center;gap:8px;padding:11px 16px;border-bottom:1px solid #E5E7EB;background:#F8F9FA}.section-num{font-size:11px;font-weight:700;color:#fff;background:#0A2444;border-radius:4px;padding:2px 7px;min-width:24px;text-align:center}.section-title{font-size:14px;font-weight:700}.summary-body,.news-body{padding:14px 16px}.summary-item{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #F0F0F0;font-size:13px;line-height:1.65}.summary-item:last-child{border-bottom:none}.summary-dot{flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:#1A6FD4;margin-top:8px}.price-section-label{font-size:12px;font-weight:500;color:#666;padding:12px 16px 6px}.price-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:0 16px 14px}.price-card{background:#F8F9FA;border-radius:8px;padding:10px 8px;text-align:center}.price-label{font-size:11px;color:#666;margin-bottom:4px}.price-value{font-size:18px;font-weight:700;line-height:1}.price-unit{font-size:10px;color:#999;margin-top:2px}.price-change{font-size:11px;margin-top:3px}.up{color:#C0392B}.down{color:#0A7B4E}.flat{color:#888}.divider{height:1px;background:#F0F0F0;margin:0 16px 4px}.chart-wrap{padding:12px 14px;position:relative}.chart-legend{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px;font-size:12px;color:#666}.legend-item{display:flex;align-items:center;gap:5px}.legend-dot{width:12px;height:3px;border-radius:2px}.chart-box{position:relative;width:100%;min-height:245px;touch-action:pan-y;-webkit-user-select:none;user-select:none;overflow:visible}.chart-svg{width:100%;height:auto;display:block;overflow:visible}.tooltip{position:absolute;z-index:20;display:none;min-width:132px;max-width:215px;background:rgba(10,36,68,.96);color:#fff;border-radius:8px;padding:8px 10px;font-size:11px;line-height:1.45;pointer-events:none;box-shadow:0 6px 18px rgba(0,0,0,.18)}.tooltip .date{font-weight:700;margin-bottom:4px}.tooltip-row{display:flex;justify-content:space-between;gap:12px}.issue-list,.schedule-list{padding:10px 12px}.issue-card{background:#F8F9FA;border-radius:8px;padding:12px 14px;margin-bottom:8px;border-left:3px solid #1A6FD4}.issue-card:last-child{margin-bottom:0}.issue-tag{display:inline-block;font-size:10px;font-weight:700;background:#E6F1FB;color:#185FA5;border-radius:3px;padding:2px 6px;margin-bottom:6px}.issue-title{font-size:13px;font-weight:700;margin-bottom:5px;line-height:1.5}.issue-desc{font-size:12px;color:#444;line-height:1.65}.schedule-row{display:flex;align-items:flex-start;gap:8px;padding:9px 0;border-bottom:1px solid #F0F0F0}.schedule-row:last-child{border-bottom:none}.schedule-time{flex:0 0 38px;font-size:11px;font-weight:700;color:#185FA5;margin-top:1px}.schedule-org{flex:0 0 48px;font-size:10px;background:#F0F1F3;border:1px solid #E0E0E0;border-radius:3px;padding:1px 4px;color:#555;text-align:center}.schedule-main{flex:1;font-size:12px;line-height:1.5}.schedule-rel{font-size:11px;color:#777;margin-top:2px}.note{padding:0 16px 14px;font-size:11px;color:#999}.news-trend{font-size:13px;line-height:1.75;margin-bottom:14px}.news-trend strong{font-weight:700;color:#0A2444}.news-separator{height:1px;background:#F0F0F0;margin:12px 0}.news-links-title{font-size:11px;font-weight:700;color:#999;letter-spacing:.5px;margin-bottom:8px}.news-link{display:block;padding:9px 0;border-bottom:1px solid #F0F0F0;text-decoration:none;color:inherit}.news-link-title{font-size:13px;font-weight:600;color:#0A2444;line-height:1.45;text-decoration:underline}.news-link-press{font-size:11px;color:#888;margin:2px 0}.news-link-desc{font-size:11px;color:#555;line-height:1.55}.news-url{font-size:10px;color:#999;word-break:break-all;margin-top:4px}.fact-note{font-size:11px;color:#888;background:#F8F9FA;border-top:1px solid #E5E7EB;padding:10px 16px}.footer{text-align:center;padding:12px;font-size:11px;color:#aaa;border-top:1px solid #E5E7EB;margin-top:4px}.issue-links{margin-top:9px;display:flex;flex-direction:column;gap:4px;font-size:11px}.issue-links a{color:#0A2444;text-decoration:underline;word-break:break-all}.issue-links span{color:#777}.issue-links .link-note{color:#777;font-size:10.5px;line-height:1.45}@media(max-width:430px){body{padding:10px}.header-title{font-size:18px}.header-badge{font-size:10px;padding:4px 8px}.section-header{padding:10px 12px}.summary-body,.news-body{padding:12px}.price-grid{gap:6px;padding:0 12px 12px}.price-card{padding:9px 4px}.price-value{font-size:16px}.chart-wrap{padding:10px 8px}.chart-box{min-height:230px}.chart-legend{gap:8px;font-size:11px;margin-left:4px}.schedule-org{flex-basis:42px}.tooltip{font-size:10.5px;min-width:124px}}
""".strip()


def chart_script(crude_rows: list[dict[str, Any]], product_rows: list[dict[str, Any]]) -> str:
    return f"""
<script>
const crudeData = {json.dumps(crude_rows, ensure_ascii=False)};
const productData = {json.dumps(product_rows, ensure_ascii=False)};
const chartConfigs = {{
  crude: {{ el:'crudeChart', tooltip:'crudeChartTip', line:'crudeLine', data: crudeData, keys:[['Brent','Brent'],['WTI','WTI'],['Dubai','Dubai']] }},
  product: {{ el:'productChart', tooltip:'productChartTip', line:'productLine', data: productData, keys:[['Gasoline','Gasoline'],['Diesel','Diesel'],['Naphtha','Naphtha']] }}
}};
(function(){{
  const W=440, ml=38, mr=10, pw=W-ml-mr;
  function attachTooltip(cfg){{
    const box=document.getElementById(cfg.el), tip=document.getElementById(cfg.tooltip), line=document.getElementById(cfg.line);
    if(!box || !tip) return;
    function showAt(clientX, clientY){{
      const rect=box.getBoundingClientRect(); if(!rect.width) return;
      const relX=Math.max(ml, Math.min(W-mr, (clientX-rect.left)/rect.width*W));
      const idx=Math.max(0, Math.min(cfg.data.length-1, Math.round((relX-ml)/pw*(cfg.data.length-1))));
      const r=cfg.data[idx] || {{label:'-'}};
      const xx=ml + (cfg.data.length<=1 ? 0 : idx/(cfg.data.length-1)*pw);
      if(line){{ line.setAttribute('x1',xx); line.setAttribute('x2',xx); line.setAttribute('opacity','0.45'); }}
      let html='<div class="date">'+(r.label||'-')+'</div>';
      cfg.keys.forEach(function(k){{ const v=r[k[0]]; html+='<div class="tooltip-row"><span>'+k[1]+'</span><b>'+((v===null||v===undefined||v===0)?'-':Number(v).toFixed(2))+'</b></div>'; }});
      tip.innerHTML=html; tip.style.display='block';
      let left=(clientX-rect.left)+12, top=(clientY-rect.top)-10;
      const tw=tip.offsetWidth||150, th=tip.offsetHeight||104;
      if(left+tw>rect.width) left=(clientX-rect.left)-tw-12; if(left<4) left=4;
      if(top+th>rect.height) top=rect.height-th-4; if(top<4) top=4;
      tip.style.left=left+'px'; tip.style.top=top+'px';
    }}
    function hide(){{ if(line) line.setAttribute('opacity','0'); tip.style.display='none'; }}
    box.addEventListener('mousemove', e=>showAt(e.clientX,e.clientY), {{passive:true}});
    box.addEventListener('mouseleave', hide, {{passive:true}});
    box.addEventListener('touchstart', e=>{{ if(e.touches&&e.touches[0]) showAt(e.touches[0].clientX,e.touches[0].clientY); }}, {{passive:true}});
    box.addEventListener('touchmove', e=>{{ if(e.touches&&e.touches[0]) showAt(e.touches[0].clientX,e.touches[0].clientY); }}, {{passive:true}});
  }}
  function init(){{ attachTooltip(chartConfigs.crude); attachTooltip(chartConfigs.product); }}
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
}})();
</script>
""".strip()


def build_html(report: Mapping[str, Any]) -> str:
    meta = report.get("report", {}) or {}
    prices = report.get("prices", {}) or {}
    crude = prices.get("crude", {}) or {}
    products = prices.get("products", {}) or {}
    crude_series = crude.get("chart_series", {}) or {}
    product_series = products.get("chart_series", {}) or {}

    display_date = meta.get("display_date") or meta.get("report_date") or ""
    today_label = meta.get("today_label") or ""
    prev_label = meta.get("previous_day_label") or "전일"
    report_title = "Daily 유가 동향"
    title_date = str(meta.get("report_date", "")).replace("-", ".")

    crude_keys = ["Brent", "WTI", "Dubai"]
    product_keys = ["Gasoline", "Diesel", "Naphtha"]
    crude_rows = chart_js_rows(crude_series, crude_keys)
    product_rows = chart_js_rows(product_series, product_keys)

    crude_period = crude.get("chart_period_label", "")
    product_period = products.get("chart_period_label", "")

    body = [
        '<!DOCTYPE html>',
        '<html lang="ko"><head><meta charset="utf-8"/>',
        '<meta content="width=device-width, initial-scale=1.0, viewport-fit=cover" name="viewport"/>',
        f'<title>{esc(report_title)} — {esc(title_date)}</title>',
        f'<style>{css()}</style></head><body><div class="container">',
        '<div class="header"><div class="header-top"><div>',
        f'<div class="header-title">{esc(report_title)}</div>',
        f'<div class="header-date">{esc(display_date)}</div>',
        '</div>',
        f'<div class="header-badge">{esc(meta.get("report_badge") or "정유 · 석유화학 · LNG")}</div>',
        '</div></div>',
        section("1", "Summary", render_summary(report.get("summary", []) or [])),
        section("2", "유가 동향", render_price_section(prices)),
        render_chart_section("3", f"원유 가격 추이 ({crude_period})", crude_series, CRUDE_COLORS, crude_keys, None, "crudeChart", "crudeLine"),
        render_chart_section("4", f"석유제품 가격 추이 ({product_period})", product_series, PRODUCT_COLORS, product_keys, PRODUCT_DISPLAY, "productChart", "productLine"),
        section("5", "이해관계자·정책 주요 동향 (전일 기준)", render_issues(report.get("issues", []) or [])),
        section("6", f"금일 주요 일정 ({today_label})", render_schedules(report.get("schedules", []) or [])),
        section("7", f"조간 신문 트렌드 ({today_label})", render_news(report)),
        f'<div class="footer">SK Innovation Communication Division · {esc(title_date)}</div>',
        '</div>',
        chart_script(crude_rows, product_rows),
        '</body></html>',
    ]
    return "\n".join(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="리포트 JSON을 HTML로 변환")
    parser.add_argument("--date", required=True)
    parser.add_argument("--report-dir", default="data/reports")
    parser.add_argument("--out-dir", default="docs/reports")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = read_json(Path(args.report_dir) / f"{args.date}.report.json")
        out_path = Path(args.out_dir) / f"{args.date}.html"
        report = sanitize_report(report)
        if not has_valid_report_content(report):
            if out_path.exists():
                out_path.unlink()
                print(f"[SKIP] 가격 외 유효 콘텐츠 없음. 기존 HTML 삭제: {out_path}")
            else:
                print(f"[SKIP] 가격 외 유효 콘텐츠 없음. HTML 생성 제외: {args.date}")
            return 0
        atomic_write(out_path, build_html(report))
        print(f"[OK] HTML 리포트 생성 완료: {out_path}")
        return 0
    except Exception as exc:
        print(f"[ERROR] HTML 리포트 생성 실패: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
