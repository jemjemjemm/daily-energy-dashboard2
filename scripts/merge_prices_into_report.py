#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
merge_prices_into_report.py v1.3

오피넷 국제유가 JSON과 장기 history.json을 리포트용 JSON 초안에 반영합니다.

정책
- data/prices/history.json에는 2026년 이후 장기 데이터를 계속 보유합니다.
- 리포트 화면 그래프에는 기준일 전일 기준 과거 2개월만 넣습니다.
  예: --date 2026-05-21 → 2026-03-20 ~ 2026-05-20
  예: --date 2026-05-20 → 2026-03-19 ~ 2026-05-19
- 가격 0은 제외합니다.
- 가격 카드: 당일 수집 JSON의 최신 가격 기준
- 가격 그래프: history.json에서 window만 잘라서 사용
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
    parser = argparse.ArgumentParser(description="오피넷 가격 JSON을 리포트 JSON에 반영")
    parser.add_argument("--date", required=True, help="리포트 기준일 YYYY-MM-DD")
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


def validate_price_data(price_data: Mapping[str, Any]) -> None:
    if not price_data.get("success", True):
        raise MergePriceError("오피넷 가격 수집 실패 JSON입니다.")
    if not price_data.get("crude", {}).get("cards"):
        raise MergePriceError("원유 가격 카드 데이터가 없습니다.")
    if not price_data.get("products", {}).get("cards"):
        raise MergePriceError("석유제품 가격 카드 데이터가 없습니다.")


def valid_point(date_text: str, value: Any) -> Optional[Dict[str, Any]]:
    try:
        number = float(value)
    except Exception:
        return None
    if number == 0:
        return None
    return {"date": date_text, "label": short_date(date_text), "value": round(number, 2)}


def in_window(date_text: str, start_date: str, end_date: str) -> bool:
    return start_date <= date_text <= end_date


def build_series_from_history(
    history: Optional[Mapping[str, Any]],
    section: str,
    mapping: Mapping[str, str],
    start_date: str,
    end_date: str,
) -> Dict[str, List[Dict[str, Any]]]:
    series: Dict[str, List[Dict[str, Any]]] = {label: [] for label in mapping.keys()}

    if not history:
        return series

    rows = history.get(section, {}) or {}

    for row_date in sorted(rows.keys()):
        if not in_window(row_date, start_date, end_date):
            continue

        values = rows.get(row_date, {}) or {}
        for label, source_key in mapping.items():
            point = valid_point(row_date, values.get(source_key))
            if point:
                series[label].append(point)

    return series


def clean_daily_series(
    series: Mapping[str, List[Mapping[str, Any]]],
    start_date: str,
    end_date: str,
) -> Dict[str, List[Dict[str, Any]]]:
    cleaned: Dict[str, List[Dict[str, Any]]] = {}

    for label, points in series.items():
        cleaned[label] = []
        for item in points:
            row_date = str(item.get("date", ""))
            if not in_window(row_date, start_date, end_date):
                continue
            point = valid_point(row_date, item.get("value"))
            if point:
                cleaned[label].append(point)

    return cleaned


def choose_chart_series(
    price_data: Mapping[str, Any],
    history: Optional[Mapping[str, Any]],
    start_date: str,
    end_date: str,
):
    crude_history_series = build_series_from_history(
        history=history,
        section="crude",
        mapping={"Brent": "Brent", "WTI": "WTI", "Dubai": "Dubai"},
        start_date=start_date,
        end_date=end_date,
    )

    product_history_series = build_series_from_history(
        history=history,
        section="products",
        mapping={"Gasoline": "Gasoline_92RON", "Diesel": "Diesel_0.001", "Naphtha": "Naphtha"},
        start_date=start_date,
        end_date=end_date,
    )

    crude_points = sum(len(points) for points in crude_history_series.values())
    product_points = sum(len(points) for points in product_history_series.values())

    if crude_points > 0:
        crude_series = crude_history_series
        crude_source = "history.json window"
    else:
        crude_series = clean_daily_series(price_data.get("crude", {}).get("chart_series", {}) or {}, start_date, end_date)
        crude_source = "daily price json window"

    if product_points > 0:
        product_series = product_history_series
        product_source = "history.json window"
    else:
        product_series = clean_daily_series(price_data.get("products", {}).get("chart_series", {}) or {}, start_date, end_date)
        product_source = "daily price json window"

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


def normalize_crude_cards(cards: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    order = ["Brent", "WTI", "Dubai"]
    by_label = {str(card.get("label")): dict(card) for card in cards}
    result = []

    for label in order:
        card = by_label.get(label)
        if not card:
            continue
        result.append({
            "label": label,
            "value": card.get("value"),
            "change": card.get("change", 0),
            "direction": card.get("direction", "flat"),
            "unit": card.get("unit", "$/Bbl"),
        })

    return result


def normalize_product_cards(cards: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    order = ["휘발유", "경유", "나프타"]
    by_label = {str(card.get("label")): dict(card) for card in cards}
    result = []

    for label in order:
        card = by_label.get(label)
        if not card:
            continue
        result.append({
            "label": label,
            "value": card.get("value"),
            "change": card.get("change", 0),
            "direction": card.get("direction", "flat"),
            "unit": card.get("unit", "$/Bbl"),
        })

    return result


def update_price_section(
    report: Dict[str, Any],
    price_data: Mapping[str, Any],
    history: Optional[Mapping[str, Any]],
    start_date: str,
    end_date: str,
) -> Dict[str, str]:
    crude = price_data["crude"]
    products = price_data["products"]

    crude_series, product_series, crude_source, product_source = choose_chart_series(
        price_data=price_data,
        history=history,
        start_date=start_date,
        end_date=end_date,
    )

    report["prices"] = {
        "unit": "$/Bbl",
        "price_data_note": (
            "※ 오피넷 국제유가 메뉴에서 수집한 $/Bbl 기준 가격입니다. "
            f"그래프는 기준일 전일 기준 과거 2개월({short_date(start_date)}~{short_date(end_date)})만 표시하며, "
            "값이 0인 가격은 제외했습니다."
        ),
        "crude": {
            "base_label": short_date(crude.get("latest_date", "")),
            "cards": normalize_crude_cards(crude.get("cards", [])),
            "chart_period_label": chart_period_label(crude_series),
            "chart_window": {
                "start": start_date,
                "end": end_date,
                "rule": "report_date - 1 day, then minus 2 calendar months",
            },
            "chart_series": crude_series,
        },
        "products": {
            "base_label": short_date(products.get("latest_date", "")),
            "cards": normalize_product_cards(products.get("cards", [])),
            "chart_period_label": chart_period_label(product_series),
            "chart_window": {
                "start": start_date,
                "end": end_date,
                "rule": "report_date - 1 day, then minus 2 calendar months",
            },
            "chart_series": product_series,
        },
    }

    return {
        "crude_chart_source": crude_source,
        "products_chart_source": product_source,
    }


def update_summary(report: Dict[str, Any], price_data: Mapping[str, Any], start_date: str, end_date: str) -> None:
    summary = report.setdefault("summary", [])
    while len(summary) < 3:
        summary.append({"type": "auto", "text": ""})

    crude_date = price_data.get("crude", {}).get("latest_date", "")
    product_date = price_data.get("products", {}).get("latest_date", "")
    sentence = (
        f"오피넷 국제유가 기준 최신 가격은 원유 {short_date(crude_date)}, "
        f"석유제품 {short_date(product_date)} 기준으로 반영함. "
        f"그래프는 기준일 전일 기준 과거 2개월({short_date(start_date)}~{short_date(end_date)})만 표시하며, "
        "값이 0인 가격은 제외."
    )

    existing = summary[0].get("text", "")
    if "오피넷 국제유가 기준 최신 가격" not in existing:
        summary[0]["text"] = (existing.rstrip() + " " + sentence).strip()


def update_sources_and_quality(
    report: Dict[str, Any],
    price_data: Mapping[str, Any],
    history: Optional[Mapping[str, Any]],
    start_date: str,
    end_date: str,
) -> None:
    quality = report.setdefault("quality_control", {})
    notes = quality.setdefault("quality_notes", [])
    sources = quality.setdefault("sources", [])

    new_notes = [
        "오피넷 국제유가 데이터는 원유·석유제품 표의 $/Bbl 행을 기준으로 자동 반영했습니다.",
        f"가격 추이 그래프는 기준일 전일 기준 과거 2개월({short_date(start_date)}~{short_date(end_date)})만 표시하며, 전체 장기 데이터는 history.json에 보유합니다.",
        "값이 0인 가격은 그래프 이력에서 제외했습니다.",
        "가격 데이터는 원유와 석유제품 각각의 최신 가격 일자가 다를 수 있으므로 기준일 라벨을 별도 표시합니다.",
    ]

    for note in new_notes:
        if note not in notes:
            notes.append(note)

    if history and history.get("source_files"):
        source_note = "장기 가격 이력 출처 파일: " + json.dumps(history.get("source_files"), ensure_ascii=False)
        if source_note not in notes:
            notes.append(source_note)

    urls = price_data.get("source_urls", {})
    sources = [
        source for source in sources
        if not (source.get("type") == "price" and "오피넷" in source.get("name", ""))
    ]
    sources.extend([
        {"name": "오피넷 국제유가 > 원유", "type": "price", "url": urls.get("crude", "")},
        {"name": "오피넷 국제유가 > 석유제품", "type": "price", "url": urls.get("products", "")},
    ])
    quality["sources"] = sources


def update_automation(
    report: Dict[str, Any],
    price_data: Mapping[str, Any],
    history: Optional[Mapping[str, Any]],
    chart_sources: Mapping[str, str],
    start_date: str,
    end_date: str,
) -> None:
    report.setdefault("automation", {})
    report["automation"]["opinet_prices"] = {
        "source_schema_version": price_data.get("schema_version", ""),
        "source_date": price_data.get("date", ""),
        "collected_at": price_data.get("collected_at", ""),
        "crude_latest_date": price_data.get("crude", {}).get("latest_date", ""),
        "products_latest_date": price_data.get("products", {}).get("latest_date", ""),
        "history_schema_version": history.get("schema_version", "") if history else "",
        "history_period": history.get("period", {}) if history else {},
        "chart_window": {
            "start": start_date,
            "end": end_date,
            "rule": "report_date - 1 day, then minus 2 calendar months",
        },
        "crude_chart_source": chart_sources.get("crude_chart_source", ""),
        "products_chart_source": chart_sources.get("products_chart_source", ""),
        "merged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "merge_script": "merge_prices_into_report.py v1.3",
        "needs_review": True,
    }


def merge_prices(
    report: Dict[str, Any],
    price_data: Mapping[str, Any],
    history: Optional[Mapping[str, Any]],
    report_date: str,
    months: int,
) -> Dict[str, Any]:
    validate_price_data(price_data)
    start_date, end_date = chart_window(report_date, months=months)

    chart_sources = update_price_section(
        report=report,
        price_data=price_data,
        history=history,
        start_date=start_date,
        end_date=end_date,
    )
    update_summary(report, price_data, start_date, end_date)
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
        price_data = read_json(price_path)
        history = read_json_optional(history_path)

        merged = merge_prices(
            report=report,
            price_data=price_data,
            history=history,
            report_date=args.date,
            months=args.chart_months,
        )
        atomic_write_json(out_path, merged)

        window = merged["prices"]["crude"]["chart_window"]
        print(f"[OK] 오피넷 가격 데이터 반영 완료: {out_path}")
        print(f"[OK] 그래프 표시 목표 기간: {short_date(window['start'])}~{short_date(window['end'])}")
        print(f"[OK] 원유 그래프 실제 데이터 기간: {merged.get('prices', {}).get('crude', {}).get('chart_period_label', '')}")
        print(f"[OK] 제품 그래프 실제 데이터 기간: {merged.get('prices', {}).get('products', {}).get('chart_period_label', '')}")
        return 0

    except Exception as exc:
        print(f"[ERROR] 오피넷 가격 데이터 반영 실패: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
