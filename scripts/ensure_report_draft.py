#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_html_report.py v1.2

리포트 JSON을 HTML로 변환합니다.

수정 사항
- 그래프 디자인: 기존처럼 선만 표시. 점(circle)은 전혀 생성하지 않음.
- tooltip: 날짜별 투명 세로 hover 영역(rect)을 사용.
- 마우스를 그래프 위 특정 날짜 영역에 올리면 해당일의 가격을 커스텀 tooltip으로 표시.
- iPhone/모바일에서는 터치 시 tooltip이 잠시 표시됨.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence


CRUDE_COLORS = {"Brent": "#1A6FD4", "WTI": "#E24B4A", "Dubai": "#1D9E75"}
PRODUCT_COLORS = {"Gasoline": "#1A6FD4", "Diesel": "#E24B4A", "Naphtha": "#1D9E75"}


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt(value: Any) -> str:
    try:
        n = float(value)
    except Exception:
        return "-"
    if not math.isfinite(n):
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


def render_summary(items: Sequence[Mapping[str, Any]]) -> str:
    if not items:
        return '<div class="empty">Summary 데이터가 없습니다.</div>'

    rows = []
    for item in items[:5]:
        rows.append(
            '<div class="summary-item"><span class="dot"></span><div>'
            + esc(item.get("text", ""))
            + '</div></div>'
        )
    return "\n".join(rows)


def render_cards(cards: Sequence[Mapping[str, Any]]) -> str:
    if not cards:
        return '<div class="empty">가격 데이터가 없습니다.</div>'

    rows = []
    for c in cards:
        direction = str(c.get("direction", "flat"))
        symbol = {"up": "▲", "down": "▼", "flat": "－"}.get(direction, "－")

        try:
            change = abs(float(c.get("change", 0)))
        except Exception:
            change = 0

        rows.append(
            '<div class="price-card">'
            '<div class="price-label">' + esc(c.get("label", "")) + '</div>'
            '<div class="price-value">' + fmt(c.get("value")) + '</div>'
            '<div class="price-unit">' + esc(c.get("unit", "$/Bbl")) + '</div>'
            '<div class="price-change ' + esc(direction) + '">' + symbol + ' ' + fmt(change) + '</div>'
            '</div>'
        )
    return "\n".join(rows)


def render_schedules(items: Sequence[Mapping[str, Any]]) -> str:
    if not items:
        return '<div class="empty">금일 주요 일정 데이터가 없습니다.</div>'

    rows = []
    for i in items:
        rows.append(
            '<div class="schedule-row">'
            '<div class="schedule-time">' + esc(i.get("time", "")) + '</div>'
            '<div class="schedule-org">' + esc(i.get("org", "")) + '</div>'
            '<div class="schedule-main">'
            '<div>' + esc(i.get("title", "")) + '</div>'
            '<div class="schedule-rel">' + esc(i.get("relevance", "")) + '</div>'
            '</div></div>'
        )
    return "\n".join(rows)


def render_issues(items: Sequence[Mapping[str, Any]]) -> str:
    if not items:
        return '<div class="empty">전일 주요 이슈 데이터가 없습니다.</div>'

    rows = []
    for i in items:
        grade = str(i.get("grade", "C 참고"))
        gcls = "grade-a" if grade.startswith("A") else "grade-b" if grade.startswith("B") else "grade-c"

        rows.append(
            '<div class="issue-card">'
            '<span class="issue-tag">' + esc(i.get("category", "")) + '</span>'
            '<div class="issue-title">' + esc(i.get("title", "")) + '</div>'
            '<div class="issue-desc">' + esc(i.get("description", "")) + '</div>'
            '<div class="issue-footer"><span class="issue-grade ' + gcls + '">' + esc(grade) + '</span></div>'
            '</div>'
        )
    return "\n".join(rows)


def render_news(report: Mapping[str, Any]) -> str:
    news = report.get("news_trend", {}) or {}
    summary = news.get("summary_html") or esc(news.get("summary", "")) or "조간 신문 트렌드 데이터가 아직 없습니다."
    articles = news.get("articles", []) or []

    rows = []
    for idx, a in enumerate(articles[:5], 1):
        url = str(a.get("url", "") or "")
        title = esc(a.get("title", ""))
        press = esc(a.get("press", ""))

        if url:
            link = '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + title + '</a>'
        else:
            link = title

        rows.append(
            '<div class="news-item"><div class="news-num">' + str(idx) + '</div><div>'
            '<div class="news-title">' + link + '</div>'
            '<div class="news-press">' + press + '</div>'
            '</div></div>'
        )

    if not rows:
        rows.append('<div class="empty">대표 기사 데이터가 아직 없습니다.</div>')

    return (
        '<div class="news-summary">' + summary + '</div>'
        '<div class="section-divider"></div>'
        '<div class="small-title">대표 기사</div>'
        + "".join(rows)
    )


def render_quality(report: Mapping[str, Any]) -> str:
    q = report.get("quality_control", {}) or {}
    sources = q.get("sources", []) or []

    source_rows = []
    for s in sources:
        name = esc(s.get("name", ""))
        typ = esc(s.get("type", ""))
        url = str(s.get("url", "") or "")

        if url:
            source_rows.append(
                '<li><a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">'
                + name
                + '</a> <span>('
                + typ
                + ')</span></li>'
            )
        else:
            source_rows.append('<li>' + name + ' <span>(' + typ + ')</span></li>')

    return (
        '<ul class="quality-list">'
        + ("".join(source_rows) or "<li>주요 출처 데이터가 없습니다.</li>")
        + '</ul>'
    )


def get_dates(series: Mapping[str, Sequence[Mapping[str, Any]]]):
    return sorted({str(p.get("date")) for pts in series.values() for p in pts if p.get("date")})


def get_values(series):
    vals = []
    for pts in series.values():
        for p in pts:
            try:
                v = float(p.get("value"))
                if math.isfinite(v) and v != 0:
                    vals.append(v)
            except Exception:
                pass
    return vals


def date_label(date_text: str) -> str:
    try:
        return f"{int(date_text[5:7])}/{int(date_text[8:10])}"
    except Exception:
        return date_text


def render_chart(series: Mapping[str, Sequence[Mapping[str, Any]]], colors: Mapping[str, str]) -> str:
    dates = get_dates(series)
    vals = get_values(series)

    if not dates or not vals:
        return '<div class="empty">표시 가능한 그래프 데이터가 없습니다.</div>'

    lo, hi = min(vals), max(vals)
    if lo == hi:
        lo -= 1
        hi += 1

    pad = (hi - lo) * 0.12
    lo = max(0, lo - pad)
    hi = hi + pad

    W, H, L, R, T, B = 440, 220, 40, 430, 14, 188
    date_idx = {d: idx for idx, d in enumerate(dates)}

    def x(idx):
        if len(dates) <= 1:
            return (L + R) / 2
        return L + (R - L) * idx / (len(dates) - 1)

    def y(value):
        return B - ((value - lo) / (hi - lo)) * (B - T)

    # date -> list of value strings for tooltip
    tooltip_by_date = {d: [] for d in dates}
    for name, pts in series.items():
        for p in pts:
            d = str(p.get("date"))
            if d not in tooltip_by_date:
                continue
            try:
                v = float(p.get("value"))
            except Exception:
                continue
            tooltip_by_date[d].append(f"{name}: {v:.2f} $/Bbl")

    parts = [
        '<svg class="chart-svg" viewBox="0 0 440 220" xmlns="http://www.w3.org/2000/svg">'
    ]

    for i in range(5):
        yy = B - (B - T) * i / 4
        label = lo + (hi - lo) * i / 4
        parts.append(f'<line x1="{L}" y1="{yy:.1f}" x2="{R}" y2="{yy:.1f}" stroke="rgba(0,0,0,.09)" />')
        parts.append(f'<text x="{L-6}" y="{yy+3:.1f}" text-anchor="end" font-size="9" fill="#888">{label:.1f}</text>')

    for i, d in enumerate(dates):
        if len(dates) <= 9 or i in {0, len(dates) - 1} or i % max(1, len(dates) // 6) == 0:
            parts.append(
                f'<text x="{x(i):.1f}" y="210" text-anchor="middle" font-size="9" fill="#888">'
                + esc(date_label(d))
                + '</text>'
            )

    # 1) visible line only. No visible points/circles.
    for name, pts in series.items():
        poly = []
        for p in pts:
            d = str(p.get("date"))
            if d not in date_idx:
                continue

            try:
                v = float(p.get("value"))
            except Exception:
                continue

            poly.append(f'{x(date_idx[d]):.1f},{y(v):.1f}')

        if poly:
            color = colors.get(name, "#1A6FD4")
            parts.append(
                '<polyline fill="none" stroke="'
                + color
                + '" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" points="'
                + " ".join(poly)
                + '" />'
            )

    # 2) invisible vertical hover bands.
    # This avoids visible dots while making tooltip easy to trigger.
    if len(dates) == 1:
        band_width = R - L
    else:
        band_width = max(6, (R - L) / (len(dates) - 1))

    for i, d in enumerate(dates):
        tooltip_lines = [d] + tooltip_by_date.get(d, [])
        tooltip = esc(" | ".join(tooltip_lines))
        cx = x(i)
        rect_x = max(L, cx - band_width / 2)
        rect_w = min(band_width, R - rect_x)
        parts.append(
            f'<rect x="{rect_x:.1f}" y="{T}" width="{rect_w:.1f}" height="{B-T}" '
            f'fill="transparent" class="hover-band" data-tooltip="{tooltip}" />'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def render_legend(names, colors):
    return "".join(
        '<span class="legend-item"><span class="legend-dot" style="background:'
        + colors.get(n, "#1A6FD4")
        + '"></span>'
        + esc(n)
        + '</span>'
        for n in names
    )


def css() -> str:
    return """
  :root { --bg:#F4F5F7; --card:#fff; --ink:#1A1A1A; --muted:#666; --line:#E5E7EB; --navy:#0A2444; --blue:#1A6FD4; --red:#C0392B; --green:#0A7B4E; }
  * { box-sizing:border-box; }
  html { -webkit-text-size-adjust:100%; text-size-adjust:100%; }
  body { margin:0; padding:14px; padding-left:max(14px, env(safe-area-inset-left)); padding-right:max(14px, env(safe-area-inset-right)); background:var(--bg); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif; font-size:14px; line-height:1.62; word-break:keep-all; overflow-wrap:anywhere; }
  a { color:inherit; }
  .container { max-width:480px; margin:0 auto; }
  .header { background:var(--navy); color:#fff; border-radius:14px; padding:18px 16px; }
  .header-top { display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }
  .header-title { font-size:20px; font-weight:800; letter-spacing:-.3px; }
  .header-date { font-size:12px; color:rgba(255,255,255,.7); margin-top:2px; }
  .badge { flex-shrink:0; border-radius:999px; background:rgba(255,255,255,.12); padding:4px 10px; font-size:11px; }
  .meta { margin-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:6px 10px; color:rgba(255,255,255,.78); font-size:11px; }
  .section { background:#fff; border:1px solid var(--line); border-radius:14px; margin:10px 0; overflow:hidden; }
  .section-head { display:flex; align-items:center; gap:8px; padding:11px 16px; background:#F8F9FA; border-bottom:1px solid var(--line); }
  .num { background:var(--navy); color:#fff; border-radius:4px; font-size:11px; font-weight:800; min-width:24px; text-align:center; padding:2px 7px; }
  .section-title { font-size:14px; font-weight:800; }
  .body { padding:14px 16px; }
  .summary-item { display:flex; gap:10px; padding:8px 0; border-bottom:1px solid #F0F0F0; font-size:13px; }
  .summary-item:last-child { border-bottom:0; }
  .dot { flex-shrink:0; width:6px; height:6px; border-radius:50%; background:var(--blue); margin-top:8px; }
  .price-label-title { padding:12px 16px 6px; font-size:12px; color:var(--muted); }
  .price-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; padding:0 16px 14px; }
  .price-card { background:#F8F9FA; border-radius:10px; text-align:center; padding:10px 6px; }
  .price-label { font-size:11px; color:#666; }
  .price-value { font-size:18px; font-weight:800; line-height:1.1; margin-top:2px; }
  .price-unit { font-size:10px; color:#999; }
  .price-change { font-size:11px; margin-top:2px; }
  .up { color:var(--red); } .down { color:var(--green); } .flat { color:#888; }
  .note { padding:0 16px 12px; font-size:11px; color:#999; }
  .chart-wrap { padding:12px 10px 14px; }
  .legend { display:flex; flex-wrap:wrap; gap:10px; padding:0 6px 8px; font-size:12px; color:#666; }
  .legend-item { display:inline-flex; align-items:center; gap:5px; }
  .legend-dot { width:12px; height:3px; border-radius:2px; display:inline-block; }
  .chart-svg { width:100%; height:auto; display:block; }
  .hover-band { cursor:crosshair; pointer-events:all; }
  .chart-tooltip { position:fixed; z-index:9999; pointer-events:none; background:rgba(10,36,68,.94); color:#fff; border-radius:8px; padding:7px 9px; font-size:11px; line-height:1.45; box-shadow:0 6px 18px rgba(0,0,0,.18); transform:translate(10px, -30px); white-space:nowrap; max-width:260px; }
  .chart-tooltip.hidden { display:none; }
  .issue-card { background:#F8F9FA; border-left:3px solid var(--blue); border-radius:10px; padding:12px 14px; margin-bottom:8px; }
  .issue-tag { display:inline-block; font-size:10px; font-weight:800; color:#185FA5; background:#E6F1FB; border-radius:3px; padding:2px 6px; margin-bottom:6px; }
  .issue-title { font-size:13px; font-weight:800; margin-bottom:4px; }
  .issue-desc { font-size:12px; color:#444; }
  .issue-footer { margin-top:7px; }
  .issue-grade { font-size:11px; font-weight:800; border-radius:3px; padding:2px 7px; }
  .grade-a { background:#FEECEC; color:#A32D2D; } .grade-b { background:#FFF3E0; color:#854F0B; } .grade-c { background:#F1F1F1; color:#555; }
  .schedule-row { display:flex; gap:8px; padding:9px 0; border-bottom:1px solid #F0F0F0; }
  .schedule-row:last-child { border-bottom:0; }
  .schedule-time { min-width:40px; color:#185FA5; font-size:11px; font-weight:800; }
  .schedule-org { min-width:44px; height:max-content; background:#F0F1F3; border:1px solid #E0E0E0; border-radius:4px; padding:1px 6px; font-size:10px; text-align:center; color:#555; }
  .schedule-main { flex:1; min-width:0; font-size:12px; }
  .schedule-rel { color:#777; font-size:11px; margin-top:2px; }
  .news-summary { font-size:13px; }
  .section-divider { height:1px; background:#F0F0F0; margin:12px 0; }
  .small-title { color:#999; font-size:11px; font-weight:800; margin-bottom:8px; }
  .news-item { display:flex; gap:8px; padding:8px 0; border-bottom:1px solid #F0F0F0; }
  .news-num { color:var(--blue); font-weight:800; font-size:11px; min-width:14px; }
  .news-title { font-size:13px; font-weight:700; text-decoration:underline; text-underline-offset:2px; }
  .news-press { color:#888; font-size:11px; }
  .quality-list { margin:0; padding-left:18px; font-size:12px; color:#555; }
  .quality-list li { margin:5px 0; }
  .empty { background:#F8F9FA; border-radius:10px; padding:12px; color:#777; font-size:12px; }
  .footer { text-align:center; color:#aaa; font-size:11px; padding:14px; }
  @media(max-width:430px) { body { padding:10px; } .header-title { font-size:19px; } .price-grid { gap:6px; padding-left:12px; padding-right:12px; } .price-value { font-size:17px; } .meta { grid-template-columns:1fr; } }
"""


def tooltip_js() -> str:
    return """
(function () {
  var tooltip = document.getElementById('chart-tooltip');
  if (!tooltip) return;

  function formatText(text) {
    return String(text || '').split(' | ').join('\\n');
  }

  function show(evt) {
    var target = evt.target;
    var text = target.getAttribute('data-tooltip');
    if (!text) return;
    tooltip.textContent = formatText(text);
    tooltip.style.whiteSpace = 'pre-line';
    tooltip.classList.remove('hidden');
    move(evt);
  }

  function move(evt) {
    if (tooltip.classList.contains('hidden')) return;
    var clientX = evt.clientX;
    var clientY = evt.clientY;
    if (evt.touches && evt.touches.length) {
      clientX = evt.touches[0].clientX;
      clientY = evt.touches[0].clientY;
    }
    var x = clientX + 12;
    var y = clientY - 34;
    var maxX = window.innerWidth - tooltip.offsetWidth - 8;
    var maxY = window.innerHeight - tooltip.offsetHeight - 8;
    if (x > maxX) x = Math.max(8, clientX - tooltip.offsetWidth - 12);
    if (y < 8) y = clientY + 18;
    if (y > maxY) y = maxY;
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
  }

  function hide() {
    tooltip.classList.add('hidden');
  }

  document.addEventListener('mouseover', function (evt) {
    if (evt.target && evt.target.classList && evt.target.classList.contains('hover-band')) show(evt);
  });

  document.addEventListener('mousemove', function (evt) {
    if (evt.target && evt.target.classList && evt.target.classList.contains('hover-band')) move(evt);
  });

  document.addEventListener('mouseout', function (evt) {
    if (evt.target && evt.target.classList && evt.target.classList.contains('hover-band')) hide();
  });

  document.addEventListener('touchstart', function (evt) {
    if (evt.target && evt.target.classList && evt.target.classList.contains('hover-band')) {
      show(evt);
      window.setTimeout(hide, 1800);
    }
  }, { passive: true });
})();
"""


def section(num: str, title: str, body: str) -> str:
    return (
        '<section class="section"><div class="section-head"><span class="num">'
        + num
        + '</span><span class="section-title">'
        + title
        + '</span></div><div class="body">'
        + body
        + '</div></section>'
    )


def build_html(report: Mapping[str, Any]) -> str:
    meta = report.get("report", {}) or {}
    prices = report.get("prices", {}) or {}
    crude = prices.get("crude", {}) or {}
    products = prices.get("products", {}) or {}
    crude_series = crude.get("chart_series", {}) or {}
    product_series = products.get("chart_series", {}) or {}

    parts = [
        '<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        '<meta name="format-detection" content="telephone=no">',
        '<title>' + esc(meta.get("report_title") or "Daily 유가 동향") + '</title>',
        '<style>' + css() + '</style></head><body><div class="container">',
        '<header class="header"><div class="header-top"><div>',
        '<div class="header-title">' + esc(meta.get("header_title") or "Daily 유가 동향") + '</div>',
        '<div class="header-date">' + esc(meta.get("display_date") or meta.get("report_date") or "") + '</div>',
        '</div><div class="badge">' + esc(meta.get("report_badge") or "정유 · 석유화학 · LNG") + '</div></div>',
        '<div class="meta"><div>기준일: ' + esc(meta.get("report_date", "")) + '</div>',
        '<div>생성: ' + esc(meta.get("generated_at", "")) + '</div></div></header>',
        section("1", "Summary", render_summary(report.get("summary", []))),
        '<section class="section"><div class="section-head"><span class="num">2</span><span class="section-title">유가 동향</span></div>',
        '<div class="price-label-title">최신 유가 정보 ($/Bbl) — ' + esc(crude.get("base_label", "")) + ' 기준</div>',
        '<div class="price-grid">' + render_cards(crude.get("cards", [])) + '</div>',
        '<div class="price-label-title">최신 석유제품 가격 정보 ($/Bbl) — ' + esc(products.get("base_label", "")) + ' 기준</div>',
        '<div class="price-grid">' + render_cards(products.get("cards", [])) + '</div>',
        '<div class="note">' + esc(prices.get("price_data_note", "")) + '</div></section>',
        section(
            "3",
            "원유 가격 추이 그래프 (" + esc(crude.get("chart_period_label", "")) + ")",
            '<div class="chart-wrap"><div class="legend">'
            + render_legend(["Brent", "WTI", "Dubai"], CRUDE_COLORS)
            + '</div>'
            + render_chart(crude_series, CRUDE_COLORS)
            + '</div>',
        ),
        section(
            "4",
            "석유제품 가격 추이 그래프 (" + esc(products.get("chart_period_label", "")) + ")",
            '<div class="chart-wrap"><div class="legend">'
            + render_legend(["Gasoline", "Diesel", "Naphtha"], PRODUCT_COLORS)
            + '</div>'
            + render_chart(product_series, PRODUCT_COLORS)
            + '</div>',
        ),
        section("5", "전일 주요 이슈 (" + esc(meta.get("previous_day_label", "")) + ")", render_issues(report.get("issues", []))),
        '<section class="section"><div class="section-head"><span class="num">6</span><span class="section-title">금일 주요 일정 ('
        + esc(meta.get("today_label", ""))
        + ')</span></div><div class="body">'
        + render_schedules(report.get("schedules", []))
        + '</div><div class="note">※ 관련성·영향도는 일정 원문에 기재된 사실이 아니라, 정유/석화/LNG 관점의 작성자 해석입니다.</div></section>',
        section("7", "조간 신문 트렌드", render_news(report)),
        section("8", "주요 출처", render_quality(report)),
        '<footer class="footer">자동 생성 리포트 · 사실/해석 구분 및 기사 원문 확인 필요</footer>',
        '<div id="chart-tooltip" class="chart-tooltip hidden"></div>',
        '<script>' + tooltip_js() + '</script>',
        '</div></body></html>',
    ]
    return "\n".join(parts)


def parse_args():
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
        atomic_write(out_path, build_html(report))
        print(f"[OK] HTML 리포트 생성 완료: {out_path}")
        return 0
    except Exception as exc:
        print(f"[ERROR] HTML 리포트 생성 실패: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
