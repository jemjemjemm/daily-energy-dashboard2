# daily-energy-dashboard 최종 수정 패키지 (2026-05-26)

## 목적
- 원유/석유제품 가격 추이 그래프의 날짜별 tooltip 복원
- iPhone Safari 터치 환경에서도 tooltip 표시
- 조간 신문 트렌드 대표 기사 하단의 긴 URL 텍스트 미노출 유지
- 대시보드 우상단 `Calendar Report Viewer` 문구 제거
- 기존 자동화의 데이터 수집·가격 병합·뉴스 수집 로직은 변경하지 않음

## 교체/추가 파일
1. `scripts/generate_html_report.py` 교체
2. `scripts/remove_calendar_report_viewer_label.py` 추가

## 적용 후 실행
```bash
python -m py_compile scripts/generate_html_report.py
python -m py_compile scripts/remove_calendar_report_viewer_label.py
python scripts/remove_calendar_report_viewer_label.py
python scripts/generate_html_report.py --date 2026-05-26 --report-dir data/reports --out-dir docs/reports
python scripts/generate_report_index.py --reports-dir docs/reports --out docs/report-index.json
```

## 5/4~5/26 전체 리포트 재생성 시
기존에 사용하던 `scripts/generate_reports_range.py` 명령을 그대로 사용하면 됩니다.
이 패키지는 최종 HTML 렌더링만 바꾸므로, 5/27 이후 자동화의 수집/병합 순서에는 영향을 주지 않습니다.

## 확인 포인트
- 생성 HTML 안에 `data-chart`와 `pointerdown`, `touchmove`가 포함되어야 합니다.
- 대표 기사 제목에는 href가 있고, 별도 긴 URL 텍스트는 보이지 않아야 합니다.
- `docs/index.html`에서 `Calendar Report Viewer` 문구가 없어야 합니다.
