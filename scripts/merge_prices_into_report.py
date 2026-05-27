#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
merge_prices_into_report.py v1.4

과거 날짜 리포트도 안정적으로 생성합니다.

정책
- data/prices/history.json에는 장기 데이터를 보유.
- 그래프는 기준일 전일 기준 과거 2개월만 표시.
- data/prices/YYYY-MM-DD.json이 없어도 history.json에서 가격 카드와 그래프를 생성.
- 가격 0은 제외.
"""

from __future__ import annotations

import argparse
import calendar
import json
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


class MergePriceError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="가격 데이터를 리포트 JSON에 반영")
    parser.add_argument("--date", required=True)
    parser.add_argument("--report-dir", default="data/reports")
    parser.add_argument("--price-dir", default="data/prices")
    parser.add_argument("--history", default="data/prices/history.json")
    parser.add_argument("--out", default="")
    parser.add_argument("--chart-months", type=int, default=2)
    return parser.parse_args()


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise MergePriceError(f"파일을 찾을 수 없습니다: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MergePriceError(f"JSON 파일을 읽을 수 없습니다: {path} / {exc}") from exc


def read_json_optional(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False,
                                     prefix=f".{path.name}.", suffix=".tmp") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise MergePriceError(f"날짜 형식이 올바르지 않습니다: {value}") from exc


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def chart_window(report_date_text: str, months: int = 2) -> Tuple[str, str]:
    report_date = parse_date(report_date_text)
    end_date = report_date - timedelta(days=1)
    start_date = add_months(end_date, -months)
    return start_date.isoformat(), end_date.isoformat()


def short_date(date_text: str) -> str:
    try:
        return f"{int(date_text[5:7])}/{int(date_text[8:10])}"
    except Exception:
        return date_text or ""


def valid_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except Exception:
        return None
    if number == 0:
        return None
    return round(number, 2)


def point(date_text: str, value: Any) -> Optional[Dict[str, Any]]:
    number = valid_number(value)
    if number is None:
        return None
    return {"date": date_text, "label": short_date(date_text), "value": number}


def in_window(date_text: str, start_date: str, end_date: str) -> bool:
    return start_date <= date_text <= end_date


def build_series_from_history(history: Optional[Mapping[str, Any]], section: str, mapping: Mapping[str, str],
                              start_date: str, end_date: str) -> Dict[str, List[Dict[str, Any]]]:
    series = {label: [] for label in mapping.keys()}
    if not history:
        return series

    rows = history.get(section, {}) or {}
    for row_date in sorted(rows.keys()):
        if not in_window(row_date, start_date, end_date):
            continue
        values = rows.get(row_date, {}) or {}
        for label, source_key in mapping.items():
            p = point(row_date, values.get(source_key))
            if p:
                series[label].append(p)
    return series


def clean_daily_series(series: Mapping[str, List[Mapping[str, Any]]], start_date: str, end_date: str) -> Dict[str, List[Dict[str, Any]]]:
    cleaned: Dict[str, List[Dict[str, Any]]] = {}
    for label, points in series.items():
        cleaned[label] = []
        for item in points:
            row_date = str(item.get("date", ""))
            if not in_window(row_date, start_date, end_date):
                continue
            p = point(row_date, item.get("value"))
            if p:
                cleaned[label].append(p)
    return cleaned


def history_rows(history: Optional[Mapping[str, Any]], section: str) -> Mapping[str, Any]:
    if not history:
        return {}
    return history.get(section, {}) or {}


def latest_history_values(history: Optional[Mapping[str, Any]], section: str, keys: Mapping[str, str], end_date: str) -> Tuple[str, Dict[str, float], Dict[str, float]]:
    """
    end_date 이하의 최신 날짜 가격과 직전 날짜 대비 변동폭을 history에서 구함.
    return: latest_date, latest_values_by_label, changes_by_label
    """
    rows = history_rows(history, section)
    available_dates = sorted([d for d in rows.keys() if d <= end_date])

    if not available_dates:
        return "", {}, {}

    latest_date = available_dates[-1]
    prev_date = available_dates[-2] if len(available_dates) >= 2 else ""

    latest_values: Dict[str, float] = {}
    changes: Dict[str, float] = {}

    latest_row = rows.get(latest_date, {}) or {}
    prev_row = rows.get(prev_date, {}) or {}

    for label, source_key in keys.items():
        latest = valid_number(latest_row.get(source_key))
        if latest is None:
            continue
        latest_values[label] = latest

        prev = valid_number(prev_row.get(source_key))
        if prev is None:
            changes[label] = 0.0
        else:
            changes[label] = round(latest - prev, 2)

    return latest_date, latest_values, changes


def direction(change: float) -> str:
    if change > 0:
        return "up"
    if change < 0:
        return "down"
    return "flat"


def cards_from_history(history: Optional[Mapping[str, Any]], section: str, keys: Mapping[str, str], end_date: str, label_map: Optional[Mapping[str, str]] = None) -> Tuple[str, List[Dict[str, Any]]]:
    latest_date, values, changes = latest_history_values(history, section, keys, end_date)
    cards: List[Dict[str, Any]] = []

    for label in keys.keys():
        if label not in values:
            continue
        display_label = label_map.get(label, label) if label_map else label
        change = changes.get(label, 0.0)
        cards.append({
            "label": display_label,
            "value": values[label],
            "change": change,
            "direction": direction(change),
            "unit": "$/Bbl",
        })

    return latest_date, cards


def normalize_crude_cards(price_data: Optional[Mapping[str, Any]], history: Optional[Mapping[str, Any]], end_date: str) -> Tuple[str, List[Dict[str, Any]]]:
    if price_data and price_data.get("crude", {}).get("cards"):
        crude = price_data["crude"]
        order = ["Brent", "WTI", "Dubai"]
        by_label = {str(card.get("label")): dict(card) for card in crude.get("cards", [])}
        cards = []
        for label in order:
            card = by_label.get(label)
            if not card:
                continue
            cards.append({
                "label": label,
                "value": card.get("value"),
                "change": card.get("change", 0),
                "direction": card.get("direction", "flat"),
                "unit": card.get("unit", "$/Bbl"),
            })
        return crude.get("latest_date", ""), cards

    return cards_from_history(history, "crude", {"Brent": "Brent", "WTI": "WTI", "Dubai": "Dubai"}, end_date)


def normalize_product_cards(price_data: Optional[Mapping[str, Any]], history: Optional[Mapping[str, Any]], end_date: str) -> Tuple[str, List[Dict[str, Any]]]:
    if price_data and price_data.get("products", {}).get("cards"):
        products = price_data["products"]
        order = ["휘발유", "경유", "나프타"]
        by_label = {str(card.get("label")): dict(card) for card in products.get("cards", [])}
        cards = []
        for label in order:
            card = by_label.get(label)
            if not card:
                continue
            cards.append({
                "label": label,
                "value": card.get("value"),
                "change": card.get("change", 0),
                "direction": card.get("direction", "flat"),
                "unit": card.get("unit", "$/Bbl"),
            })
        return products.get("latest_date", ""), cards

    return cards_from_history(
        history,
        "products",
        {"Gasoline": "Gasoline_92RON", "Diesel": "Diesel_0.001", "Naphtha": "Naphtha"},
        end_date,
        {"Gasoline": "휘발유", "Diesel": "경유", "Naphtha": "나프타"},
    )


def choose_chart_series(price_data: Optional[Mapping[str, Any]], history: Optional[Mapping[str, Any]], start_date: str, end_date: str):
    crude_history_series = build_series_from_history(history, "crude", {"Brent": "Brent", "WTI": "WTI", "Dubai": "Dubai"}, start_date, end_date)
    product_history_series = build_series_from_history(history, "products", {"Gasoline": "Gasoline_92RON", "Diesel": "Diesel_0.001", "Naphtha": "Naphtha"}, start_date, end_date)

    if sum(len(points) for points in crude_history_series.values()) > 0:
        crude_series = crude_history_series
        crude_source = "history.json window"
    elif price_data:
        crude_series = clean_daily_series(price_data.get("crude", {}).get("chart_series", {}) or {}, start_date, end_date)
        crude_source = "daily price json window"
    else:
        crude_series = crude_history_series
        crude_source = "none"

    if sum(len(points) for points in product_history_series.values()) > 0:
        product_series = product_history_series
        product_source = "history.json window"
    elif price_data:
        product_series = clean_daily_series(price_data.get("products", {}).get("chart_series", {}) or {}, start_date, end_date)
        product_source = "daily price json window"
    else:
        product_series = product_history_series
        product_source = "none"

    return crude_series, product_series, crude_source, product_source


def chart_period_label(series: Mapping[str, List[Mapping[str, Any]]]) -> str:
    dates = []
    for points in series.values():
        for item in points:
            if item.get("date"):
                dates.append(str(item["date"]))
    if not dates:
        return ""
    dates = sorted(set(dates))
    return f"{short_date(dates[0])}~{short_date(dates[-1])}"


def source_urls(price_data: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    if not price_data:
        return {}
    return price_data.get("source_urls", {}) or {}


def update_price_section(report: Dict[str, Any], price_data: Optional[Mapping[str, Any]], history: Optional[Mapping[str, Any]], start_date: str, end_date: str) -> Dict[str, str]:
    crude_series, product_series, crude_source, product_source = choose_chart_series(price_data, history, start_date, end_date)
    crude_latest_date, crude_cards = normalize_crude_cards(price_data, history, end_date)
    product_latest_date, product_cards = normalize_product_cards(price_data, history, end_date)

    if not crude_cards:
        raise MergePriceError("원유 가격 카드 데이터를 만들 수 없습니다. history.json 또는 가격 JSON을 확인하세요.")
    if not product_cards:
        raise MergePriceError("석유제품 가격 카드 데이터를 만들 수 없습니다. history.json 또는 가격 JSON을 확인하세요.")

    report["prices"] = {
        "unit": "$/Bbl",
        "price_data_note": "※ 오피넷 기준. 과거 2개월만 표시, 값이 0인 가격은 제외.",
        "crude": {
            "base_label": short_date(crude_latest_date),
            "cards": crude_cards,
            "chart_period_label": chart_period_label(crude_series),
            "chart_window": {"start": start_date, "end": end_date, "rule": "report_date - 1 day, then minus 2 calendar months"},
            "chart_series": crude_series,
        },
        "products": {
            "base_label": short_date(product_latest_date),
            "cards": product_cards,
            "chart_period_label": chart_period_label(product_series),
            "chart_window": {"start": start_date, "end": end_date, "rule": "report_date - 1 day, then minus 2 calendar months"},
            "chart_series": product_series,
        },
    }
    return {"crude_chart_source": crude_source, "products_chart_source": product_source}


def update_summary(report: Dict[str, Any], start_date: str, end_date: str) -> None:
    # 가격 그래프 설명은 prices.price_data_note에만 둔다.
    # Summary에는 정책·일정·조간 보도만 남겨 보고서 문맥이 흐려지지 않도록 한다.
    return None


def update_sources_and_quality(report: Dict[str, Any], price_data: Optional[Mapping[str, Any]], history: Optional[Mapping[str, Any]], start_date: str, end_date: str) -> None:
    quality = report.setdefault("quality_control", {})
    notes = quality.setdefault("quality_notes", [])
    sources = quality.setdefault("sources", [])

    for note in [
        f"가격 추이 그래프는 기준일 전일 기준 과거 2개월({short_date(start_date)}~{short_date(end_date)})만 표시하며, 전체 장기 데이터는 history.json에 보유합니다.",
        "값이 0인 가격은 그래프 이력에서 제외했습니다.",
        "과거 날짜에 일별 가격 JSON이 없더라도 history.json에서 가격 카드와 그래프를 생성합니다.",
    ]:
        if note not in notes:
            notes.append(note)

    urls = source_urls(price_data)
    sources = [s for s in sources if not (s.get("type") == "price" and "오피넷" in s.get("name", ""))]
    sources.extend([
        {"name": "오피넷 국제유가 > 원유", "type": "price", "url": urls.get("crude", "")},
        {"name": "오피넷 국제유가 > 석유제품", "type": "price", "url": urls.get("products", "")},
    ])
    if history and history.get("source_files"):
        sources.append({"name": "장기 가격 이력 history.json", "type": "price-history", "url": ""})
    quality["sources"] = sources


def update_automation(report: Dict[str, Any], price_data: Optional[Mapping[str, Any]], history: Optional[Mapping[str, Any]], chart_sources: Mapping[str, str], start_date: str, end_date: str) -> None:
    report.setdefault("automation", {})
    report["automation"]["opinet_prices"] = {
        "price_json_used": bool(price_data),
        "source_date": price_data.get("date", "") if price_data else "",
        "history_schema_version": history.get("schema_version", "") if history else "",
        "history_period": history.get("period", {}) if history else {},
        "chart_window": {"start": start_date, "end": end_date, "rule": "report_date - 1 day, then minus 2 calendar months"},
        "crude_chart_source": chart_sources.get("crude_chart_source", ""),
        "products_chart_source": chart_sources.get("products_chart_source", ""),
        "merged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "merge_script": "merge_prices_into_report.py v1.4",
        "needs_review": True,
    }


def merge_prices(report: Dict[str, Any], price_data: Optional[Mapping[str, Any]], history: Optional[Mapping[str, Any]], report_date: str, months: int) -> Dict[str, Any]:
    start_date, end_date = chart_window(report_date, months=months)
    chart_sources = update_price_section(report, price_data, history, start_date, end_date)
    update_summary(report, start_date, end_date)
    update_sources_and_quality(report, price_data, history, start_date, end_date)
    update_automation(report, price_data, history, chart_sources, start_date, end_date)
    return report


def main() -> int:
    args = parse_args()
    report_path = Path(args.report_dir) / f"{args.date}.report.json"
    price_path = Path(args.price_dir) / f"{args.date}.json"
    history_path = Path(args.history)
    out_path = Path(args.out) if args.out else report_path

    try:
        report = read_json(report_path)
        price_data = read_json_optional(price_path)
        history = read_json_optional(history_path)

        if not price_data and not history:
            raise MergePriceError("가격 JSON과 history.json이 모두 없습니다.")

        merged = merge_prices(report, price_data, history, args.date, args.chart_months)
        atomic_write_json(out_path, merged)

        window = merged["prices"]["crude"]["chart_window"]
        print(f"[OK] 가격 데이터 반영 완료: {out_path}")
        print(f"[OK] 그래프 표시 목표 기간: {short_date(window['start'])}~{short_date(window['end'])}")
        print(f"[OK] 원유 그래프 실제 데이터 기간: {merged.get('prices', {}).get('crude', {}).get('chart_period_label', '')}")
        print(f"[OK] 제품 그래프 실제 데이터 기간: {merged.get('prices', {}).get('products', {}).get('chart_period_label', '')}")
        return 0

    except Exception as exc:
        print(f"[ERROR] 가격 데이터 반영 실패: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
