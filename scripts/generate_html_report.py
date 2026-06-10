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
from datetime import datetime, timedelta
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
*{box-sizing:border-box}body{margin:0;padding:16px;background:#F4F5F7;color:#1A1A1A;font-family:'Noto Sans KR',sans-serif;font-size:14px;line-height:1.6}.container{max-width:480px;margin:0 auto}.header{background:#0A2444;color:#fff;padding:18px 16px 14px;border-radius:12px 12px 0 0}.header-top{display:flex;justify-content:space-between;gap:12px}.header-title{font-size:20px;font-weight:700}.header-date{font-size:12px;color:rgba(255,255,255,.7);margin-top:3px}.header-badge{font-size:11px;background:rgba(255,255,255,.12);border-radius:20px;padding:4px 10px;height:fit-content;white-space:nowrap}.section{background:#fff;border:1px solid #E5E7EB;border-radius:12px;margin:10px 0;overflow:hidden}.section-header{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 16px;border-bottom:1px solid #E5E7EB;background:#F8F9FA}.section-heading{display:flex;align-items:center;gap:8px;min-width:0}.section-num{font-size:11px;font-weight:700;color:#fff;background:#0A2444;border-radius:4px;padding:2px 7px;min-width:24px;text-align:center}.section-title{font-size:14px;font-weight:700;min-width:0}.section-detail-btn{flex:0 0 auto;min-height:30px;border:1px solid #C9D8EA;border-radius:999px;background:#fff;color:#185FA5;padding:4px 11px;font-size:12px;font-weight:700;line-height:1;cursor:pointer;-webkit-tap-highlight-color:transparent}.section-detail-btn:active{background:#EAF3FF}.summary-body,.news-body{padding:14px 16px}.summary-item{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #F0F0F0;font-size:13px}.summary-item:last-child{border-bottom:none}.summary-dot{flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:#1A6FD4;margin-top:8px}.price-section-label{font-size:12px;font-weight:500;color:#666;padding:12px 16px 6px}.price-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:0 16px 14px}.price-card{background:#F8F9FA;border-radius:8px;padding:10px 8px;text-align:center}.price-label{font-size:11px;color:#666;margin-bottom:4px}.price-value{font-size:18px;font-weight:700;line-height:1}.price-unit{font-size:10px;color:#999;margin-top:2px}.price-change{font-size:11px;margin-top:3px}.up{color:#C0392B}.down{color:#0A7B4E}.flat{color:#888}.divider{height:1px;background:#F0F0F0;margin:0 16px 4px}.chart-wrap{padding:12px 14px}.chart-legend{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px;font-size:12px;color:#666}.legend-item{display:flex;align-items:center;gap:5px}.legend-dot{width:12px;height:3px;border-radius:2px}.chart-box{position:relative;width:100%;min-height:245px;touch-action:pan-y;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;overflow:visible}.chart-svg{width:100%;height:auto;display:block;overflow:visible}.chart-hover-line{opacity:0}.chart-tooltip{position:absolute;z-index:20;display:none;min-width:132px;max-width:220px;background:rgba(10,36,68,.96);color:#fff;border-radius:8px;padding:8px 10px;font-size:11px;line-height:1.45;pointer-events:none;box-shadow:0 6px 18px rgba(0,0,0,.18)}.chart-tooltip .date{font-weight:700;margin-bottom:4px}.tooltip-row{display:flex;justify-content:space-between;gap:12px}.no-data{padding:24px 8px;text-align:center;color:#888;background:#F8F9FA;border-radius:8px}.issue-list,.schedule-list{padding:10px 12px}.issue-card{background:#F8F9FA;border-radius:8px;padding:12px 14px;margin-bottom:8px;border-left:3px solid #1A6FD4}.issue-tag{display:inline-block;font-size:10px;font-weight:700;background:#E6F1FB;color:#185FA5;border-radius:3px;padding:2px 6px;margin-bottom:6px}.issue-title{font-size:13px;font-weight:700;margin-bottom:5px;line-height:1.5}.issue-desc{font-size:12px;color:#444;line-height:1.65}.issue-links{margin-top:8px;font-size:11px}.issue-links a{display:block;color:#0A2444;text-decoration:underline;margin-top:3px}.issue-links span{display:block;color:#777;margin-top:3px}.schedule-row{display:flex;align-items:flex-start;gap:8px;padding:9px 0;border-bottom:1px solid #F0F0F0}.schedule-row:last-child{border-bottom:none}.schedule-time{flex:0 0 38px;font-size:11px;font-weight:700;color:#185FA5;margin-top:1px}.schedule-org{flex:0 0 48px;font-size:10px;background:#F0F1F3;border:1px solid #E0E0E0;border-radius:3px;padding:1px 4px;color:#555;text-align:center}.schedule-main{flex:1;font-size:12px;line-height:1.5}.schedule-rel{font-size:11px;color:#777;margin-top:2px}.schedule-table{width:100%;border-collapse:collapse;table-layout:fixed}.schedule-table th{font-size:11px;color:#666;background:#F8F9FA;border-bottom:1px solid #E5E7EB;padding:6px 5px;text-align:left}.schedule-table th:first-child{width:46px}.schedule-table th:nth-child(2){width:28%}.schedule-table td{vertical-align:top;border-bottom:1px solid #F0F0F0;padding:8px 5px}.schedule-table .schedule-row{display:table-row;border-bottom:none}.schedule-table .schedule-time{width:46px;display:table-cell;flex:none;font-size:11px;font-weight:700;color:#185FA5;margin:0;white-space:normal;word-break:keep-all}.schedule-table .schedule-main{width:28%;display:table-cell;flex:none;font-size:12px;line-height:1.5;font-weight:600}.schedule-attendees{font-size:12px;line-height:1.55;color:#333}.news-trend{font-size:13px;line-height:1.75;margin-bottom:14px}.news-separator{height:1px;background:#F0F0F0;margin:12px 0}.news-links-title{font-size:11px;font-weight:700;color:#999;letter-spacing:.5px;margin-bottom:8px}.news-link{display:block;padding:9px 0;border-bottom:1px solid #F0F0F0;text-decoration:none;color:inherit}.news-link-title{font-size:13px;font-weight:600;color:#0A2444;line-height:1.45;text-decoration:underline}.news-link-press{font-size:11px;color:#888;margin:2px 0}.news-link-desc{font-size:11px;color:#555;line-height:1.55}.fact-note{font-size:11px;color:#888;background:#F8F9FA;border-top:1px solid #E5E7EB;padding:10px 16px}.schedule-detail-modal{position:fixed;inset:0;z-index:9999;display:none;align-items:center;justify-content:center;background:rgba(10,36,68,.35);padding:12px}.schedule-detail-modal.is-open{display:flex}.schedule-detail-panel{width:100%;max-width:430px;height:calc(100vh - 24px);height:calc(100dvh - 24px);background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 18px 50px rgba(0,0,0,.25);display:flex;flex-direction:column}.schedule-detail-topbar{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 10px;background:#0A2444;color:#fff}.schedule-detail-topbar span{font-size:13px;font-weight:700}.schedule-detail-close{min-height:34px;border:1px solid rgba(255,255,255,.35);border-radius:999px;background:rgba(255,255,255,.12);color:#fff;padding:4px 12px;font-size:12px;font-weight:700;cursor:pointer}.schedule-detail-frame{flex:1;width:100%;height:100%;border:0;background:#F4F6F9}.schedule-detail-fallback{display:none;flex:1;align-items:center;justify-content:center;padding:22px;color:#555;text-align:center;background:#fff}.schedule-detail-fallback.is-visible{display:flex}.footer{text-align:center;padding:12px;font-size:11px;color:#aaa;border-top:1px solid #E5E7EB;margin-top:4px}@media(max-width:430px){body{padding:10px}.header-title{font-size:18px}.header-badge{font-size:10px;padding:4px 8px}.price-grid{gap:6px;padding:0 12px 12px}.price-value{font-size:16px}.chart-wrap{padding:10px 8px}.chart-box{min-height:230px}.chart-tooltip{font-size:10.5px;min-width:124px}.schedule-table th:first-child{width:42px}.schedule-table th:nth-child(2){width:26%}.schedule-table .schedule-time{width:42px}.schedule-table .schedule-main{width:26%}.section-header{padding:10px 12px}.schedule-detail-modal{padding:8px}.schedule-detail-panel{height:calc(100vh - 16px);height:calc(100dvh - 16px);border-radius:14px}}
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily Issue Report HTML 리포트 생성", allow_abbrev=False)
    parser.add_argument("--date", help="기준일 YYYY-MM-DD")
    parser.add_argument("--report-dir", default="data/reports", help="report JSON 폴더")
    parser.add_argument("--out-dir", default="docs/reports", help="HTML 출력 폴더")
    parser.add_argument("--input", help="입력 report JSON 파일")
    parser.add_argument("--output", help="출력 HTML 파일")
    parser.add_argument("--report-slot", choices=["morning", "evening"], default="morning", help="호출한 보고서 슬롯")
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


def news_window_labels(date_text: str) -> tuple[str, str]:
    try:
        d = datetime.strptime(date_text, "%Y-%m-%d")
    except Exception:
        today = short_date(date_text)
        return f"{today} 08:00", f"{today} 17:00"
    prev = d - timedelta(days=1)
    prev_label = f"{prev.month}/{prev.day}"
    today_label = f"{d.month}/{d.day}"
    return (
        f"{prev_label} 17:00 - {today_label} 08:00",
        f"{today_label} 08:00 - 17:00",
    )




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


def section(num: int, title: str, body: str, class_name: str = "", action_html: str = "") -> str:
    klass = f"section {class_name}".strip()
    action = action_html or ""
    return f"""
<section class="{klass}">
  <div class="section-header"><div class="section-heading"><span class="section-num">{num}</span><span class="section-title">{esc(title)}</span></div>{action}</div>
  {body}
</section>
"""


def schedule_detail_button(date_text: str) -> str:
    src = f"../schedules/{date_text}.html"
    return f'<button type="button" class="section-detail-btn" data-schedule-detail-open data-schedule-detail-src="{esc(src)}">상세</button>'


def schedule_detail_modal() -> str:
    return """
<div id="scheduleDetailModal" class="schedule-detail-modal" hidden aria-hidden="true">
  <div class="schedule-detail-panel" role="dialog" aria-modal="true" aria-label="전체 일정 상세">
    <div class="schedule-detail-topbar"><span>전체 일정</span><button type="button" class="schedule-detail-close" data-schedule-detail-close>닫기</button></div>
    <div class="schedule-detail-fallback" data-schedule-detail-fallback>상세 일정 파일을 찾을 수 없습니다.</div>
    <iframe id="scheduleDetailFrame" class="schedule-detail-frame" title="전체 일정 상세"></iframe>
  </div>
</div>
""".strip()


def text_of(item: Any) -> str:
    if isinstance(item, Mapping):
        for key in ("text", "summary", "description", "desc", "title", "name", "content"):
            if item.get(key):
                return clean_text(item.get(key))
        return clean_text(" ".join(str(v) for v in item.values() if isinstance(v, (str, int, float))))
    return clean_text(item)


def render_summary(data: Mapping[str, Any]) -> str:
    rows = []
    for item in list_of(data.get("summary")):
        if isinstance(item, Mapping) and item.get("type") == "stakeholder":
            continue
        text = text_of(item)
        if text.startswith("전일 주요 이슈:") or text.startswith("주요 이해관계자 동향:"):
            continue
        if text.startswith("주요 이해관계자 동향:"):
            text = "전일 주요 이슈:" + text.split(":", 1)[1]
        if text.startswith("전일 주요 이슈:") and "관련 자료 찾지 못함" in text:
            text = "전일 주요 이슈: 주요 동향 없음."
        if text.startswith("금일 주요 일정:") and "관련 자료 찾지 못함" in text:
            text = "금일 주요 일정: 주요 일정 없음."
        if text:
            rows.append(f'<div class="summary-item"><span class="summary-dot"></span><span>{esc(text)}</span></div>')
    return '<div class="summary-body">' + "\n".join(rows[:4]) + '</div>'


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


def normalize_issue_compare(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\b\d{1,2}[:：]\d{2}\b", "", text)
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE).lower()


def split_issue_title_time_location(title: str) -> tuple[str, str, str]:
    title = clean_text(title)
    parsed_time = ""
    location = ""
    while True:
        match = re.search(r"\(([^()]*)\)\s*$", title)
        if not match:
            break
        inner = clean_text(match.group(1))
        inner_time_match = re.search(r"\b\d{1,2}[:：]\d{2}\b", inner)
        if inner_time_match and not parsed_time:
            parsed_time = inner_time_match.group(0).replace("：", ":")
        inner_location = clean_text(re.sub(r"\b\d{1,2}[:：]\d{2}\b", "", inner))
        if inner_location:
            location = inner_location if not location else f"{inner_location} · {location}"
        title = clean_text(title[:match.start()])
    leading_time = re.match(r"^\b\d{1,2}[:：]\d{2}\b", title)
    if leading_time and not parsed_time:
        parsed_time = leading_time.group(0).replace("：", ":")
    title = re.sub(r"^\b\d{1,2}[:：]\d{2}\b\s*", "", title).strip()
    if "," in title:
        left, right = [part.strip() for part in title.split(",", 1)]
        if any(role in left for role in ["장관", "차관", "위원장", "의장", "지사", "시장", "대표", "원내대표"]) and right:
            title = right
    return title, parsed_time, location


def issue_desc_for_display(item: Mapping[str, Any], display_title: str, parsed_time: str, location: str) -> str:
    raw_desc = clean_text(item.get("description") or item.get("desc") or item.get("summary") or item.get("impact") or "")
    time = clean_text(item.get("time") or item.get("start_time") or parsed_time)
    org = clean_text(item.get("org") or item.get("organization") or item.get("agency") or "")
    item_location = clean_text(item.get("location") or location)

    desc_parts = []
    if time and time != "시간미정":
        desc_parts.append(time)
    if org:
        desc_parts.append(org)
    if item_location:
        desc_parts.append(item_location)
    canonical_desc = " · ".join(desc_parts)

    # Section 5 is schedule-derived: render the meta line from normalized
    # fields, so legacy description text cannot repeat the title or omit place.
    if canonical_desc:
        return canonical_desc

    if raw_desc:
        # 방어 로직: 설명에 제목(또는 괄호 포함 제목)이 그대로 포함된 경우 제거
        try:
            # 제목 그대로 또는 괄호 포함 형태가 반복되어 들어오면 제거
            if display_title:
                raw_desc = re.sub(re.escape(display_title), "", raw_desc, flags=re.I)
                raw_desc = re.sub(rf"{re.escape(display_title)}\s*\([^)]*\)", "", raw_desc, flags=re.I)
        except Exception:
            pass
        raw_desc = raw_desc.replace("/", " · ")
        parts = [clean_text(part) for part in re.split(r"\s*·\s*", raw_desc) if clean_text(part)]
        kept = []
        title_n = normalize_issue_compare(display_title)
        for part in parts:
            part_n = normalize_issue_compare(part)
            if title_n and part_n and (part_n in title_n or title_n in part_n):
                continue
            # 추가 방어: 파트 자체가 제목을 포함하거나 제목이 파트에 포함되는 경우 제외
            if display_title and display_title.strip():
                if display_title.strip() in part or part in display_title.strip():
                    continue
            kept.append(part)
        if kept:
            return " · ".join(kept)

    desc_parts = []
    if time and time != "시간미정":
        desc_parts.append(time)
    if org:
        desc_parts.append(org)
    if item_location:
        desc_parts.append(item_location)
    return " · ".join(desc_parts) or "세부 정보 확인 필요"


def normalize_links(item: Mapping[str, Any]) -> list[dict[str, str]]:
    raw = item.get("links") or item.get("related_links") or []
    out = []
    if isinstance(raw, list):
        for link in raw[:3]:
            if isinstance(link, Mapping):
                label = clean_text(link.get("label") or link.get("title") or "관련 자료")
                url = str(link.get("url") or "").strip()
                if label or url:
                    out.append({"url": url, "label": label or "관련 자료"})
    if not out:
        out.append({"url": "", "label": "관련 기사 없음"})
    return out


def render_issues(data: Mapping[str, Any]) -> str:
    rows = []
    for item in list_of(data.get("issues"))[:8]:
        if not isinstance(item, Mapping):
            continue
        tag = clean_text(item.get("tag") or item.get("category") or "동향")
        raw_title = clean_text(item.get("title") or item.get("name") or "주요 동향")
        title, parsed_time, location = split_issue_title_time_location(raw_title)
        title = title or raw_title
        desc = issue_desc_for_display(item, title, parsed_time, location)
        links = normalize_links(item)
        link_html = ""
        if links:
            rendered_links = []
            for l in links:
                if l.get("url"):
                    rendered_links.append(f'<a href="{esc(l["url"])}" target="_blank" rel="noopener noreferrer">{esc(l["label"])}</a>')
                else:
                    rendered_links.append(f'<span>{esc(l["label"])}</span>')
            link_html = '<div class="issue-links">관련 링크' + ''.join(rendered_links) + '</div>'
        rows.append(f'<div class="issue-card"><div class="issue-tag">{esc(tag)}</div><div class="issue-title">{esc(title)}</div><div class="issue-desc">{esc(desc)}</div>{link_html}</div>')
    if not rows:
        rows.append('<div class="issue-card"><div class="issue-tag">확인</div><div class="issue-title">전일 주요 동향 데이터 확인 필요</div><div class="issue-desc">전일 일정·이슈 데이터가 비어 있음</div></div>')
    return '<div class="issue-list">' + ''.join(rows) + '</div><div class="fact-note">※ 관련 링크가 없는 항목은 일정·보도자료 원문 확인 범위 내에서 작성</div>'


def render_schedules(data: Mapping[str, Any]) -> str:
    rows = []
    for item in list_of(data.get("schedules"))[:12]:
        if not isinstance(item, Mapping):
            continue
        time = clean_text(item.get("time") or item.get("start_time") or "-")
        title = clean_text(item.get("title") or item.get("name") or item.get("event") or "일정 확인 필요")
        attendees = clean_text(item.get("attendees") or item.get("participant") or item.get("participants") or item.get("org") or item.get("organization") or item.get("agency") or "-")
        rel = clean_text(item.get("relevance") or item.get("impact") or item.get("description") or item.get("desc") or "")
        rel_html = f'<div class="schedule-rel">{esc(rel)}</div>' if rel else ''
        rows.append(f'<tr class="schedule-row"><td class="schedule-time">{esc(time)}</td><td class="schedule-main">{esc(title)}{rel_html}</td><td class="schedule-attendees">{esc(attendees)}</td></tr>')
    if not rows:
        validation = dict_of(dict_of(data.get("automation")).get("validation"))
        if validation.get("today_schedule_parse_failed") or validation.get("today_schedule_status") == "parse_failed":
            title = "금일 주요 일정 데이터 확인 필요"
            rel = "일정 원문 수집 또는 파싱 결과 확인 필요."
        else:
            title = "주요 일정 없음"
            rel = "확인된 정유·석유화학·LNG 관련 주요 일정이 없습니다."
        rows.append(f'<tr class="schedule-row"><td class="schedule-time">-</td><td class="schedule-main">{esc(title)}<div class="schedule-rel">{esc(rel)}</div></td><td class="schedule-attendees">-</td></tr>')
    return '<div class="schedule-list"><table class="schedule-table"><thead><tr><th>시간</th><th>일정</th><th>참석자</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def get_news(data: Mapping[str, Any], key: str = "news_trend") -> tuple[str, list[Mapping[str, Any]]]:
    news = dict_of(data.get(key))
    summary = clean_text(news.get("summary") or news.get("trend") or news.get("text") or "")
    articles = [a for a in list_of(news.get("articles")) if isinstance(a, Mapping) and a.get("title")]
    return summary, articles[:5]


def strip_article_source_suffix(text: str, press: str = "") -> str:
    text = clean_text(text)
    press = clean_text(press)
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


def fallback_article_desc(title: str) -> str:
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


def article_desc_for_display(article: Mapping[str, Any]) -> str:
    title = clean_text(article.get("title") or "")
    press = clean_text(article.get("press") or article.get("source") or article.get("publisher") or "")
    desc = clean_text(article.get("summary") or article.get("description") or article.get("desc") or "")
    if is_repeated_article_desc(title, desc, press):
        return fallback_article_desc(title)
    return strip_article_source_suffix(desc, press)


def render_afternoon_news_placeholder() -> str:
    return (
        '<div class="news-body">'
        '<div class="news-trend">17:30 업데이트 예정입니다.</div>'
        '<div class="news-separator"></div>'
        '<div class="news-links-title">대표 기사</div>'
        '<div class="news-link">'
        '<div class="news-link-title">오후 News Trend 데이터 대기</div>'
        '<div class="news-link-press">-</div>'
        '<div class="news-link-desc">당일 08:00~17:00 발간 기사 기준으로 추후 자동 업데이트됩니다.</div>'
        '</div>'
        '</div>'
        '<div class="fact-note">※ 오후 트렌드는 당일 08:00~17:00 KST 발간 기사 기준으로 작성 예정.</div>'
    )


def render_news(data: Mapping[str, Any], key: str = "news_trend", empty_summary: str = "기준일 조간 신문 트렌드 확인 필요.", fact_note: str | None = None, empty_article_desc: str = "조간 기사 후보가 report JSON에 반영되지 않음") -> str:
    summary, articles = get_news(data, key)
    if not summary:
        if articles:
            summary = " · ".join(clean_text(a.get("title")) for a in articles[:3])
        else:
            summary = empty_summary
    rows = []
    for a in articles:
        url = str(a.get("url") or "#").strip() or "#"
        title = clean_text(a.get("title") or "기사 제목 확인 필요")
        press = clean_text(a.get("press") or a.get("source") or a.get("publisher") or "출처 확인")
        desc = article_desc_for_display(a)
        desc_html = f'<div class="news-link-desc">{esc(desc)}</div>' if desc else ''
        # 중요: 긴 URL 텍스트는 출력하지 않고, 제목에만 href를 건다.
        rows.append(f'<a class="news-link" href="{esc(url)}" target="_blank" rel="noopener noreferrer"><div class="news-link-title">{esc(title)}</div><div class="news-link-press">{esc(press)}</div>{desc_html}</a>')
    if not rows:
        rows.append(f'<div class="news-link"><div class="news-link-title">대표 기사 데이터 확인 필요</div><div class="news-link-press">-</div><div class="news-link-desc">{esc(empty_article_desc)}</div></div>')
    if fact_note is None:
        fact_note = "※ 조간 트렌드는 웹 확인 가능한 기준일 오전 보도 중 정유·석유화학·LNG 업계 관련성이 높은 기사 중심 작성."
    return f'<div class="news-body"><div class="news-trend">{esc(summary)}</div><div class="news-separator"></div><div class="news-links-title">대표 기사</div>{"".join(rows)}</div><div class="fact-note">{esc(fact_note)}</div>'


def render_afternoon_news(data: Mapping[str, Any]) -> str:
    summary, articles = get_news(data, "news_trend_afternoon")
    if not summary and not articles:
        return render_afternoon_news_placeholder()
    return render_news(
        data,
        key="news_trend_afternoon",
        empty_summary="기준일 오후 신문 트렌드 확인 필요.",
        fact_note="※ 오후 트렌드는 당일 08:00~17:00 KST 발간 기사 중 정유·석유화학·LNG 업계 관련성이 높은 기사 중심 작성.",
        empty_article_desc="오후 기사 후보가 report JSON에 반영되지 않음",
    )



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


SCHEDULE_DETAIL_SCRIPT = r"""
<script>
(function(){
  var modal = document.getElementById('scheduleDetailModal');
  var frame = document.getElementById('scheduleDetailFrame');
  if(!modal || !frame) return;
  var closeBtn = modal.querySelector('[data-schedule-detail-close]');
  var fallback = modal.querySelector('[data-schedule-detail-fallback]');
  var previousOverflow = "";

  function showFallback(){
    if(fallback) fallback.classList.add('is-visible');
    frame.style.display = 'none';
  }

  function hideFallback(){
    if(fallback) fallback.classList.remove('is-visible');
    frame.style.display = 'block';
  }

  function openModal(src){
    if(!src) return;
    hideFallback();
    previousOverflow = document.body.style.overflow || "";
    document.body.style.overflow = "hidden";
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    modal.classList.add('is-open');
    frame.removeAttribute('src');
    frame.src = src;
    if(window.fetch){
      fetch(src, {method: 'HEAD', cache: 'no-store'}).then(function(response){
        if(!response.ok) showFallback();
      }).catch(function(){});
    }
  }

  function closeModal(){
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    modal.hidden = true;
    frame.removeAttribute('src');
    hideFallback();
    document.body.style.overflow = previousOverflow;
  }

  document.querySelectorAll('[data-schedule-detail-open]').forEach(function(btn){
    btn.addEventListener('click', function(){
      openModal(btn.getAttribute('data-schedule-detail-src'));
    });
  });
  if(closeBtn) closeBtn.addEventListener('click', closeModal);
  modal.addEventListener('click', function(e){
    if(e.target === modal) closeModal();
  });
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape' && modal.classList.contains('is-open')) closeModal();
  });
  window.addEventListener('message', function(e){
    if(e && e.data && e.data.type === 'closeScheduleDetail') closeModal();
  });
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
    morning_news_label, afternoon_news_label = news_window_labels(date_text)
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
    {section(5, f"금일 주요 일정 ({today_label})", render_schedules(data), action_html=schedule_detail_button(date_text))}
    {section(6, f"News Trend - Morning ({morning_news_label})", render_news(data))}
    {section(7, f"News Trend - Evening ({afternoon_news_label})", render_afternoon_news(data))}
    <footer class="footer">SK Innovation Communication Division · {esc(date_text.replace('-', '.'))}</footer>
  </main>
  {schedule_detail_modal()}
  {TOOLTIP_SCRIPT}
  {SCHEDULE_DETAIL_SCRIPT}
</body>
</html>
"""
    return html_text


def main() -> int:
    args = parse_args()
    input_path, output_path, date_text = resolve_paths(args)
    if not input_path.exists():
        raise FileNotFoundError(f"입력 JSON을 찾을 수 없습니다: {input_path}")
    # 일부 report JSON에 UTF-8 BOM이 포함될 수 있어 'utf-8-sig'로 안전하게 읽음
    data = json.loads(input_path.read_text(encoding="utf-8-sig"))
    date_text = get_report_date(data, date_text)
    if not args.output:
        output_path = Path(args.out_dir) / f"{date_text}.html"
    html_text = render(data, date_text)
    atomic_write(output_path, html_text)
    print(f"[OK] HTML 리포트 생성 완료: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
