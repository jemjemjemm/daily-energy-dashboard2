# 대표 기사 설명 반복 제거 + 그래프 tooltip 유지 패치

## 수정 목적

- 조간 신문 트렌드의 `대표 기사` 영역에서 제목 아래 회색 설명이 제목을 그대로 반복하는 문제를 제거합니다.
- `summary/description/desc`가 실제 요약이면 그대로 사용합니다.
- 설명이 제목과 같거나 너무 비슷하면 기사 제목의 키워드 기반으로 짧은 요약 문구를 자동 대체합니다.
- 제목 클릭 링크는 유지하고 긴 URL 텍스트는 계속 노출하지 않습니다.
- 기존 자동화 흐름인 일정 수집, 뉴스 수집, 가격 수집, 가격 병합, report-index 생성 로직은 건드리지 않습니다.
- 현재 GitHub 원본에서 비어 있는 `TOOLTIP_SCRIPT`도 함께 복구하므로 PC hover 및 iPhone Safari touch/pointer tooltip도 유지됩니다.

## 적용 파일

새 파일 1개를 추가합니다.

```bash
scripts/patch_news_desc_and_tooltip.py
```

이 파일은 1회성 패치 스크립트입니다. 실행 후 실제로 수정되는 파일은 아래 1개입니다.

```bash
scripts/generate_html_report.py
```

## 적용 순서

repo 루트에서 실행하세요.

```bash
python scripts/patch_news_desc_and_tooltip.py
python -m py_compile scripts/generate_html_report.py
```

5/26 리포트만 다시 생성하려면:

```bash
python scripts/generate_html_report.py --date 2026-05-26 --report-dir data/reports --out-dir docs/reports
python scripts/generate_report_index.py --reports-dir docs/reports --out docs/report-index.json
```

과거 리포트 전체에도 동일 양식을 반영하려면 기존 backfill 명령으로 5/4~5/26을 다시 생성하세요.

```bash
python scripts/generate_reports_range.py \
  --start 2026-05-04 \
  --end 2026-05-26 \
  --skip-weekends \
  --skip-korean-holidays \
  --report-dir data/reports \
  --schedule-dir data/schedules \
  --price-dir data/prices \
  --history data/prices/history.json \
  --html-dir docs/reports \
  --index-out docs/report-index.json \
  --base-report report_sample.json \
  --chart-months 2 \
  --max-pages 80
```

## 확인 기준

생성된 `docs/reports/2026-05-26.html`에서 아래를 확인합니다.

```bash
grep -n "국제유가, 호르무즈" docs/reports/2026-05-26.html
grep -n "chart-tooltip\|touchmove\|pointermove" docs/reports/2026-05-26.html
```

정상 결과:

- 제목 아래 설명이 제목을 그대로 반복하지 않습니다.
- 설명은 `호르무즈 해협 개방 기대감에 따른 국제유가 하락...` 같은 짧은 요약으로 표시됩니다.
- 그래프 hover/touch tooltip 관련 문자열이 HTML에 포함됩니다.

## 5/27 이후 자동화 영향

이 패치는 최종 HTML 렌더링 함수만 수정합니다.

수정하지 않는 영역:

- GitHub Actions YAML
- SafeTimes 일정 수집
- 뉴스 후보 수집
- Opinet 가격 수집
- 가격 병합
- report JSON 생성
- report-index 생성

따라서 5/27 이후 자동화 흐름은 기존 그대로 유지됩니다.
