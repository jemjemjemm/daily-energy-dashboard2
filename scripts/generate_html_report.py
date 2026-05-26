#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_html_report.py

Render data/reports/YYYY-MM-DD.report.json to docs/reports/YYYY-MM-DD.html.
This renderer only changes presentation. It does not collect news, parse schedules,
or merge prices.

Compatible calls:
  python scripts/generate_html_report.py --date 2026-05-26 --report-dir data/reports --out-dir docs/reports
  python scripts/generate_html_report.py --input data/reports/2026-05-26.report.json --output docs/reports/2026-05-26.html
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily 유가 동향 HTML 리포트 생성", allow_abbrev=False)
    parser.add_argument("--date", help="기준일 YYYY-MM-DD")
    parser.add_argument("--report-dir", default="data/reports", help="report JSON 폴더")
    parser.add_argument("--out-dir", default="docs/reports", help="HTML 출력 폴더")
    parser.add_argument("--input", help="입력 report JSON 파일")
    parser.add_argument("--output", help="출력 HTML 파일")
    return parser.parse_args()


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def text_of(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "summary", "description", "desc", "title", "name", "content"):
            if value.get(key):
                return str(value.get(key)).strip()
        return " ".join(str(v).strip() for v in value.values() if isinstance(v, (str, int, float)) and str(v).strip())
    return str(value).strip()


def list_of(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def get_report_date(data: Dict[str, Any], fallback: str = "") -> str:
    report = data.get("report") if isinstance(data.get("report"), dict) else {}
    return str(report.get("report_date") or data.get("date") or fallback or "").strip()


def display_date_from(date_text: str, data: Dict[str, Any]) -> str:
    report = data.get("report") if isinstance(data.get("report"), dict) else {}
    if report.get("display_date"):
        return str(report["display_date"])
    if not date_text:
        return ""
    try:
        d = datetime.strptime(date_text, "%Y-%m-%d")
        weekdays = "월화수목금토일"
        return f"{d.year}년 {d.month}월 {d.day}일 ({weekdays[d.weekday()]})"
    except Exception:
        return date_text


def short_date(date_text: str) -> str:
    try:
        d = datetime.strptime(date_text, "%Y-%m-%d")
        return f"{d.month}/{d.day}"
    except Exception:
        return date_text


def normalize_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    # 과도한 구어체/존댓말 안내문을 보고서형으로 최소 보정
    replacements = {
        "확인됩니다": "확인",
        "확인되었습니다": "확인",
        "필요합니다": "필요",
        "보도했습니다": "보도",
        "분석했습니다": "분석",
        "전망했습니다": "전망",
        "나타났습니다": "나타남",
        "있습니다": "있음",
        "없습니다": "없음",
        "입니다": "",
        "합니다": "함",
    }
    for a, b in replacements.items():
        if text.endswith(a):
            text = text[: -len(a)] + b
            break
    return text


def get_summary_items(data: Dict[str, Any]) -> List[str]:
    items = []
    for item in list_of(data.get("summary")):
        t = normalize_sentence(text_of(item))
        if t:
            items.append(t)
    while len(items) < 3:
        defaults = [
            "전일 주요 이해관계자·정책 동향은 일정 및 기사 기준 확인 필요",
            "금일 주요 일정은 정부·국회·산업 현안과의 연계 가능성 중심 모니터링 필요",
            "조간 보도는 정유·석유화학·LNG 업계 관련 대표 기사 중심 정리",
        ]
        items.append(defaults[len(items)])
    return items[:3]


def find_price_block(data: Dict[str, Any]) -> Dict[str, Any]:
    prices = data.get("prices") if isinstance(data.get("prices"), dict) else {}
    return prices


def as_number(value: Any) -> Optional[float]:
    if value in (None, "", "-", "N/A"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def pick_price(prices: Dict[str, Any], names: Iterable[str]) -> Optional[float]:
    # Search recursively in common price structures.
    name_set = {n.lower() for n in names}

    def walk(obj: Any) -> Optional[float]:
        if isinstance(obj, dict):
            # direct value by key
            for k, v in obj.items():
                kl = str(k).lower()
                if kl in name_set or any(n in kl for n in name_set):
                    if isinstance(v, dict):
                        for vk in ("value", "price", "latest", "current", "close"):
                            num = as_number(v.get(vk))
                            if num is not None:
                                return num
                        num = walk(v)
                        if num is not None:
                            return num
                    else:
                        num = as_number(v)
                        if num is not None:
                            return num
            for v in obj.values():
                num = walk(v)
                if num is not None:
                    return num
        elif isinstance(obj, list):
            for item in reversed(obj):
                num = walk(item)
                if num is not None:
                    return num
        return None

    return walk(prices)


def price_cards(data: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    prices = find_price_block(data)
    note = str(prices.get("price_data_note") or prices.get("note") or "") if isinstance(prices, dict) else ""
    crude = [
        {"label": "Brent", "value": pick_price(prices, ["brent"])},
        {"label": "WTI", "value": pick_price(prices, ["wti"])},
        {"label": "Dubai", "value": pick_price(prices, ["dubai"])},
    ]
    product = [
        {"label": "휘발유", "value": pick_price(prices, ["gasoline", "휘발유", "92ron"])},
        {"label": "경유", "value": pick_price(prices, ["diesel", "gasoil", "경유"])},
        {"label": "나프타", "value": pick_price(prices, ["naphtha", "나프타"])},
    ]
    return crude, product, note


def extract_series(data: Dict[str, Any], group: str) -> List[Dict[str, Any]]:
    prices = find_price_block(data)
    candidates = []
    if isinstance(prices, dict):
        for key in (f"{group}_chart", f"{group}_series", f"{group}_history", "chart_data", "history"):
            v = prices.get(key)
            if isinstance(v, list):
                candidates = v
                break
            if isinstance(v, dict):
                for vv in v.values():
                    if isinstance(vv, list):
                        candidates = vv
                        break
    # filter date-like rows
    rows = []
    for row in candidates:
        if isinstance(row, dict) and (row.get("date") or row.get("label")):
            rows.append(row)
    return rows[-65:]


def make_svg(rows: List[Dict[str, Any]], keys: List[tuple[str, str, str]]) -> str:
    if not rows:
        return '<div class="chart-empty">그래프 데이터 없음</div>'
    values = []
    for r in rows:
        for k, _, _ in keys:
            n = as_number(r.get(k))
            if n is not None:
                values.append(n)
    if not values:
        return '<div class="chart-empty">그래프 데이터 없음</div>'
    min_v, max_v = min(values), max(values)
    if min_v == max_v:
        min_v -= 1; max_v += 1
    pad = (max_v - min_v) * 0.12
    min_v -= pad; max_v += pad
    W,H = 440,230; left,right,top,bottom = 38,10,16,32
    pw,ph = W-left-right, H-top-bottom
    def x(i:int)->float: return left + (0 if len(rows)<=1 else i/(len(rows)-1)*pw)
    def y(v:float)->float: return top + (max_v-v)/(max_v-min_v)*ph
    grid = []
    for i in range(5):
        val = min_v + (max_v-min_v)*i/4
        yy = y(val)
        grid.append(f'<line x1="{left}" x2="{W-right}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="rgba(0,0,0,.08)"/><text x="{left-5}" y="{yy+3:.1f}" text-anchor="end" font-size="9" fill="#888">{val:.0f}</text>')
    paths=[]
    for key, label, color in keys:
        pts=[]
        for i,r in enumerate(rows):
            n=as_number(r.get(key))
            if n is not None:
                pts.append(f'{x(i):.1f},{y(n):.1f}')
        if len(pts)>=2:
            paths.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
    labels=[]
    for idx in sorted(set([0, max(0,len(rows)//3), max(0,(len(rows)*2)//3), len(rows)-1])):
        label = rows[idx].get("label") or short_date(str(rows[idx].get("date","")))
        labels.append(f'<text x="{x(idx):.1f}" y="222" text-anchor="middle" font-size="9" fill="#888">{esc(label)}</text>')
    return f'<svg class="chart-svg" viewBox="0 0 {W} {H}" role="img" aria-label="가격 추이 그래프">{"".join(grid)}{"".join(paths)}{"".join(labels)}</svg>'


def get_issues(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues = list_of(data.get("issues"))
    return [x for x in issues if isinstance(x, dict)][:8]


def get_schedules(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    schedules = list_of(data.get("schedules"))
    return [x for x in schedules if isinstance(x, dict)][:12]


def get_news(data: Dict[str, Any]) -> tuple[str, List[Dict[str, Any]]]:
    news = data.get("news_trend") if isinstance(data.get("news_trend"), dict) else {}
    summary = text_of(news.get("summary") or news.get("trend") or news.get("text"))
    articles = [a for a in list_of(news.get("articles")) if isinstance(a, dict)]
    return normalize_sentence(summary), articles[:5]


def issue_html(issue: Dict[str, Any]) -> str:
    tag = issue.get("tag") or issue.get("category") or "동향"
    title = issue.get("title") or issue.get("name") or "주요 동향"
    desc = issue.get("description") or issue.get("desc") or issue.get("summary") or issue.get("impact") or "세부 내용 확인 필요"
    links = issue.get("links") if isinstance(issue.get("links"), list) else []
    link_html = ""
    if links:
        items=[]
        for l in links[:3]:
            if isinstance(l, dict) and l.get("url"):
                items.append(f'<a href="{esc(l.get("url"))}" target="_blank" rel="noopener">{esc(l.get("title") or l.get("url"))}</a>')
        if items:
            link_html = '<div class="issue-links"><span>관련 링크</span>' + ''.join(items) + '</div>'
    return f'<div class="issue-card"><div class="issue-tag">{esc(tag)}</div><div class="issue-title">{esc(title)}</div><div class="issue-desc">{esc(normalize_sentence(str(desc)))}</div>{link_html}</div>'


def schedule_html(row: Dict[str, Any]) -> str:
    time = row.get("time") or row.get("start_time") or "-"
    org = row.get("org") or row.get("organization") or row.get("agency") or "-"
    title = row.get("title") or row.get("name") or row.get("event") or "일정 확인 필요"
    rel = row.get("relevance") or row.get("impact") or row.get("description") or row.get("desc") or "세부 안건은 일정 자료 기준 확인 필요"
    return f'<div class="schedule-row"><div class="schedule-time">{esc(time)}</div><div class="schedule-org">{esc(org)}</div><div class="schedule-main"><div>{esc(title)}</div><div class="schedule-rel">{esc(normalize_sentence(str(rel)))}</div></div></div>'


def render(data: Dict[str, Any], date_text: str) -> str:
    display_date = display_date_from(date_text, data)
    today_label = short_date(date_text)
    report = data.get("report") if isinstance(data.get("report"), dict) else {}
    badge = report.get("report_badge") or "정유 · 석유화학 · LNG"
    summary_items = get_summary_items(data)
    crude_cards, product_cards, price_note = price_cards(data)
    crude_series = extract_series(data, "crude")
    product_series = extract_series(data, "product")
    issues = get_issues(data)
    schedules = get_schedules(data)
    news_summary, articles = get_news(data)

    def card(c):
        v = c.get("value")
        val = "-" if v is None else f"{v:.2f}"
        return f'<div class="price-card"><div class="price-label">{esc(c["label"])}</div><div class="price-value">{val}</div><div class="price-unit">$/Bbl</div></div>'

    article_html = ""
    for a in articles:
        url = a.get("url") or "#"
        title = a.get("title") or "기사 제목 확인 필요"
        press = a.get("press") or a.get("source") or a.get("publisher") or "출처 확인"
        desc = a.get("summary") or a.get("description") or a.get("desc") or "기사 주요 내용 확인 필요"
        article_html += f'<a class="news-link" href="{esc(url)}" target="_blank" rel="noopener"><div class="news-link-title">{esc(title)}</div><div class="news-link-press">{esc(press)}</div><div class="news-link-desc">{esc(normalize_sentence(str(desc)))}</div><div class="news-url">{esc(url)}</div></a>'
    if not article_html:
        article_html = '<div class="news-link"><div class="news-link-title">대표 기사 데이터 확인 필요</div><div class="news-link-desc">조간 기사 후보가 report JSON에 반영되지 않음</div></div>'

    issues_html = ''.join(issue_html(i) for i in issues) or '<div class="issue-card"><div class="issue-tag">확인</div><div class="issue-title">전일 주요 동향 데이터 확인 필요</div><div class="issue-desc">전일 일정·이슈 데이터가 비어 있음</div></div>'
    schedules_html = ''.join(schedule_html(s) for s in schedules) or '<div class="schedule-row"><div class="schedule-time">-</div><div class="schedule-org">-</div><div class="schedule-main"><div>금일 주요 일정 데이터 확인 필요</div><div class="schedule-rel">일정 데이터가 비어 있음</div></div></div>'

    crude_svg = make_svg(crude_series, [("Brent","Brent","#1A6FD4"),("WTI","WTI","#E24B4A"),("Dubai","Dubai","#1D9E75")])
    product_svg = make_svg(product_series, [("Gasoline","Gasoline","#1A6FD4"),("Diesel","Diesel","#E24B4A"),("Naphtha","Naphtha","#1D9E75")])

    css = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;800&display=swap');
*{box-sizing:border-box}body{margin:0;padding:16px;background:#F4F5F7;color:#1A1A1A;font-family:'Noto Sans KR',sans-serif;font-size:14px;line-height:1.6}.container{max-width:480px;margin:0 auto}.header{background:#0A2444;color:#fff;padding:18px 16px 14px;border-radius:12px 12px 0 0}.header-top{display:flex;justify-content:space-between;gap:12px}.header-title{font-size:20px;font-weight:800}.header-date{font-size:12px;color:rgba(255,255,255,.65);margin-top:3px}.header-badge{font-size:11px;background:rgba(255,255,255,.12);border-radius:20px;padding:4px 10px;height:fit-content;white-space:nowrap}.section{background:#fff;border:1px solid #E5E7EB;border-radius:12px;margin:10px 0;overflow:hidden}.section-header{display:flex;align-items:center;gap:8px;padding:11px 16px;border-bottom:1px solid #E5E7EB;background:#F8F9FA}.section-num{font-size:11px;font-weight:800;color:#fff;background:#0A2444;border-radius:4px;padding:2px 7px;min-width:24px;text-align:center}.section-title{font-size:14px;font-weight:800}.summary-body,.news-body{padding:14px 16px}.summary-item{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #F0F0F0;font-size:13px;line-height:1.65}.summary-item:last-child{border-bottom:none}.summary-dot{flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:#1A6FD4;margin-top:8px}.price-section-label{font-size:12px;font-weight:600;color:#666;padding:12px 16px 6px}.price-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:0 16px 14px}.price-card{background:#F8F9FA;border-radius:8px;padding:10px 8px;text-align:center}.price-label{font-size:11px;color:#666;margin-bottom:4px}.price-value{font-size:18px;font-weight:800;line-height:1}.price-unit{font-size:10px;color:#999;margin-top:2px}.divider{height:1px;background:#F0F0F0;margin:0 16px 4px}.chart-wrap{padding:12px 14px}.chart-legend{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px;font-size:12px;color:#666}.legend-item{display:flex;align-items:center;gap:5px}.legend-dot{width:12px;height:3px;border-radius:2px}.chart-svg{width:100%;height:auto;display:block}.chart-empty{height:190px;display:flex;align-items:center;justify-content:center;color:#999;background:#F8F9FA;border-radius:10px}.issue-list,.schedule-list{padding:10px 12px}.issue-card{background:#F8F9FA;border-radius:8px;padding:12px 14px;margin-bottom:8px;border-left:3px solid #1A6FD4}.issue-tag{display:inline-block;font-size:10px;font-weight:800;background:#E6F1FB;color:#185FA5;border-radius:3px;padding:2px 6px;margin-bottom:6px}.issue-title{font-size:13px;font-weight:800;margin-bottom:5px;line-height:1.5}.issue-desc{font-size:12px;color:#444;line-height:1.65}.issue-links{margin-top:9px;display:flex;flex-direction:column;gap:4px;font-size:11px}.issue-links a{color:#0A2444;text-decoration:underline;word-break:break-all}.schedule-row{display:flex;align-items:flex-start;gap:8px;padding:9px 0;border-bottom:1px solid #F0F0F0}.schedule-row:last-child{border-bottom:none}.schedule-time{flex:0 0 38px;font-size:11px;font-weight:800;color:#185FA5;margin-top:1px}.schedule-org{flex:0 0 48px;font-size:10px;background:#F0F1F3;border:1px solid #E0E0E0;border-radius:3px;padding:1px 4px;color:#555;text-align:center}.schedule-main{flex:1;font-size:12px;line-height:1.5}.schedule-rel{font-size:11px;color:#777;margin-top:2px}.note{padding:0 16px 14px;font-size:11px;color:#999}.news-trend{font-size:13px;line-height:1.75;margin-bottom:14px}.news-separator{height:1px;background:#F0F0F0;margin:12px 0}.news-links-title{font-size:11px;font-weight:800;color:#999;letter-spacing:.5px;margin-bottom:8px}.news-link{display:block;padding:9px 0;border-bottom:1px solid #F0F0F0;text-decoration:none;color:inherit}.news-link-title{font-size:13px;font-weight:700;color:#0A2444;line-height:1.45;text-decoration:underline}.news-link-press{font-size:11px;color:#888;margin:2px 0}.news-link-desc{font-size:11px;color:#555;line-height:1.55}.news-url{font-size:10px;color:#999;word-break:break-all;margin-top:4px}.fact-note{font-size:11px;color:#888;background:#F8F9FA;border-top:1px solid #E5E7EB;padding:10px 16px}.footer{text-align:center;padding:12px;font-size:11px;color:#aaa;border-top:1px solid #E5E7EB;margin-top:4px}@media(max-width:430px){body{padding:10px}.header-title{font-size:18px}.header-badge{font-size:10px;padding:4px 8px}.section-header{padding:10px 12px}.summary-body,.news-body{padding:12px}.price-grid{gap:6px;padding:0 12px 12px}.price-card{padding:9px 4px}.price-value{font-size:16px}.chart-wrap{padding:10px 8px}.chart-legend{gap:8px;font-size:11px;margin-left:4px}.schedule-org{flex-basis:42px}}
"""
    return f'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"/><title>Daily 유가 동향 — {esc(date_text.replace('-', '.'))}</title><style>{css}</style></head>
<body><div class="container">
<div class="header"><div class="header-top"><div><div class="header-title">Daily 유가 동향</div><div class="header-date">{esc(display_date)}</div></div><div class="header-badge">{esc(badge)}</div></div></div>
<div class="section"><div class="section-header"><span class="section-num">1</span><span class="section-title">Summary</span></div><div class="summary-body">
{''.join(f'<div class="summary-item"><div class="summary-dot"></div><div>{esc(t)}</div></div>' for t in summary_items)}
</div></div>
<div class="section"><div class="section-header"><span class="section-num">2</span><span class="section-title">유가 동향</span></div>
<div class="price-section-label">원유 ($/Bbl) — {esc(today_label)} 기준</div><div class="price-grid">{''.join(card(c) for c in crude_cards)}</div>
<div class="divider"></div><div class="price-section-label">석유제품 ($/Bbl) — {esc(today_label)} 기준</div><div class="price-grid">{''.join(card(c) for c in product_cards)}</div>
<div class="note">{esc(price_note or '※ 가격 데이터는 제공 데이터 및 history.json 기준')}</div></div>
<div class="section"><div class="section-header"><span class="section-num">3</span><span class="section-title">원유 가격 추이</span></div><div class="chart-wrap"><div class="chart-legend"><div class="legend-item"><div class="legend-dot" style="background:#1A6FD4"></div>Brent</div><div class="legend-item"><div class="legend-dot" style="background:#E24B4A"></div>WTI</div><div class="legend-item"><div class="legend-dot" style="background:#1D9E75"></div>Dubai</div></div>{crude_svg}</div></div>
<div class="section"><div class="section-header"><span class="section-num">4</span><span class="section-title">석유제품 가격 추이</span></div><div class="chart-wrap"><div class="chart-legend"><div class="legend-item"><div class="legend-dot" style="background:#1A6FD4"></div>Gasoline</div><div class="legend-item"><div class="legend-dot" style="background:#E24B4A"></div>Diesel</div><div class="legend-item"><div class="legend-dot" style="background:#1D9E75"></div>Naphtha</div></div>{product_svg}</div></div>
<div class="section"><div class="section-header"><span class="section-num">5</span><span class="section-title">이해관계자·정책 주요 동향 (전일 기준)</span></div><div class="issue-list">{issues_html}</div><div class="fact-note">※ 일정·이슈 영향도는 보고서 작성 목적의 해석</div></div>
<div class="section"><div class="section-header"><span class="section-num">6</span><span class="section-title">금일 주요 일정 ({esc(today_label)})</span></div><div class="schedule-list">{schedules_html}</div><div class="note">※ 세이프타임즈 일정 텍스트 기준</div></div>
<div class="section"><div class="section-header"><span class="section-num">7</span><span class="section-title">조간 신문 트렌드 ({esc(today_label)})</span></div><div class="news-body"><div class="news-trend">{esc(news_summary or '조간 신문 트렌드는 대표 기사 기준 정리')}</div><div class="news-separator"></div><div class="news-links-title">대표 기사</div>{article_html}</div><div class="fact-note">※ 조간 트렌드는 웹 확인 가능한 보도 중 업계 관련성이 높은 기사 중심 작성</div></div>
<div class="footer">SK Innovation Communication Division · {esc(date_text)}</div></div></body></html>'''


def main() -> int:
    args = parse_args()
    if args.input:
        in_path = Path(args.input)
        date_text = args.date or in_path.name.replace(".report.json", "")
    else:
        if not args.date:
            raise SystemExit("--date 또는 --input이 필요합니다.")
        date_text = args.date
        in_path = Path(args.report_dir) / f"{date_text}.report.json"
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = Path(args.out_dir) / f"{date_text}.html"
    if not in_path.exists():
        raise SystemExit(f"[ERROR] report JSON이 없습니다: {in_path}")
    data = json.loads(in_path.read_text(encoding="utf-8"))
    date_text = get_report_date(data, date_text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(data, date_text), encoding="utf-8")
    print(f"[OK] HTML 리포트 생성 완료: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
