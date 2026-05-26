#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remove_calendar_report_viewer_label.py

대시보드 우상단에 노출되는 고정 문구 `Calendar Report Viewer`를 제거한다.
- docs/index.html, public/index.html을 모두 대상으로 한다.
- 파일이 없으면 건너뛰므로 GitHub Actions/로컬 실행 모두 안전하다.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

TARGETS = [Path("docs/index.html"), Path("public/index.html")]
LABEL = "Calendar Report Viewer"


def atomic_write(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, prefix=f".{path.name}.", suffix=".tmp") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def remove_label(text: str) -> str:
    # 1) 문구만 들어 있는 단독 HTML 요소는 요소째 제거한다.
    text = re.sub(
        r"\n?\s*<(?P<tag>[a-zA-Z][\w:-]*)(?P<attrs>[^>]*)>\s*Calendar\s+Report\s+Viewer\s*</(?P=tag)>\s*\n?",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    # 2) 요소 구조가 달라도 화면 노출 문구는 반드시 제거한다.
    text = re.sub(r"\s*Calendar\s+Report\s+Viewer\s*", "", text, flags=re.IGNORECASE)
    return text


def main() -> int:
    changed = 0
    for path in TARGETS:
        if not path.exists():
            print(f"[SKIP] 파일 없음: {path}")
            continue
        original = path.read_text(encoding="utf-8")
        updated = remove_label(original)
        if updated != original:
            atomic_write(path, updated)
            changed += 1
            print(f"[OK] 문구 제거 완료: {path}")
        else:
            print(f"[OK] 제거할 문구 없음: {path}")
    print(f"[DONE] 변경 파일 수: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
