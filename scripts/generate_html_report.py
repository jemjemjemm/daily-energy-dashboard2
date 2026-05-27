#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_html_report.py

Render data/reports/YYYY-MM-DD.report.json to docs/reports/YYYY-MM-DD.html.

핵심 수정
- prices.crude.chart_series / prices.products.chart_series 중첩 구조를 직접 지원한다.
- price cards도 중첩형 cards/latest/chart_series/history 구조를 모두 탐색한다.
- 조간 신문 트렌드 대표 기사는 제목 클릭만 남기고, 화면에 긴 URL 텍스트를 출력하지 않는다.
- 그래프 mouse/touch tooltip을 HTML에 포함해 날짜별 가격을 다시 표시한다.
- 기존 CLI(--date --report-dir --out-dir / --input --output)를 유지한다.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CRUDE_KEYS = ["Brent", "WTI", "Dubai"]
PRODUCT_KEYS = ["Gasoline", "Diesel", "Naphtha"]
PRODUCT_LABELS = {"Gasoline": "휘발유", "Diesel": "경유", "Naphtha": "나프타"}
COLORS = {
    "Brent": "#1A6FD4", "WTI": "#E24B4A", "Dubai": "#1D9E75",
    "Gasoline": "#1A6FD4", "Diesel": "#E24B4A", "Naphtha": "#1D9E75",
}

STYLE = r"""
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
*{box-sizing:border-box}body{margin:0;padding:16px;background:#F4F5F7;color:#1A1A1A;font-family:'Noto Sans KR',sans-serif;font-size:14px;line-height:1.6}.container{max-width:480px;margin:0 auto}.header{background:#0A2444;color:#fff;padding:18px 16px 14px;border-radius:12px 12px 0 0}.header-top{display:flex;justify-content:space-between;gap:12px}.header-title{font-size:20px;font-weight:700}.header-date{font-size:12px;color:rgba(255,255,255,.7);margin-top:3px}.header-badge{font-size:11px;background:rgba(255,255,255,.12);border-radius:20px;padding:4px 10px;height:fit-content;white-space:nowrap}.section{background:#fff;border:1px solid #E5E7EB;border-radius:12px;margin:10px 0;overflow:hidden}.section-header{display:flex;align-items:center;gap:8px;padding:11px 16px;border-bottom:1px solid #E5E7EB;background:#F8F9FA}.section-num{font-size:11px;font-weight:700;color:#fff;background:#0A2444;border-radius:4px;padding:2px 7px;min-width:24px;text-align:center}.section-title{font-size:14px;font-weight:700}.summary-body,.news-body{padding:14px 16px}.summary-item{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #F0F0F0;font-size:13px}.summary-item:last-child{border-bottom:none}.summary-dot{flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:#1A6FD4;margin-top:8px}.price-section-label{font-size:12px;font-weight:500;color:#666;padding:12px 16px 6px}.price-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:0 16px 14px}.price-card{background:#F8F9FA;border-radius:8px;padding:10px 8px;text-align:center}.price-label{font-size:11px;color:#666;margin-bottom:4px}.price-value{font-size:18px;font-weight:700;line-height:1}.price-unit{font-size:10px;color:#999;margin-top:2px}.price-change{font-size:11px;margin-top:3px}.up{color:#C0392B}.down{color:#0A7B4E}.flat{color:#888}.divider{height:1px;background:#F0F0F0;margin:0 16px 4px}.chart-wrap{padding:12px 14px}.chart-legend{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px;font-size:12px;color:#666}.legend-item{display:flex;align-items:center;gap:5px}.legend-dot{width:12px;height:3px;border-radius:2px}.chart-box{position:relative;width:100%;min-height:245px;touch-action:pan-y;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;overflow:visible}.chart-svg{width:100%;height:auto;display:block;overflow:visible}.chart-hover-line{opacity:0}.chart-tooltip{position:absolute;z-index:20;display:none;min-width:132px;max-width:220px;background:rgba(10,36,68,.96);color:#fff;border-radius:8px;padding:8px 10px;font-size:11px;line-height:1.45;pointer-events:none;box-shadow:0 6px 18px rgba(0,0,0,.18)}.chart-tooltip .date{font-weight:700;margin-bottom:4px}.tooltip-row{display:flex;justify-content:space-between;gap:12px}.no-data{padding:24px 8px;text-align:center;color:#888;background:#F8F9FA;border-radius:8px}.issue-list,.schedule-list{padding:10px 12px}.issue-card{background:#F8F9FA;border-radius:8px;padding:12px 14px;margin-bottom:8px;border-left:3px solid #1A6FD4}.issue-tag{display:inline-block;font-size:10px;font-weight:700;background:#E6F1FB;color:#185FA5;border-radius:3px;padding:2px 6px;margin-bottom:6px}.issue-title{font-size:13px;font-weight:700;margin-bottom:5px;line-height:1.5}.issue-desc{font-size:12px;color:#444;line-height:1.65}.issue-links{margin-top:8px;font-size:11px}.issue-links a{display:block;color:#0A2444;text-decoration:underline;margin-top:3px}.schedule-row{display:flex;align-items:flex-start;gap:8px;padding:9px 0;border-bottom:1px solid #F0F0F0}.schedule-row:last-child{border-bottom:none}.schedule-time{flex:0 0 38px;font-size:11px;font-weight:700;color:#185FA5;margin-top:1px}.schedule-org{flex:0 0 48px;font-size:10px;background:#F0F1F3;border:1px solid #E0E0E0;border-radius:3px;padding:1px 4px;color:#555;text-align:center}.schedule-main{flex:1;font-size:12px;line-height:1.5}.schedule-rel{font-size:11px;color:#777;margin-top:2px}.news-trend{font-size:13px;line-height:1.75;margin-bottom:14px}.news-separator{height:1px;background:#F0F0F0;margin:12px 0}.news-links-title{font-size:11px;font-weight:700;color:#999;letter-spacing:.5px;margin-bottom:8px}.news-link{display:block;padding:9px 0;border-bottom:1px solid #F0F0F0;text-decoration:none;color:inherit}.news-link-title{font-size:13px;font-weight:600;color:#0A2444;line-height:1.45;text-decoration:underline}.news-link-press{font-size:11px;color:#888;margin:2px 0}.news-link-desc{font-size:11px;color:#555;line-height:1.55}.fact-note{font-size:11px;color:#888;background:#F8F9FA;border-top:1px solid #E5E7EB;padding:10px 16px}.footer{text-align:center;padding:12px;font-size:11px;color:#aaa;border-top:1px solid #E5E7EB;margin-top:4px}@media(max-width:430px){body{padding:10px}.header-title{font-size:18px}.header-badge{font-size:10px;padding:4px 8px}.price-grid{gap:6px;padding:0 12px 12px}.price-value{font-size:16px}.chart-wrap{padding:10px 8px}.chart-box{min-height:230px}.chart-tooltip{font-size:10.5px;min-width:124px}.schedule-org{flex-basis:42px}}
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily Issue Report HTML 리포트 생성", allow_abbrev=False)
    parser.add_argument("--date", help="기준일 YYYY-MM-DD")
    parser.add_argument("--report-dir", default="data/reports", help="report JSON 폴더")
    parser.add_argument("--out-dir", default="docs/reports", help="HTML 출력 폴더")
    parser.add_argument("--input", help="입력 report JSON 파일")
    parser.add_argument("--output", help="출력 HTML 파일")
    return parser.parse_args()


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def list_of(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def dict_of(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_number(value: Any) -> float | None:
    if value in (None, "", "-", "N/A"):
        return None
    try:
        n = float(value)
    except Exception:
        return None
    return n if math.isfinite(n) and n != 0 else None


def fmt(value: Any) -> str:
    n = as_number(value)
    return "-" if n is None else f"{n:.2f}"


def short_date(date_text: str) -> str:
    try:
        d = datetime.strptime(date_text, "%Y-%m-%d")
        return f"{d.month}/{d.day}"
    except Exception:
        return date_text




def get_report_date(data: Mapping[str, Any], fallback: str) -> str:
    report = dict_of(data.get("report"))
    value = report.get("report_date") or data.get("date") or fallback
    value = str(value or fallback).strip()
    # 자동화 입력값은 YYYY-MM-DD로 들어오므로, 형식이 깨진 값은 fallback 유지
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value
    return fallback

def display_date(date_text: str, data: Mapping[str, Any]) -> str:
    report = dict_of(data.get("report"))
    if report.get("display_date"):
        return str(report["display_date"])
    try:
        d = datetime.strptime(date_text, "%Y-%m-%d")
        weekdays = "월화수목금토일"
        return f"{d.year}년 {d.month}월 {d.day}일 ({weekdays[d.weekday()]})"
    except Exception:
        return date_text


def section(num: int, title: str, body: str, class_name: str = "") -> str:
    klass = f"section {class_name}".strip()
    return f"""
<section class="{klass}">
  <div class="section-header"><span class="section-num">{num}</span><span class="section-title">{esc(title)}</span></div>
  {body}
</section>
"""


def text_of(item: Any) -> str:
    if isinstance(item, Mapping):
        for key in ("text", "summary", "description", "desc", "title", "name", "content"):
            if item.get(key):
                return clean_text(item.get(key))
        return clean_text(" ".join(str(v) for v in item.values() if isinstance(v, (str, int, float))))
    return clean_text(item)


def render_summary(data: Mapping[str, Any]) -> str:
    rows = []
    for item in list_of(data.get("summary"))[:3]:
        text = text_of(item)
        if text:
            rows.append(f'<div class="summary-item"><span class="summary-dot"></span><span>{esc(text)}</span></div>')
    defaults = [
        "전일 주요 이해관계자·정책 동향은 일정 및 기사 기준 확인 필요",
        "금일 주요 일정은 정부·국회·산업 현안과의 연계 가능성 중심 모니터링 필요",
        "조간 보도는 정유·석유화학·LNG 업계 관련 대표 기사 중심 정리",
    ]
    while len(rows) < 3:
        rows.append(f'<div class="summary-item"><span class="summary-dot"></span><span>{defaults[len(rows)]}</span></div>')
    return '<div class="summary-body">' + "\n".join(rows[:3]) + '</div>'


def find_by_names(obj: Any, names: Iterable[str]) -> float | None:
    name_set = [n.lower() for n in names]
    def walk(node: Any, parent_key: str = "") -> float | None:
        if isinstance(node, Mapping):
            # 카드 구조 우선 처리
            label = str(node.get("label") or node.get("name") or node.get("source_column") or parent_key).lower()
            if any(n in label for n in name_set):
                for vk in ("value", "price", "latest", "current", "close"):
                    n = as_number(node.get(vk))
                    if n is not None:
                        return n
            for k, v in node.items():
                kl = str(k).lower()
                if any(n in kl for n in name_set):
                    direct = as_number(v)
                    if direct is not None:
                        return direct
                    found = walk(v, kl)
                    if found is not None:
                        return found
            for k, v in node.items():
                found = walk(v, str(k))
                if found is not None:
                    return found
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            for item in reversed(list(node)):
                found = walk(item, parent_key)
                if found is not None:
                    return found
        return None
    return walk(obj)


def cards_from_block(block: Mapping[str, Any], wanted: Sequence[tuple[str, Sequence[str]]]) -> list[dict[str, Any]]:
    existing = list_of(block.get("cards"))
    cards = []
    for label, aliases in wanted:
        matched = None
        for c in existing:
            if not isinstance(c, Mapping):
                continue
            c_label = str(c.get("label") or c.get("source_column") or "").lower()
            if any(alias.lower() in c_label for alias in aliases):
                matched = c
                break
        value = as_number(matched.get("value")) if isinstance(matched, Mapping) else None
        if value is None:
            value = find_by_names(block, aliases)
        change = as_number(matched.get("change")) if isinstance(matched, Mapping) else None
        direction = str(matched.get("direction") or "flat") if isinstance(matched, Mapping) else "flat"
        cards.append({"label": label, "value": value, "change": change, "direction": direction})
    return cards


def price_cards(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    prices = dict_of(data.get("prices"))
    crude_block = dict_of(prices.get("crude")) or prices
    product_block = dict_of(prices.get("products")) or prices
    crude = cards_from_block(crude_block, [
        ("Brent", ["Brent"]), ("WTI", ["WTI"]), ("Dubai", ["Dubai"]),
    ])
    product = cards_from_block(product_block, [
        ("휘발유", ["Gasoline", "Gasoline_92RON", "92RON", "휘발유"]),
        ("경유", ["Diesel", "Diesel_0.001", "경유"]),
        ("나프타", ["Naphtha", "나프타"]),
    ])
    note = clean_text(prices.get("price_data_note") or prices.get("note") or "")
    return crude, product, note


def render_price_cards(cards: Sequence[Mapping[str, Any]]) -> str:
    html_rows = []
    for c in cards[:3]:
        direction = str(c.get("direction") or "flat")
        cls = direction if direction in {"up", "down", "flat"} else "flat"
        change = as_number(c.get("change"))
        if change is None:
            change_text = "-"
        else:
            symbol = "▲" if change > 0 else "▼" if change < 0 else "－"
            change_text = f"{symbol} {abs(change):.2f}"
        html_rows.append(f"""
<div class="price-card">
  <div class="price-label">{esc(c.get('label'))}</div>
  <div class="price-value">{fmt(c.get('value'))}</div>
  <div class="price-unit">$/Bbl</div>
  <div class="price-change {cls}">{esc(change_text)}</div>
</div>
""")
    return '<div class="price-grid">' + "\n".join(html_rows) + '</div>'


def render_price_section(data: Mapping[str, Any]) -> str:
    crude, product, note = price_cards(data)
    note_html = f'<div class="fact-note">{esc(note)}</div>' if note else ''
    return f"""
<div class="price-section-label">원유 ($/Bbl)</div>
{render_price_cards(crude)}
<div class="divider"></div>
<div class="price-section-label">석유제품 ($/Bbl)</div>
{render_price_cards(product)}
{note_html}
"""


def series_points_to_rows(series: Mapping[str, Any], keys: Sequence[str]) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for key in keys:
        points = list_of(series.get(key))
        for p in points:
            if not isinstance(p, Mapping):
                continue
            date = str(p.get("date") or "").strip()
            if not date:
                continue
            row = by_date.setdefault(date, {"date": date, "label": p.get("label") or short_date(date)})
            row[key] = as_number(p.get("value") if "value" in p else p.get(key))
    rows = [by_date[d] for d in sorted(by_date)]
    return rows[-65:]


def table_rows_to_series_rows(rows: Sequence[Any], keys: Sequence[str], value_keys: Sequence[str] | None = None) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        date = str(row.get("date") or "").strip()
        if not date:
            continue
        values = row.get("values") if isinstance(row.get("values"), list) else None
        r: dict[str, Any] = {"date": date, "label": row.get("label") or short_date(date)}
        for i, key in enumerate(keys):
            aliases = [key]
            if value_keys and i < len(value_keys):
                aliases.append(value_keys[i])
            val = None
            if values and i < len(values):
                val = as_number(values[i])
            if val is None:
                for alias in aliases:
                    val = as_number(row.get(alias))
                    if val is not None:
                        break
            r[key] = val
        out.append(r)
    return out[-65:]


def extract_series(data: Mapping[str, Any], group: str) -> list[dict[str, Any]]:
    prices = dict_of(data.get("prices"))
    if group == "crude":
        block = dict_of(prices.get("crude"))
        keys = CRUDE_KEYS
        row_value_keys = ["Brent", "WTI", "Dubai"]
    else:
        block = dict_of(prices.get("products"))
        keys = PRODUCT_KEYS
        row_value_keys = ["Gasoline_92RON", "Diesel_0.001", "Naphtha"]

    chart_series = block.get("chart_series")
    if isinstance(chart_series, Mapping):
        rows = series_points_to_rows(chart_series, keys)
        if rows:
            return rows

    for candidate_key in ("series", "history", "chart", "chart_data", "rows"):
        candidate = block.get(candidate_key)
        if isinstance(candidate, Mapping):
            rows = series_points_to_rows(candidate, keys)
            if rows:
                return rows
        if isinstance(candidate, list):
            rows = table_rows_to_series_rows(candidate, keys, row_value_keys)
            if rows:
                return rows

    # 구버전 평탄 구조 fallback
    for candidate_key in (f"{group}_chart", f"{group}_series", f"{group}_history", "chart_data", "history"):
        candidate = prices.get(candidate_key)
        if isinstance(candidate, Mapping):
            rows = series_points_to_rows(candidate, keys)
            if rows:
                return rows
        if isinstance(candidate, list):
            rows = table_rows_to_series_rows(candidate, keys, row_value_keys)
            if rows:
                return rows
    return []


def chart_js_rows(rows: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {
            "date": str(row.get("date") or ""),
            "label": str(row.get("label") or short_date(str(row.get("date") or ""))),
        }
        for key in keys:
            item[key] = as_number(row.get(key))
        out.append(item)
    return out


def make_svg(rows: list[dict[str, Any]], keys: Sequence[str], chart_id: str, labels: Mapping[str, str] | None = None) -> str:
    values = []
    for r in rows:
        for k in keys:
            n = as_number(r.get(k))
            if n is not None:
                values.append(n)
    if len(rows) < 2 or not values:
        return '<div class="no-data">표시 가능한 그래프 데이터 없음</div>'

    min_v, max_v = min(values), max(values)
    if min_v == max_v:
        min_v -= 1
        max_v += 1
    pad = max((max_v - min_v) * 0.12, 1)
    min_v = max(0, min_v - pad)
    max_v += pad
    W, H = 440, 230
    left, right, top, bottom = 38, 10, 16, 32
    pw, ph = W - left - right, H - top - bottom

    def x(i: int) -> float:
        return left + (0 if len(rows) <= 1 else i / (len(rows) - 1) * pw)

    def y(v: float) -> float:
        return top + (max_v - v) / (max_v - min_v) * ph

    grid = []
    for i in range(5):
        val = min_v + (max_v - min_v) * i / 4
        yy = y(val)
        grid.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{W-right}" y2="{yy:.1f}" stroke="#E9EDF2" stroke-width="1"/>')
        grid.append(f'<text x="4" y="{yy+4:.1f}" font-size="10" fill="#8A8F98">{val:.0f}</text>')

    paths = []
    for key in keys:
        pts = []
        for i, r in enumerate(rows):
            n = as_number(r.get(key))
            if n is not None:
                pts.append(f'{x(i):.1f},{y(n):.1f}')
        if len(pts) >= 2:
            paths.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{COLORS.get(key, "#1A6FD4")}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')

    ticks = sorted(set([0, max(0, len(rows)//3), max(0, (len(rows)*2)//3), len(rows)-1]))
    axis_labels = []
    for idx in ticks:
        label = rows[idx].get("label") or short_date(str(rows[idx].get("date", "")))
        axis_labels.append(f'<text x="{x(idx):.1f}" y="218" text-anchor="middle" font-size="10" fill="#8A8F98">{esc(label)}</text>')

    legend = []
    for key in keys:
        label = labels.get(key, key) if labels else key
        legend.append(f'<span class="legend-item"><span class="legend-dot" style="background:{COLORS.get(key, "#1A6FD4")}"></span>{esc(label)}</span>')

    payload = {
        "id": chart_id,
        "left": left,
        "right": right,
        "width": W,
        "top": top,
        "bottomY": H - bottom,
        "data": chart_js_rows(rows, keys),
        "keys": [[key, labels.get(key, key) if labels else key] for key in keys],
    }
    payload_json = html.escape(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), quote=True)

    return f"""
<div class="chart-legend">{''.join(legend)}</div>
<div class="chart-box" id="{esc(chart_id)}" data-chart='{payload_json}'>
  <svg class="chart-svg" viewBox="0 0 {W} {H}" role="img" aria-label="가격 추이 그래프">
    {''.join(grid)}
    {''.join(paths)}
    {''.join(axis_labels)}
    <line class="chart-hover-line" x1="{left}" x2="{left}" y1="{top}" y2="{H-bottom}" stroke="#0A2444" stroke-width="1"/>
    <rect class="chart-hit-area" x="{left}" y="{top}" width="{pw}" height="{ph}" fill="transparent"/>
  </svg>
  <div class="chart-tooltip"></div>
</div>
"""


def render_chart(title: str, rows: list[dict[str, Any]], keys: Sequence[str], labels: Mapping[str, str] | None = None) -> str:
    if rows:
        title = f"{title} ({short_date(str(rows[0].get('date','')))} ~ {short_date(str(rows[-1].get('date','')))})"
    chart_id = 'crudeChart' if keys == CRUDE_KEYS else 'productChart'
    body = '<div class="chart-wrap">' + make_svg(rows, keys, chart_id, labels) + '</div>'
    return section(3 if keys == CRUDE_KEYS else 4, title, body)


def normalize_links(item: Mapping[str, Any]) -> list[dict[str, str]]:
    raw = item.get("links") or item.get("related_links") or []
    out = []
    if isinstance(raw, list):
        for link in raw[:3]:
            if isinstance(link, Mapping) and link.get("url"):
                out.append({"url": str(link.get("url")), "label": clean_text(link.get("label") or link.get("title") or "관련 자료")})
    return out


def render_issues(data: Mapping[str, Any]) -> str:
    rows = []
    for item in list_of(data.get("issues"))[:8]:
        if not isinstance(item, Mapping):
            continue
        tag = clean_text(item.get("tag") or item.get("category") or "동향")
        title = clean_text(item.get("title") or item.get("name") or "주요 동향")
        desc = clean_text(item.get("description") or item.get("desc") or item.get("summary") or item.get("impact") or "세부 내용 확인 필요")
        links = normalize_links(item)
        link_html = ""
        if links:
            link_html = '<div class="issue-links">관련 링크' + ''.join(f'<a href="{esc(l["url"])}" target="_blank" rel="noopener noreferrer">{esc(l["label"])}</a>' for l in links) + '</div>'
        rows.append(f'<div class="issue-card"><div class="issue-tag">{esc(tag)}</div><div class="issue-title">{esc(title)}</div><div class="issue-desc">{esc(desc)}</div>{link_html}</div>')
    if not rows:
        rows.append('<div class="issue-card"><div class="issue-tag">확인</div><div class="issue-title">전일 주요 동향 데이터 확인 필요</div><div class="issue-desc">전일 일정·이슈 데이터가 비어 있음</div></div>')
    return '<div class="issue-list">' + ''.join(rows) + '</div><div class="fact-note">※ 관련 링크가 없는 항목은 일정·보도자료 원문 확인 범위 내에서 작성. 업계 영향 평가는 작성자 해석</div>'


def render_schedules(data: Mapping[str, Any]) -> str:
    rows = []
    for item in list_of(data.get("schedules"))[:12]:
        if not isinstance(item, Mapping):
            continue
        time = clean_text(item.get("time") or item.get("start_time") or "-")
        org = clean_text(item.get("org") or item.get("organization") or item.get("agency") or "-")
        title = clean_text(item.get("title") or item.get("name") or item.get("event") or "일정 확인 필요")
        rel = clean_text(item.get("relevance") or item.get("impact") or item.get("description") or item.get("desc") or "")
        rel_html = f'<div class="schedule-rel">{esc(rel)}</div>' if rel else ''
        rows.append(f'<div class="schedule-row"><div class="schedule-time">{esc(time)}</div><div class="schedule-org">{esc(org[:8])}</div><div class="schedule-main">{esc(title)}{rel_html}</div></div>')
    if not rows:
        rows.append('<div class="schedule-row"><div class="schedule-time">-</div><div class="schedule-org">-</div><div class="schedule-main">금일 주요 일정 데이터 확인 필요<div class="schedule-rel">일정 데이터가 비어 있음</div></div></div>')
    return '<div class="schedule-list">' + ''.join(rows) + '</div><div class="fact-note">※ 위 일정은 제공된 일정 텍스트 기준. 영향도는 보고서 작성 목적의 해석</div>'


def get_news(data: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]]]:
    news = dict_of(data.get("news_trend"))
    summary = clean_text(news.get("summary") or news.get("trend") or news.get("text") or "")
    articles = [a for a in list_of(news.get("articles")) if isinstance(a, Mapping) and a.get("title")]
    return summary, articles[:5]


def render_news(data: Mapping[str, Any]) -> str:
    summary, articles = get_news(data)
    if not summary:
        if articles:
            summary = "주요 매체가 " + "·".join(clean_text(a.get("title")) for a in articles[:3]) + " 등을 중심으로 보도."
        else:
            summary = "기준일 조간 신문 트렌드 확인 필요."
    rows = []
    for a in articles:
        url = str(a.get("url") or "#").strip() or "#"
        title = clean_text(a.get("title") or "기사 제목 확인 필요")
        press = clean_text(a.get("press") or a.get("source") or a.get("publisher") or "출처 확인")
        desc = clean_text(a.get("summary") or a.get("description") or a.get("desc") or "")
        desc_html = f'<div class="news-link-desc">{esc(desc)}</div>' if desc else ''
        # 중요: 긴 URL 텍스트는 출력하지 않고, 제목에만 href를 건다.
        rows.append(f'<a class="news-link" href="{esc(url)}" target="_blank" rel="noopener noreferrer"><div class="news-link-title">{esc(title)}</div><div class="news-link-press">{esc(press)}</div>{desc_html}</a>')
    if not rows:
        rows.append('<div class="news-link"><div class="news-link-title">대표 기사 데이터 확인 필요</div><div class="news-link-press">-</div><div class="news-link-desc">조간 기사 후보가 report JSON에 반영되지 않음</div></div>')
    return f'<div class="news-body"><div class="news-trend">{esc(summary)}</div><div class="news-separator"></div><div class="news-links-title">대표 기사</div>{"".join(rows)}</div><div class="fact-note">※ 조간 트렌드는 웹 확인 가능한 기준일 오전 보도 중 정유·석유화학·LNG 업계 관련성이 높은 기사 중심 작성. 기사 내용 밖의 업계 영향 평가는 작성자 해석</div>'



TOOLTIP_SCRIPT = r"""
<script>
(function(){
  function fmtValue(v){
    if(v === null || v === undefined || v === "" || Number.isNaN(Number(v))) return "-";
    return Number(v).toFixed(2);
  }
  function attachChartTooltip(box){
    if(!box) return;
    var raw = box.getAttribute('data-chart');
    if(!raw) return;
    var cfg;
    try { cfg = JSON.parse(raw); } catch(e) { return; }
    var data = Array.isArray(cfg.data) ? cfg.data : [];
    if(!data.length) return;
    var tip = box.querySelector('.chart-tooltip');
    var line = box.querySelector('.chart-hover-line');
    var svg = box.querySelector('svg');
    if(!tip || !svg) return;
    var left = Number(cfg.left || 38);
    var right = Number(cfg.right || 10);
    var width = Number(cfg.width || 440);
    var plotWidth = width - left - right;
    function showAt(clientX, clientY){
      var rect = box.getBoundingClientRect();
      if(!rect.width) return;
      var relX = (clientX - rect.left) / rect.width * width;
      relX = Math.max(left, Math.min(width - right, relX));
      var idx = Math.round((relX - left) / plotWidth * (data.length - 1));
      idx = Math.max(0, Math.min(data.length - 1, idx));
      var r = data[idx] || {};
      var x = left + (data.length <= 1 ? 0 : idx / (data.length - 1) * plotWidth);
      if(line){ line.setAttribute('x1', x); line.setAttribute('x2', x); line.setAttribute('opacity', '0.45'); line.style.opacity = '0.45'; }
      var html = '<div class="date">' + (r.label || r.date || '-') + '</div>';
      (cfg.keys || []).forEach(function(pair){
        var key = pair[0], label = pair[1] || key;
        html += '<div class="tooltip-row"><span>' + label + '</span><b>' + fmtValue(r[key]) + '</b></div>';
      });
      tip.innerHTML = html;
      tip.style.display = 'block';
      var localX = clientX - rect.left;
      var localY = clientY - rect.top;
      var l = localX + 12;
      var t = localY - 10;
      var tw = tip.offsetWidth || 150;
      var th = tip.offsetHeight || 104;
      if(l + tw > rect.width) l = localX - tw - 12;
      if(l < 4) l = 4;
      if(t + th > rect.height) t = rect.height - th - 4;
      if(t < 4) t = 4;
      tip.style.left = l + 'px';
      tip.style.top = t + 'px';
    }
    function hide(){
      if(line){ line.setAttribute('opacity', '0'); line.style.opacity = '0'; }
      tip.style.display = 'none';
    }
    // Desktop + iPad pointer devices
    box.addEventListener('mousemove', function(e){ showAt(e.clientX, e.clientY); }, {passive:true});
    box.addEventListener('mouseleave', hide, {passive:true});
    // iPhone/iPad Safari: support both Touch Events and Pointer Events.
    box.addEventListener('touchstart', function(e){ if(e.touches && e.touches[0]) showAt(e.touches[0].clientX, e.touches[0].clientY); }, {passive:true});
    box.addEventListener('touchmove', function(e){ if(e.touches && e.touches[0]) showAt(e.touches[0].clientX, e.touches[0].clientY); }, {passive:true});
    box.addEventListener('pointerdown', function(e){ if(e.pointerType === 'touch' || e.pointerType === 'pen') showAt(e.clientX, e.clientY); }, {passive:true});
    box.addEventListener('pointermove', function(e){ if(e.pointerType === 'touch' || e.pointerType === 'pen') showAt(e.clientX, e.clientY); }, {passive:true});
    box.addEventListener('click', function(e){ showAt(e.clientX, e.clientY); }, {passive:true});
  }
  function init(){
    document.querySelectorAll('.chart-box[data-chart]').forEach(attachChartTooltip);
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
</script>
""".strip()

def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, str]:
    if args.input:
        input_path = Path(args.input)
        date_text = args.date or input_path.name.split(".report.json")[0]
    else:
        if not args.date:
            raise SystemExit("--date 또는 --input 중 하나는 필요합니다.")
        date_text = args.date
        input_path = Path(args.report_dir) / f"{date_text}.report.json"
    output_path = Path(args.output) if args.output else Path(args.out_dir) / f"{date_text}.html"
    return input_path, output_path, date_text


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, prefix=f".{path.name}.", suffix=".tmp") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def render(data: Mapping[str, Any], date_text: str) -> str:
    report = dict_of(data.get("report"))
    badge = clean_text(report.get("report_badge") or "정유 · 석유화학 · LNG")
    today_label = short_date(date_text)
    crude_series = extract_series(data, "crude")
    product_series = extract_series(data, "product")
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Daily Issue Report — {esc(date_text.replace('-', '.'))}</title>
  <style>{STYLE}</style>
</head>
<body>
  <main class="container">
    <header class="header">
      <div class="header-top">
        <div><div class="header-title">Daily Issue Report</div><div class="header-date">{esc(display_date(date_text, data))}</div></div>
        <div class="header-badge">{esc(badge)}</div>
      </div>
    </header>
    {section(1, "Summary", render_summary(data))}
    {section(2, "유가 동향", render_price_section(data))}
    {render_chart("원유 가격 추이", crude_series, CRUDE_KEYS)}
    {render_chart("석유제품 가격 추이", product_series, PRODUCT_KEYS, PRODUCT_LABELS)}
    {section(5, "이해관계자·정책 주요 동향 (전일 기준)", render_issues(data))}
    {section(6, f"금일 주요 일정 ({today_label})", render_schedules(data))}
    {section(7, f"조간 신문 트렌드 ({today_label})", render_news(data))}
    <footer class="footer">SK Innovation Communication Division · {esc(date_text.replace('-', '.'))}</footer>
  </main>
  {TOOLTIP_SCRIPT}
</body>
</html>
"""
    return html_text


def main() -> int:
    args = parse_args()
    input_path, output_path, date_text = resolve_paths(args)
    if not input_path.exists():
        raise FileNotFoundError(f"입력 JSON을 찾을 수 없습니다: {input_path}")
    data = json.loads(input_path.read_text(encoding="utf-8"))
    date_text = get_report_date(data, date_text)
    if not args.output:
        output_path = Path(args.out_dir) / f"{date_text}.html"
    html_text = render(data, date_text)
    atomic_write(output_path, html_text)
    print(f"[OK] HTML 리포트 생성 완료: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
