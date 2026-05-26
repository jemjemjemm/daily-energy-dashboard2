#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render Daily energy dashboard report JSON to mobile HTML.

This script is intentionally limited to the rendering layer.
It does not collect schedules/news/prices and does not change report JSON.

Supported CLI forms:
  1) Existing automation/backfill:
     python scripts/generate_html_report.py --date 2026-05-26 --report-dir data/reports --out-dir docs/reports
  2) Manual single-file rendering:
     python scripts/generate_html_report.py --input data/reports/2026-05-26.report.json --output docs/reports/2026-05-26.html
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

CRUDE_KEYS = ["Brent", "WTI", "Dubai"]
PRODUCT_KEYS = ["Gasoline", "Diesel", "Naphtha"]
PRODUCT_DISPLAY = {"Gasoline": "휘발유", "Diesel": "경유", "Naphtha": "나프타"}
COLORS = {
    "Brent": "#1A6FD4",
    "WTI": "#E24B4A",
    "Dubai": "#1D9E75",
    "Gasoline": "#1A6FD4",
    "Diesel": "#E24B4A",
    "Naphtha": "#1D9E75",
}

# 실제 오류/fallback 문구만 제거합니다. '세이프타임즈'처럼 정상 출처 문구로 쓰일 수 있는 단어는 제외합니다.
BAD_REPORT_PHRASES = [
    "자동 추출된 일정 항목이 없습니다",
    "본문 구조 확인 및 수동 검수가 필요합니다",
    "원문 자동 매칭 실패",
    "주요일정 원문 데이터 미확보",
    "원문 데이터 없음",
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
]

FORMAL_REPLACEMENTS = [
    ("했습니다.", "함."),
    ("하였습니다.", "함."),
    ("입니다.", "임."),
    ("됩니다.", "됨."),
    ("필요합니다.", "필요."),
    ("가능합니다.", "가능."),
    ("확인됩니다.", "확인."),
    ("확인했습니다.", "확인."),
    ("보도했습니다.", "보도."),
    ("분석했습니다.", "분석."),
    ("전망했습니다.", "전망."),
    ("지적했습니다.", "지적."),
    ("강조했습니다.", "강조."),
    ("밝혔습니다.", "밝힘."),
]


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def text_of(value: Any) -> str:
    return "" if value is None else str(value)


def strip_tags(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value or "", flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_text(value: Any, *, keep_html: bool = False) -> str:
    text = text_of(value)
    for phrase in BAD_REPORT_PHRASES:
        text = text.replace(phrase, "")
    if not keep_html:
        text = strip_tags(text)
    else:
        text = re.sub(r"\s+", " ", text).strip()
    for old, new in FORMAL_REPLACEMENTS:
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def has_bad_phrase(value: Any) -> bool:
    text = text_of(value)
    return any(phrase in text for phrase in BAD_REPORT_PHRASES)


def fmt_num(value: Any) -> str:
    try:
        n = float(value)
    except Exception:
        return "-"
    if not math.isfinite(n) or n == 0:
        return "-"
    return f"{n:.2f}"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"리포트 JSON을 찾을 수 없습니다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, prefix=f".{path.name}.", suffix=".tmp") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def clean_list(items: Any, *, required_key: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        blob = " ".join(text_of(v) for v in item.values())
        if has_bad_phrase(blob):
            continue
        copied = dict(item)
        for key in ["title", "text", "description", "summary", "relevance", "press", "category", "org", "time"]:
            if key in copied:
                copied[key] = clean_text(copied[key])
        if text_of(copied.get(required_key, "")).strip():
            out.append(copied)
    return out


def normalize_report(report: dict[str, Any]) -> dict[str, Any]:
    report = dict(report)
    report["summary"] = clean_list(report.get("summary", []), required_key="text")
    report["issues"] = clean_list(report.get("issues", []), required_key="title")
    report["schedules"] = clean_list(report.get("schedules", []), required_key="title")

    news = dict(report.get("news_trend", {}) or {})
    articles: list[dict[str, Any]] = []
    for a in news.get("articles", []) or []:
        if not isinstance(a, Mapping):
            continue
        title = clean_text(a.get("title", ""))
        url = text_of(a.get("url", "")).strip()
        if not title or not url:
            continue
        if "오늘의 주요일정" in title or has_bad_phrase(title + " " + url):
            continue
        copied = dict(a)
        for key in ["title", "summary", "press", "published_at_kst", "desc"]:
            if key in copied:
                copied[key] = clean_text(copied[key])
        copied["title"] = title
        copied["url"] = url
        articles.append(copied)
    news["articles"] = articles[:3]

    paras = []
    for p in news.get("trend_paragraphs", []) or []:
        t = clean_text(p)
        if t and not has_bad_phrase(t):
            paras.append(t)
    news["trend_paragraphs"] = paras[:3]

    if news.get("summary_html") and not has_bad_phrase(news.get("summary_html")):
        news["summary_html"] = clean_text(news.get("summary_html"), keep_html=True)
    elif news.get("summary") and not has_bad_phrase(news.get("summary")):
        news["summary"] = clean_text(news.get("summary"))
    else:
        news["summary"] = ""
        news["summary_html"] = ""
    report["news_trend"] = news
    return report


def has_valid_content(report: Mapping[str, Any]) -> bool:
    news = report.get("news_trend", {}) if isinstance(report.get("news_trend"), Mapping) else {}
    articles = news.get("articles", []) if isinstance(news.get("articles"), list) else []
    return bool(report.get("issues") or report.get("schedules") or articles)


def section(num: int, title: str, body: str) -> str:
    return f'''<div class="section"><div class="section-header"><span class="section-num">{num}</span><span class="section-title">{esc(title)}</span></div>{body}</div>'''


def render_summary(items: Sequence[Mapping[str, Any]]) -> str:
    rows = []
    for item in items[:3]:
        text = clean_text(item.get("text", ""))
        if text:
            rows.append(f'<div class="summary-item"><div class="summary-dot"></div><div>{esc(text)}</div></div>')
    if not rows:
        rows.append('<div class="summary-item"><div class="summary-dot"></div><div>기준일 주요 요약 없음</div></div>')
    return '<div class="summary-body">' + "\n".join(rows) + '</div>'


def render_cards(cards: Any) -> str:
    if not isinstance(cards, list) or not cards:
        return '<div class="price-grid"><div class="price-card"><div class="price-value">-</div></div></div>'
    rows = []
    for card in cards[:3]:
        if not isinstance(card, Mapping):
            continue
        direction = text_of(card.get("direction", "flat"))
        cls = {"up": "up", "down": "down", "flat": "flat"}.get(direction, "flat")
        mark = {"up": "▲", "down": "▼", "flat": "－"}.get(direction, "－")
        value = fmt_num(card.get("value"))
        try:
            chg = abs(float(card.get("change", 0)))
        except Exception:
            chg = 0
        change_text = "-" if value == "-" else f"{mark} {chg:.2f}"
        rows.append(
            f'''<div class="price-card"><div class="price-label">{esc(card.get("label", ""))}</div><div class="price-value">{value}</div><div class="price-unit">{esc(card.get("unit", "$/Bbl"))}</div><div class="price-change"><span class="{cls}">{esc(change_text)}</span></div></div>'''
        )
    return '<div class="price-grid">' + "\n".join(rows) + '</div>'


def render_price(prices: Mapping[str, Any]) -> str:
    crude = prices.get("crude", {}) if isinstance(prices.get("crude"), Mapping) else {}
    products = prices.get("products", {}) if isinstance(prices.get("products"), Mapping) else {}
    note = clean_text(prices.get("price_data_note", ""))
    html_parts = [
        f'<div class="price-section-label">원유 ($/Bbl) — {esc(crude.get("base_label", ""))} 기준</div>',
        render_cards(crude.get("cards", [])),
        '<div class="divider"></div>',
        f'<div class="price-section-label">석유제품 ($/Bbl) — {esc(products.get("base_label", ""))} 기준</div>',
        render_cards(products.get("cards", [])),
    ]
    if note:
        html_parts.append(f'<div class="note">{esc(note)}</div>')
    return "\n".join(html_parts)


def date_label(date_text: str) -> str:
    try:
        return f"{int(date_text[5:7])}/{int(date_text[8:10])}"
    except Exception:
        return date_text


def collect_dates(series: Mapping[str, Any]) -> list[str]:
    dates = set()
    for pts in series.values():
        if not isinstance(pts, list):
            continue
        for p in pts:
            if isinstance(p, Mapping) and p.get("date"):
                dates.add(str(p.get("date")))
    return sorted(dates)


def collect_values(series: Mapping[str, Any]) -> list[float]:
    vals = []
    for pts in series.values():
        if not isinstance(pts, list):
            continue
        for p in pts:
            if not isinstance(p, Mapping):
                continue
            try:
                v = float(p.get("value"))
            except Exception:
                continue
            if math.isfinite(v) and v != 0:
                vals.append(v)
    return vals


def render_svg(series: Mapping[str, Any], keys: Sequence[str]) -> str:
    dates = collect_dates(series)
    vals = collect_values(series)
    if not dates or not vals:
        return '<div class="chart-empty">표시 가능한 그래프 데이터 없음</div>'
    lo, hi = min(vals), max(vals)
    if lo == hi:
        lo -= 1
        hi += 1
    pad = max((hi - lo) * 0.12, 1)
    lo = max(0, lo - pad)
    hi += pad
    L, R, T, B = 38, 430, 12, 198
    date_idx = {d: i for i, d in enumerate(dates)}

    def x(i: int) -> float:
        return (L + R) / 2 if len(dates) == 1 else L + (R - L) * i / (len(dates) - 1)

    def y(v: float) -> float:
        return B - ((v - lo) / (hi - lo)) * (B - T)

    parts = ['<svg aria-label="가격 추이 그래프" class="chart-svg" preserveAspectRatio="xMidYMid meet" role="img" viewBox="0 0 440 230" xmlns="http://www.w3.org/2000/svg">']
    for i in range(6):
        yy = B - (B - T) * i / 5
        label = lo + (hi - lo) * i / 5
        parts.append(f'<line x1="{L}" x2="{R}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="rgba(0,0,0,0.07)" stroke-width="1"/>')
        parts.append(f'<text x="34" y="{yy+3:.1f}" text-anchor="end" font-size="9" fill="#888">{label:.0f}</text>')
    tick_idxs = sorted(set([0, len(dates) - 1, max(0, len(dates)//3), max(0, (len(dates)*2)//3)]))
    for i in tick_idxs:
        parts.append(f'<text x="{x(i):.1f}" y="221" text-anchor="middle" font-size="9" fill="#888">{esc(date_label(dates[i]))}</text>')
    for key in keys:
        pts = series.get(key, []) if isinstance(series.get(key, []), list) else []
        d = []
        for p in pts:
            if not isinstance(p, Mapping):
                continue
            dt = str(p.get("date", ""))
            if dt not in date_idx:
                continue
            try:
                v = float(p.get("value"))
            except Exception:
                continue
            if not math.isfinite(v) or v == 0:
                continue
            cmd = "M" if not d else "L"
            d.append(f'{cmd}{x(date_idx[dt]):.1f},{y(v):.1f}')
        if d:
            parts.append(f'<path d="{" ".join(d)}" fill="none" stroke="{COLORS.get(key, "#1A6FD4")}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
    parts.append('</svg>')
    return "\n".join(parts)


def render_chart(title: str, series: Mapping[str, Any], keys: Sequence[str]) -> str:
    legend = []
    for key in keys:
        label = PRODUCT_DISPLAY.get(key, key)
        legend.append(f'<div class="legend-item"><div class="legend-dot" style="background:{COLORS.get(key, "#1A6FD4")}"></div>{esc(label)}</div>')
    body = '<div class="chart-wrap"><div class="chart-legend">' + "".join(legend) + '</div><div class="chart-box">' + render_svg(series, keys) + '</div></div>'
    return body


def render_issues(items: Sequence[Mapping[str, Any]]) -> str:
    rows = []
    for item in items:
        title = clean_text(item.get("title", ""))
        desc = clean_text(item.get("description", ""))
        category = clean_text(item.get("category", "")) or "정책"
        if not title:
            continue
        link_html = ""
        links = item.get("links") or item.get("related_links") or []
        if isinstance(links, list):
            link_rows = []
            for link in links[:3]:
                if not isinstance(link, Mapping):
                    continue
                url = text_of(link.get("url", "")).strip()
                label = clean_text(link.get("label") or link.get("title") or "관련 자료")
                note = clean_text(link.get("note", ""))
                if url and label:
                    link_rows.append(f'<a href="{esc(url)}" rel="noopener" target="_blank">{esc(label)}</a>' + (f'<div class="link-note">{esc(note)}</div>' if note else ''))
            if link_rows:
                link_html = '<div class="issue-links"><span>관련 링크</span>' + "".join(link_rows) + '</div>'
        rows.append(f'''<div class="issue-card"><div class="issue-tag">{esc(category)}</div><div class="issue-title">{esc(title)}</div><div class="issue-desc">{esc(desc)}</div>{link_html}</div>''')
    if not rows:
        rows.append('<div class="issue-card"><div class="issue-title">주요 이해관계자 동향 없음</div></div>')
    return '<div class="issue-list">' + "\n".join(rows) + '</div>'


def render_schedules(items: Sequence[Mapping[str, Any]]) -> str:
    rows = []
    for item in items:
        title = clean_text(item.get("title", ""))
        if not title:
            continue
        time = clean_text(item.get("time", ""))
        org = clean_text(item.get("org", "")) or "정부"
        rel = clean_text(item.get("relevance", ""))
        rows.append(f'''<div class="schedule-row"><div class="schedule-time">{esc(time)}</div><div class="schedule-org">{esc(org)}</div><div class="schedule-main"><div>{esc(title)}</div>{f'<div class="schedule-rel">{esc(rel)}</div>' if rel else ''}</div></div>''')
    if not rows:
        rows.append('<div class="schedule-row"><div class="schedule-main"><div>금일 주요 일정 데이터 없음</div></div></div>')
    return '<div class="schedule-list">' + "\n".join(rows) + '</div>'


def render_news(report: Mapping[str, Any]) -> str:
    news = report.get("news_trend", {}) if isinstance(report.get("news_trend"), Mapping) else {}
    articles = news.get("articles", []) if isinstance(news.get("articles"), list) else []
    valid = []
    for a in articles[:3]:
        if not isinstance(a, Mapping):
            continue
        title = clean_text(a.get("title", ""))
        url = text_of(a.get("url", "")).strip()
        if title and url:
            valid.append({**a, "title": title, "url": url})
    if not valid:
        raise ValueError("조간 신문 트렌드 대표 기사 0건: HTML 생성 중단")

    raw_summary = clean_text(news.get("summary_html") or news.get("summary") or "", keep_html=True)
    if raw_summary:
        raw_summary = esc(strip_tags(raw_summary))
    else:
        raw_summary = "주요 매체가 " + " ".join("△" + clean_text(a.get("title", "")) for a in valid) + " 등을 중심으로 보도."

    paras = [clean_text(p) for p in news.get("trend_paragraphs", []) or [] if clean_text(p)]
    if not paras:
        for a in valid:
            press = clean_text(a.get("press", "")) or "해당 매체"
            summary = clean_text(a.get("summary", "")) or clean_text(a.get("title", ""))
            paras.append(f"{press}는 {summary}")

    trend = f'<div class="news-trend">{raw_summary}'
    for p in paras[:3]:
        m = re.match(r"(.{2,24}?)는\s+(.+)", p)
        if m:
            trend += f'<br/><br/><strong>{esc(m.group(1))}</strong>는 {esc(m.group(2))}'
        else:
            trend += f'<br/><br/>{esc(p)}'
    trend += '</div>'

    rows = []
    for a in valid:
        title = clean_text(a.get("title", ""))
        url = text_of(a.get("url", "")).strip()
        press = clean_text(a.get("press", ""))
        summary = clean_text(a.get("summary", "")) or clean_text(a.get("desc", ""))
        rows.append(f'''<a class="news-link" href="{esc(url)}" rel="noopener" target="_blank"><div class="news-link-title">{esc(title)}</div><div class="news-link-press">{esc(press)}</div>{f'<div class="news-link-desc">{esc(summary)}</div>' if summary else ''}<div class="news-url">{esc(url)}</div></a>''')

    return '<div class="news-body">' + trend + '<div class="news-separator"></div><div class="news-links-title">대표 기사</div>' + "\n".join(rows) + '</div><div class="fact-note">※ 조간 트렌드는 기준일 오전 보도 중 정유·석유화학·LNG 업계 관련성이 높은 기사 중심 작성. 기사 내용 밖의 업계 영향 평가는 작성자 해석</div>'


def css() -> str:
    return """
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
*{box-sizing:border-box}body{margin:0;padding:16px;background:#F4F5F7;color:#1A1A1A;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;font-size:14px;line-height:1.6;word-break:keep-all;overflow-wrap:anywhere}.container{max-width:480px;margin:0 auto}.header{background:#0A2444;color:#fff;padding:18px 16px 14px;border-radius:12px 12px 0 0}.header-top{display:flex;justify-content:space-between;gap:12px}.header-title{font-size:20px;font-weight:700}.header-date{font-size:12px;color:rgba(255,255,255,.58);margin-top:3px}.header-badge{font-size:11px;background:rgba(255,255,255,.12);border-radius:20px;padding:4px 10px;height:fit-content;white-space:nowrap}.section{background:#fff;border:1px solid #E5E7EB;border-radius:12px;margin:10px 0;overflow:hidden}.section-header{display:flex;align-items:center;gap:8px;padding:11px 16px;border-bottom:1px solid #E5E7EB;background:#F8F9FA}.section-num{font-size:11px;font-weight:700;color:#fff;background:#0A2444;border-radius:4px;padding:2px 7px;min-width:24px;text-align:center}.section-title{font-size:14px;font-weight:700}.summary-body,.news-body{padding:14px 16px}.summary-item{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #F0F0F0;font-size:13px;line-height:1.65}.summary-item:last-child{border-bottom:none}.summary-dot{flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:#1A6FD4;margin-top:8px}.price-section-label{font-size:12px;font-weight:500;color:#666;padding:12px 16px 6px}.price-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:0 16px 14px}.price-card{background:#F8F9FA;border-radius:8px;padding:10px 8px;text-align:center}.price-label{font-size:11px;color:#666;margin-bottom:4px}.price-value{font-size:18px;font-weight:700;line-height:1}.price-unit{font-size:10px;color:#999;margin-top:2px}.price-change{font-size:11px;margin-top:3px}.up{color:#C0392B}.down{color:#0A7B4E}.flat{color:#888}.divider{height:1px;background:#F0F0F0;margin:0 16px 4px}.chart-wrap{padding:12px 14px;position:relative}.chart-legend{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px;font-size:12px;color:#666}.legend-item{display:flex;align-items:center;gap:5px}.legend-dot{width:12px;height:3px;border-radius:2px}.chart-box{position:relative;width:100%;min-height:245px;overflow:visible}.chart-svg{width:100%;height:auto;display:block;overflow:visible}.chart-empty{padding:40px 0;text-align:center;color:#999;font-size:12px}.issue-list,.schedule-list{padding:10px 12px}.issue-card{background:#F8F9FA;border-radius:8px;padding:12px 14px;margin-bottom:8px;border-left:3px solid #1A6FD4}.issue-card:last-child{margin-bottom:0}.issue-tag{display:inline-block;font-size:10px;font-weight:700;background:#E6F1FB;color:#185FA5;border-radius:3px;padding:2px 6px;margin-bottom:6px}.issue-title{font-size:13px;font-weight:700;margin-bottom:5px;line-height:1.5}.issue-desc{font-size:12px;color:#444;line-height:1.65}.issue-links{margin-top:9px;display:flex;flex-direction:column;gap:4px;font-size:11px}.issue-links a{color:#0A2444;text-decoration:underline;word-break:break-all}.issue-links span{color:#777}.issue-links .link-note{color:#777;font-size:10.5px;line-height:1.45}.schedule-row{display:flex;align-items:flex-start;gap:8px;padding:9px 0;border-bottom:1px solid #F0F0F0}.schedule-row:last-child{border-bottom:none}.schedule-time{flex:0 0 38px;font-size:11px;font-weight:700;color:#185FA5;margin-top:1px}.schedule-org{flex:0 0 48px;font-size:10px;background:#F0F1F3;border:1px solid #E0E0E0;border-radius:3px;padding:1px 4px;color:#555;text-align:center}.schedule-main{flex:1;font-size:12px;line-height:1.5}.schedule-rel{font-size:11px;color:#777;margin-top:2px}.note{padding:0 16px 14px;font-size:11px;color:#999}.news-trend{font-size:13px;line-height:1.75;margin-bottom:14px}.news-trend strong{font-weight:700;color:#0A2444}.news-separator{height:1px;background:#F0F0F0;margin:12px 0}.news-links-title{font-size:11px;font-weight:700;color:#999;letter-spacing:.5px;margin-bottom:8px}.news-link{display:block;padding:9px 0;border-bottom:1px solid #F0F0F0;text-decoration:none;color:inherit}.news-link-title{font-size:13px;font-weight:600;color:#0A2444;line-height:1.45;text-decoration:underline}.news-link-press{font-size:11px;color:#888;margin:2px 0}.news-link-desc{font-size:11px;color:#555;line-height:1.55}.news-url{font-size:10px;color:#999;word-break:break-all;margin-top:4px}.fact-note{font-size:11px;color:#888;background:#F8F9FA;border-top:1px solid #E5E7EB;padding:10px 16px}.footer{text-align:center;padding:12px;font-size:11px;color:#aaa;border-top:1px solid #E5E7EB;margin-top:4px}@media(max-width:430px){body{padding:10px}.header-title{font-size:18px}.header-badge{font-size:10px;padding:4px 8px}.section-header{padding:10px 12px}.summary-body,.news-body{padding:12px}.price-grid{gap:6px;padding:0 12px 12px}.price-card{padding:9px 4px}.price-value{font-size:16px}.chart-wrap{padding:10px 8px}.chart-box{min-height:230px}.chart-legend{gap:8px;font-size:11px;margin-left:4px}.schedule-org{flex-basis:42px}}
""".strip()


def build_html(report: Mapping[str, Any]) -> str:
    meta = report.get("report", {}) if isinstance(report.get("report"), Mapping) else {}
    prices = report.get("prices", {}) if isinstance(report.get("prices"), Mapping) else {}
    crude = prices.get("crude", {}) if isinstance(prices.get("crude"), Mapping) else {}
    products = prices.get("products", {}) if isinstance(prices.get("products"), Mapping) else {}
    crude_series = crude.get("chart_series", {}) if isinstance(crude.get("chart_series"), Mapping) else {}
    product_series = products.get("chart_series", {}) if isinstance(products.get("chart_series"), Mapping) else {}

    report_date = text_of(meta.get("report_date", ""))
    display_date = text_of(meta.get("display_date") or report_date)
    today_label = text_of(meta.get("today_label") or (date_label(report_date) if report_date else ""))
    title_date = report_date.replace("-", ".") if report_date else display_date
    badge = text_of(meta.get("report_badge") or "정유 · 석유화학 · LNG")
    crude_period = text_of(crude.get("chart_period_label", ""))
    product_period = text_of(products.get("chart_period_label", ""))

    parts = [
        '<!DOCTYPE html>',
        '<html lang="ko"><head><meta charset="utf-8"/>',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"/>',
        f'<title>Daily 유가 동향 — {esc(title_date)}</title>',
        f'<style>{css()}</style></head><body><div class="container">',
        f'<div class="header"><div class="header-top"><div><div class="header-title">Daily 유가 동향</div><div class="header-date">{esc(display_date)}</div></div><div class="header-badge">{esc(badge)}</div></div></div>',
        section(1, "Summary", render_summary(report.get("summary", []) or [])),
        section(2, "유가 동향", render_price(prices)),
        section(3, f"원유 가격 추이 ({crude_period})" if crude_period else "원유 가격 추이", render_chart("원유 가격 추이", crude_series, CRUDE_KEYS)),
        section(4, f"석유제품 가격 추이 ({product_period})" if product_period else "석유제품 가격 추이", render_chart("석유제품 가격 추이", product_series, PRODUCT_KEYS)),
        section(5, "이해관계자·정책 주요 동향 (전일 기준)", render_issues(report.get("issues", []) or [])),
        section(6, f"금일 주요 일정 ({today_label})" if today_label else "금일 주요 일정", render_schedules(report.get("schedules", []) or [])),
        section(7, f"조간 신문 트렌드 ({today_label})" if today_label else "조간 신문 트렌드", render_news(report)),
        f'<div class="footer">SK Innovation Communication Division · {esc(title_date)}</div>',
        '</div></body></html>',
    ]
    return "\n".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="리포트 JSON을 HTML로 변환")
    parser.add_argument("--date", default="", help="YYYY-MM-DD. 기존 자동화 호출 방식")
    parser.add_argument("--report-dir", default="data/reports", help="리포트 JSON 폴더")
    parser.add_argument("--out-dir", default="docs/reports", help="HTML 출력 폴더")
    parser.add_argument("--input", default="", help="수동 실행용 입력 JSON 경로")
    parser.add_argument("--output", default="", help="수동 실행용 출력 HTML 경로")
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.input or args.output:
        if not args.input or not args.output:
            raise ValueError("--input과 --output은 함께 지정해야 합니다.")
        return Path(args.input), Path(args.output)
    if not args.date:
        raise ValueError("--date 또는 --input/--output을 지정해야 합니다.")
    return Path(args.report_dir) / f"{args.date}.report.json", Path(args.out_dir) / f"{args.date}.html"


def main() -> int:
    args = parse_args()
    try:
        in_path, out_path = resolve_paths(args)
        report = normalize_report(read_json(in_path))
        if not has_valid_content(report):
            if out_path.exists():
                out_path.unlink()
                print(f"[SKIP] 유효 콘텐츠 없음. 기존 HTML 삭제: {out_path}")
            else:
                print(f"[SKIP] 유효 콘텐츠 없음. HTML 생성 제외: {out_path}")
            return 0
        atomic_write(out_path, build_html(report))
        print(f"[OK] HTML 리포트 생성 완료: {out_path}")
        return 0
    except Exception as exc:
        print(f"[ERROR] HTML 리포트 생성 실패: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
