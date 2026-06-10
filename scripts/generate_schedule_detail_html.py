#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_schedule_detail_html.py

Render data/schedules/YYYY-MM-DD.json to docs/schedules/YYYY-MM-DD.html.
The output is a standalone mobile schedule detail page intended to open in an
iframe modal from a Daily Issue Report page.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import tempfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any


PARTY_NAMES = ["더불어민주당", "국민의힘", "조국혁신당", "개혁신당"]
FIELD_CATEGORY_ORDER = ["외교안보", "경제", "산업", "소비자경제", "테크", "사회", "정책사회", "국제"]
DROP_PATTERNS = [
    "오늘의 주요일정",
    "세이프타임즈",
    "저작권자",
    "무단전재",
    "SNS 기사보내기",
    "댓글",
    "기사제보",
]


STYLE = r"""
*{box-sizing:border-box}html{background:#E9EEF5}body{margin:0;background:#E9EEF5;color:#172033;font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Segoe UI",sans-serif;font-size:14px;line-height:1.55}.page{width:100%;max-width:430px;min-height:100vh;margin:0 auto;background:#F4F6F9;padding:0 12px 22px}.hero{margin:0 -12px;padding:20px 18px 18px;background:#0A2444;color:#fff;border-radius:0 0 18px 18px}.eyebrow{font-size:12px;color:rgba(255,255,255,.72);margin-bottom:4px}.hero h1{margin:0;font-size:21px;line-height:1.25}.hero-date{margin-top:6px;font-size:13px;color:rgba(255,255,255,.8)}.back-row{padding:12px 0}.back-btn{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:0 15px;border:0;border-radius:999px;background:#fff;color:#0A2444;font-size:13px;font-weight:700;box-shadow:0 3px 10px rgba(10,36,68,.12);cursor:pointer;-webkit-tap-highlight-color:transparent}.card{background:#fff;border:1px solid #E0E5EE;border-radius:12px;margin:10px 0;overflow:hidden;box-shadow:0 2px 8px rgba(10,36,68,.04)}.card-head{display:flex;align-items:center;gap:9px;padding:13px 14px;border-bottom:1px solid #EEF1F5;background:#FBFCFE}.num-badge{display:inline-flex;align-items:center;justify-content:center;min-width:27px;height:24px;padding:0 8px;border-radius:7px;background:#1A6FD4;color:#fff;font-size:12px;font-weight:800}.card-title{font-size:15px;font-weight:800;color:#0A2444}.card-body{padding:8px 12px 12px}.group-title{display:flex;align-items:center;gap:7px;margin:9px 0 5px;color:#172033;font-size:13px;font-weight:800}.person-badge,.dept-badge,.field-badge,.party-badge{display:inline-flex;align-items:center;min-height:24px;border-radius:999px;padding:2px 9px;font-size:11px;font-weight:800;white-space:nowrap}.person-badge{background:#E8F1FF;color:#185FA5}.dept-badge{background:#EEF2F7;color:#44546A}.field-badge{background:#EDF7F1;color:#177245}.party-badge.democratic{background:#E6F1FF;color:#145EA8}.party-badge.people-power{background:#FFE8EA;color:#B3263A}.party-badge.rebuilding{background:#EAF3FF;color:#2069B2}.party-badge.reform{background:#FFF1D9;color:#A35B00}.party-badge.other{background:#EEF0F4;color:#4B5563}.event{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid #F0F2F5}.event:last-child{border-bottom:0}.time-col{flex:0 0 47px;color:#185FA5;font-size:12px;font-weight:800;line-height:1.4;padding-top:2px;word-break:keep-all}.event-body{min-width:0;flex:1}.event-title{color:#1C2738;font-size:13px;font-weight:650;word-break:keep-all;overflow-wrap:anywhere}.loc{margin-top:3px;color:#667085;font-size:12px;word-break:keep-all;overflow-wrap:anywhere}.icon{display:inline-block;width:18px}.empty{padding:12px;color:#788294;font-size:13px;background:#F8FAFC;border-radius:8px}.dept-block,.field-block,.party-block,.core-block{padding:4px 0 8px}.footer-space{height:4px}@media(max-width:430px){.page{max-width:none}.hero h1{font-size:20px}.card{border-radius:10px}.event-title{font-size:12.8px}.time-col{flex-basis:45px}}
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="세이프타임즈 전체 일정 상세 HTML 생성", allow_abbrev=False)
    parser.add_argument("--date", required=True, help="기준일 YYYY-MM-DD")
    parser.add_argument("--schedule-dir", default="data/schedules", help="일정 JSON 폴더")
    parser.add_argument("--out-dir", default="docs/schedules", help="상세 HTML 출력 폴더")
    return parser.parse_args()


def esc(value: Any) -> str:
    return html_lib.escape("" if value is None else str(value), quote=True)


def normalize_line(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\ufeff", "").replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_bullet(value: Any) -> str:
    return re.sub(r"^[▲△▶▷□◇◆○●\s]+", "", normalize_line(value)).strip()


def section_name(line: str) -> str:
    match = re.match(r"^\[([^\]]+)\](?:\(([^)]*)\))?$", normalize_line(line))
    return match.group(1).strip() if match else ""


def top_section_name(line: str) -> str:
    match = re.match(r"^■\s*(.+)$", normalize_line(line))
    return match.group(1).strip() if match else ""


def clean_source_lines(body: str) -> list[str]:
    rows: list[str] = []
    for raw in (body or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = normalize_line(raw)
        if not line:
            continue
        if any(pattern in line for pattern in DROP_PATTERNS):
            continue
        rows.append(line)
    return rows


def split_regions(body: str) -> tuple[list[str], list[str]]:
    field_lines: list[str] = []
    minister_lines: list[str] = []
    current = ""
    for line in clean_source_lines(body):
        top = top_section_name(line)
        if top:
            if "분야별" in top:
                current = "field"
            elif "총리 및 장차관" in top:
                current = "minister"
            else:
                current = "other"
            continue
        if current == "field":
            field_lines.append(line)
        elif current == "minister":
            minister_lines.append(line)
    return field_lines, minister_lines


def extract_time_note(text: str) -> tuple[str, str]:
    text = normalize_line(text)
    match = re.search(r"\b(\d{1,2})[:：](\d{2})\b", text)
    if not match:
        return "", text
    time_text = f"{int(match.group(1)):02d}:{match.group(2)}"
    note = normalize_line((text[: match.start()] + " " + text[match.end() :]).strip(" ,·-"))
    return time_text, note


def parse_event_text(text: str) -> dict[str, str]:
    title = clean_bullet(text)
    parsed_time = ""
    locations: list[str] = []

    while True:
        match = re.search(r"\(([^()]*)\)\s*$", title)
        if not match:
            break
        inner = normalize_line(match.group(1))
        inner_time, inner_note = extract_time_note(inner)
        if inner_time and not parsed_time:
            parsed_time = inner_time
        if inner_note:
            locations.insert(0, inner_note)
        title = normalize_line(title[: match.start()])

    leading = re.match(r"^(?:(?P<note>[가-힣A-Za-z]+시간)\s*)?(?P<h>\d{1,2})[:：](?P<m>\d{2})\s*", title)
    if leading:
        if not parsed_time:
            parsed_time = f"{int(leading.group('h')):02d}:{leading.group('m')}"
        if leading.group("note"):
            locations.insert(0, leading.group("note"))
        title = normalize_line(title[leading.end() :])

    if not parsed_time:
        inline_time, inline_note = extract_time_note(title)
        if inline_time and ("시간" in inline_note or not title.startswith(inline_time)):
            parsed_time = inline_time
            if inline_note.endswith("시간"):
                locations.insert(0, inline_note)
                title = normalize_line(re.sub(r"\b\d{1,2}[:：]\d{2}\b", "", title, count=1))

    return {
        "time": parsed_time or "-",
        "title": title or clean_bullet(text),
        "location": " · ".join(dict.fromkeys([loc for loc in locations if loc])),
    }


def split_actor_event(text: str, fallback_actor: str = "") -> tuple[str, str]:
    text = clean_bullet(text)
    if "," in text:
        actor, event = [part.strip() for part in text.split(",", 1)]
        if actor and event:
            return actor, event
    return fallback_actor, text


def ensure_ordered_group(container: OrderedDict[str, list[dict[str, str]]], key: str) -> list[dict[str, str]]:
    if key not in container:
        container[key] = []
    return container[key]


def parse_field_lines(field_lines: list[str]) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]], OrderedDict[str, list[dict[str, str]]]]:
    core = {"대통령": [], "국무총리": []}
    parties = {name: [] for name in PARTY_NAMES}
    parties["기타 정당"] = []
    fields: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
    current_category = ""
    current_subject = ""
    current_bucket = ""

    for line in field_lines:
        sec = section_name(line)
        if sec:
            current_category = sec
            current_subject = ""
            current_bucket = ""
            if sec != "정치":
                ensure_ordered_group(fields, sec)
            continue

        if line.startswith("▲"):
            subject = clean_bullet(line)
            if current_category == "정치":
                current_subject = subject
                if "대통령" in subject:
                    current_bucket = "대통령"
                elif "국무총리" in subject or subject.endswith("총리"):
                    current_bucket = "국무총리"
                elif subject in PARTY_NAMES:
                    current_bucket = subject
                elif "당" in subject:
                    current_bucket = "기타 정당"
                else:
                    current_bucket = ""
                continue

            actor, event_text = split_actor_event(subject)
            item = parse_event_text(event_text)
            item["actor"] = actor or current_category
            ensure_ordered_group(fields, current_category).append(item)
            continue

        if current_category == "정치" and current_bucket:
            item = parse_event_text(line)
            item["actor"] = current_subject
            if current_bucket in core:
                core[current_bucket].append(item)
            else:
                parties[current_bucket].append(item)

    return core, parties, fields


def parse_minister_lines(minister_lines: list[str]) -> OrderedDict[str, OrderedDict[str, list[dict[str, str]]]]:
    groups: OrderedDict[str, OrderedDict[str, list[dict[str, str]]]] = OrderedDict()
    current_dept = ""
    current_person = ""

    for line in minister_lines:
        sec = section_name(line)
        if sec:
            current_dept = sec
            current_person = ""
            if current_dept not in groups:
                groups[current_dept] = OrderedDict()
            continue

        if line.startswith("▲"):
            current_person = clean_bullet(line)
            if current_dept:
                groups.setdefault(current_dept, OrderedDict()).setdefault(current_person, [])
            continue

        if current_dept and current_person:
            groups[current_dept][current_person].append(parse_event_text(line))

    return groups


def parse_from_items(items: Any) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]], OrderedDict[str, OrderedDict[str, list[dict[str, str]]]], OrderedDict[str, list[dict[str, str]]]]:
    core = {"대통령": [], "국무총리": []}
    parties = {name: [] for name in PARTY_NAMES}
    parties["기타 정당"] = []
    ministers: OrderedDict[str, OrderedDict[str, list[dict[str, str]]]] = OrderedDict()
    fields: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
    fields["기타"] = []
    if isinstance(items, list):
        for raw in items:
            text = raw.get("text") if isinstance(raw, dict) else raw
            line = normalize_line(text)
            if line:
                fields["기타"].append({**parse_event_text(line), "actor": "일정"})
    return core, parties, ministers, fields


def parse_schedule(schedule_data: dict[str, Any]) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]], OrderedDict[str, OrderedDict[str, list[dict[str, str]]]], OrderedDict[str, list[dict[str, str]]]]:
    body = schedule_data.get("raw_text") or schedule_data.get("body") or ""
    if body:
        field_lines, minister_lines = split_regions(body)
        core, parties, fields = parse_field_lines(field_lines)
        ministers = parse_minister_lines(minister_lines)
        if any(core.values()) or any(parties.values()) or fields or ministers:
            return core, parties, ministers, fields
    return parse_from_items(schedule_data.get("items") or [])


def render_event(item: dict[str, str]) -> str:
    loc = item.get("location", "")
    loc_html = f'<div class="loc"><span class="icon">📍</span>{esc(loc)}</div>' if loc else ""
    return (
        '<div class="event">'
        f'<div class="time-col">{esc(item.get("time") or "-")}</div>'
        '<div class="event-body">'
        f'<div class="event-title"><span class="icon">🕒</span>{esc(item.get("title") or "일정 확인 필요")}</div>'
        f"{loc_html}</div></div>"
    )


def render_empty(text: str = "표시할 일정이 없습니다.") -> str:
    return f'<div class="empty">{esc(text)}</div>'


def render_core(core: dict[str, list[dict[str, str]]]) -> str:
    blocks = []
    for label in ["대통령", "국무총리"]:
        events = core.get(label, [])
        rows = "".join(render_event(item) for item in events) if events else render_empty()
        blocks.append(f'<div class="core-block"><div class="group-title"><span class="person-badge">{esc(label)}</span></div>{rows}</div>')
    return "".join(blocks)


def party_class(name: str) -> str:
    return {
        "더불어민주당": "democratic",
        "국민의힘": "people-power",
        "조국혁신당": "rebuilding",
        "개혁신당": "reform",
    }.get(name, "other")


def render_parties(parties: dict[str, list[dict[str, str]]]) -> str:
    blocks = []
    for name in [*PARTY_NAMES, "기타 정당"]:
        events = parties.get(name, [])
        rows = "".join(render_event(item) for item in events) if events else render_empty()
        blocks.append(f'<div class="party-block"><div class="group-title"><span class="party-badge {party_class(name)}">{esc(name)}</span></div>{rows}</div>')
    return "".join(blocks)


def render_ministers(ministers: OrderedDict[str, OrderedDict[str, list[dict[str, str]]]]) -> str:
    if not ministers:
        return render_empty()
    blocks = []
    for dept, people in ministers.items():
        people_html = []
        for person, events in people.items():
            rows = "".join(render_event(item) for item in events) if events else render_empty()
            people_html.append(f'<div class="group-title"><span class="person-badge">{esc(person)}</span></div>{rows}')
        blocks.append(f'<div class="dept-block"><div class="group-title"><span class="dept-badge">{esc(dept)}</span></div>{"".join(people_html)}</div>')
    return "".join(blocks)


def render_fields(fields: OrderedDict[str, list[dict[str, str]]]) -> str:
    if not fields:
        return render_empty()
    names = [name for name in FIELD_CATEGORY_ORDER if name in fields]
    names.extend(name for name in fields.keys() if name not in names and name != "정치")
    blocks = []
    for name in names:
        rows = []
        for item in fields.get(name, []):
            actor = item.get("actor", "")
            actor_html = f'<div class="group-title"><span class="dept-badge">{esc(actor)}</span></div>' if actor else ""
            rows.append(actor_html + render_event(item))
        blocks.append(f'<div class="field-block"><div class="group-title"><span class="field-badge">{esc(name)}</span></div>{"".join(rows) if rows else render_empty()}</div>')
    return "".join(blocks)


def display_date(date_text: str) -> str:
    try:
        d = datetime.strptime(date_text, "%Y-%m-%d")
        weekdays = "월화수목금토일"
        return f"{d.year}년 {d.month}월 {d.day}일 ({weekdays[d.weekday()]})"
    except Exception:
        return date_text


def card(num: int, title: str, body: str) -> str:
    return (
        '<section class="card">'
        f'<div class="card-head"><span class="num-badge">{num}</span><div class="card-title">{esc(title)}</div></div>'
        f'<div class="card-body">{body}</div></section>'
    )


def render_html(schedule_data: dict[str, Any], date_text: str) -> str:
    core, parties, ministers, fields = parse_schedule(schedule_data)
    fallback_url = f"../reports/{date_text}.html"
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>전체 일정 상세 - {esc(date_text)}</title>
  <style>{STYLE}</style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <div class="eyebrow">Daily Issue Report</div>
      <h1>전체 일정 상세</h1>
      <div class="hero-date">{esc(display_date(date_text))}</div>
    </header>
    <div class="back-row"><button type="button" class="back-btn">← 뒤로가기</button></div>
    {card(1, "핵심 인사 일정", render_core(core))}
    {card(2, "정당 주요 일정", render_parties(parties))}
    {card(3, "장·차관 주요 일정", render_ministers(ministers))}
    {card(4, "부처·분야별 주요 일정", render_fields(fields))}
    <div class="back-row"><button type="button" class="back-btn">← 뒤로가기</button></div>
    <div class="footer-space"></div>
  </main>
  <script>
  (function(){{
    var fallbackUrl = {json.dumps(fallback_url, ensure_ascii=False)};
    function goBack(){{
      try {{
        if (window.parent && window.parent !== window) {{
          window.parent.postMessage({{type: "closeScheduleDetail"}}, "*");
          return;
        }}
      }} catch (e) {{}}
      if (window.history && window.history.length > 1) window.history.back();
      else window.location.href = fallbackUrl;
    }}
    document.querySelectorAll(".back-btn").forEach(function(btn){{
      btn.addEventListener("click", goBack);
    }});
  }})();
  </script>
</body>
</html>
"""


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, prefix=f".{path.name}.", suffix=".tmp") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def public_mirror_path(out_path: Path) -> Path | None:
    parts = list(out_path.parts)
    for idx, part in enumerate(parts):
        if part.lower() == "docs":
            base = Path(*parts[:idx]) if idx else Path()
            candidate = base / "public" / Path(*parts[idx + 1 :])
            public_root = base / "public"
            if public_root.exists():
                return candidate
            return None
    return None


def main() -> int:
    args = parse_args()
    schedule_path = Path(args.schedule_dir) / f"{args.date}.json"
    out_path = Path(args.out_dir) / f"{args.date}.html"

    if not schedule_path.exists():
        print(f"[WARN] 일정 JSON이 없어 상세 HTML 생성을 건너뜁니다: {schedule_path}")
        return 0

    schedule_data = json.loads(schedule_path.read_text(encoding="utf-8-sig"))
    html_text = render_html(schedule_data, args.date)
    atomic_write(out_path, html_text)
    print(f"[OK] 일정 상세 HTML 생성 완료: {out_path}")

    mirror = public_mirror_path(out_path)
    if mirror:
        atomic_write(mirror, html_text)
        print(f"[OK] public 일정 상세 HTML 동기화 완료: {mirror}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
