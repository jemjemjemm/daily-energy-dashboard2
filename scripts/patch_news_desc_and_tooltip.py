#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch scripts/generate_html_report.py safely.

Purpose
- 대표 기사 제목 아래에 제목과 거의 같은 회색 설명이 반복되는 문제를 제거한다.
- summary/description이 실제 요약이면 그대로 사용하고, 제목 반복이면 간단한 기사 요약 문구로 대체한다.
- 기존 자동화 흐름(일정 수집, 가격 수집/병합, report-index 생성)은 건드리지 않는다.
- TOOLTIP_SCRIPT가 비어 있는 현재 파일에도 그래프 hover/touch tooltip을 복구한다.
"""
from __future__ import annotations

import re
from pathlib import Path

TARGET = Path("scripts/generate_html_report.py")

NEWS_HELPERS = r'''
def strip_article_source_suffix(text: str) -> str:
    """기사 제목 끝의 '- 언론사' 식 출처 표기를 제거한다."""
    text = clean_text(text)
    # 마지막 대시 뒤가 짧은 출처명처럼 보이면 제거한다.
    text = re.sub(r"\s[-–—]\s[^-–—]{2,18}$", "", text).strip()
    return text


def normalize_for_compare(text: str) -> str:
    text = strip_article_source_suffix(text)
    text = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE).lower()
    return text


def is_repeated_article_desc(title: str, desc: str) -> bool:
    """대표 기사 설명이 제목을 거의 그대로 반복하는지 판정한다."""
    title_n = normalize_for_compare(title)
    desc_n = normalize_for_compare(desc)
    if not desc_n:
        return True
    if title_n and (desc_n in title_n or title_n in desc_n):
        return True
    # 제목 앞부분이 설명 앞부분에 그대로 반복되는 경우
    if len(title_n) >= 16 and len(desc_n) >= 16 and title_n[:16] == desc_n[:16]:
        return True
    # 너무 짧은 설명은 요약으로 보기 어렵다.
    if len(desc_n) < 18:
        return True
    return False


def fallback_article_desc(title: str) -> str:
    """기사 제목이 반복될 때 보여줄 짧은 요약 문구를 제목 기반으로 생성한다."""
    t = strip_article_source_suffix(title)
    compact = re.sub(r"\s+", " ", t)

    if "호르무즈" in compact and "국제유가" in compact:
        if "브렌트" in compact:
            return "호르무즈 해협 개방 기대감에 따른 국제유가 하락과 브렌트유 가격 흐름을 다룬 보도."
        if "WTI" in compact.upper():
            return "호르무즈 해협 개방 기대감에 따른 국제유가 하락과 WTI 가격 흐름을 다룬 보도."
        return "호르무즈 해협 개방 기대감이 국제유가 하락 압력으로 작용한 흐름을 다룬 보도."

    if "석유화학" in compact:
        if "공급과잉" in compact:
            return "석유화학 업황 개선에도 공급과잉 부담이 지속되는 구조적 리스크를 다룬 보도."
        return "석유화학 업황과 주요 기업·시장 변동 요인을 정리한 보도."

    if "정유" in compact:
        if "정제마진" in compact or "재고" in compact or "실적" in compact:
            return "유가·정제마진·재고평가 흐름이 정유사 실적에 미치는 영향을 다룬 보도."
        return "정유업계 수익성 및 시장 여건 변화를 다룬 보도."

    if "SAF" in compact or "항공" in compact or "친환경 연료" in compact:
        return "고유가와 지속가능항공유 비용 부담이 항공·정유업계에 미치는 영향을 다룬 보도."

    if "LNG" in compact or "가스" in compact:
        return "LNG·가스 가격 및 수급 변동이 에너지 시장에 미치는 영향을 다룬 보도."

    if "유가" in compact or "원유" in compact or "석유" in compact:
        return "국제유가와 석유시장 변동 요인을 중심으로 시장 영향을 정리한 보도."

    return "해당 이슈의 시장 영향과 업계 관련성을 확인할 수 있는 대표 기사."


def article_desc_for_display(article: Mapping[str, Any]) -> str:
    """제목 반복 설명을 제거하고, 실제 요약 또는 간단한 대체 요약을 반환한다."""
    title = clean_text(article.get("title") or "")
    desc = clean_text(article.get("summary") or article.get("description") or article.get("desc") or "")
    if is_repeated_article_desc(title, desc):
        return fallback_article_desc(title)
    return desc
'''

TOOLTIP_SCRIPT = r'''TOOLTIP_SCRIPT = r"""
<script>
(function(){
  function parseChartPayload(box){
    if(!box) return null;
    var raw = box.getAttribute('data-chart') || '{}';
    try { return JSON.parse(raw); } catch(e) { return null; }
  }
  function valueText(v){
    if(v === null || v === undefined || v === '' || Number(v) === 0 || Number.isNaN(Number(v))) return '-';
    return Number(v).toFixed(2);
  }
  function ensureTooltip(box){
    var tip = box.querySelector('.chart-tooltip');
    if(!tip){
      tip = document.createElement('div');
      tip.className = 'chart-tooltip';
      box.appendChild(tip);
    }
    return tip;
  }
  function showAt(box, payload, clientX, clientY){
    if(!box || !payload || !payload.data || !payload.data.length) return;
    var rect = box.getBoundingClientRect();
    if(!rect.width || !rect.height) return;
    var width = payload.width || 440;
    var left = Number(payload.left || 38);
    var right = Number(payload.right || 10);
    var top = Number(payload.top || 16);
    var bottomY = Number(payload.bottomY || 198);
    var plotW = width - left - right;
    var relSvgX = Math.max(left, Math.min(width - right, (clientX - rect.left) / rect.width * width));
    var idx = Math.round((relSvgX - left) / plotW * (payload.data.length - 1));
    idx = Math.max(0, Math.min(payload.data.length - 1, idx));
    var row = payload.data[idx] || {};
    var svgX = left + (payload.data.length <= 1 ? 0 : idx / (payload.data.length - 1) * plotW);

    var line = box.querySelector('.chart-hover-line');
    if(line){
      line.setAttribute('x1', svgX);
      line.setAttribute('x2', svgX);
      line.setAttribute('y1', top);
      line.setAttribute('y2', bottomY);
      line.setAttribute('opacity', '0.45');
      line.style.opacity = '0.45';
    }

    var tip = ensureTooltip(box);
    var html = '<div class="date">' + (row.label || row.date || '') + '</div>';
    (payload.keys || []).forEach(function(pair){
      var key = pair[0], label = pair[1] || key;
      html += '<div class="tooltip-row"><span>' + label + '</span><b>' + valueText(row[key]) + '</b></div>';
    });
    tip.innerHTML = html;
    tip.style.display = 'block';

    var localX = clientX - rect.left;
    var localY = clientY - rect.top;
    var tipW = tip.offsetWidth || 150;
    var tipH = tip.offsetHeight || 100;
    var x = localX + 12;
    var y = localY - 10;
    if(x + tipW > rect.width) x = localX - tipW - 12;
    if(x < 4) x = 4;
    if(y + tipH > rect.height) y = rect.height - tipH - 4;
    if(y < 4) y = 4;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }
  function hide(box){
    if(!box) return;
    var line = box.querySelector('.chart-hover-line');
    if(line){
      line.setAttribute('opacity','0');
      line.style.opacity = '0';
    }
    var tip = box.querySelector('.chart-tooltip');
    if(tip) tip.style.display = 'none';
  }
  function attach(box){
    var payload = parseChartPayload(box);
    if(!payload || !payload.data || !payload.data.length) return;
    function move(clientX, clientY){ showAt(box, payload, clientX, clientY); }
    box.addEventListener('mousemove', function(e){ move(e.clientX, e.clientY); }, {passive:true});
    box.addEventListener('mouseleave', function(){ hide(box); }, {passive:true});
    box.addEventListener('click', function(e){ move(e.clientX, e.clientY); }, {passive:true});
    box.addEventListener('touchstart', function(e){ if(e.touches && e.touches[0]) move(e.touches[0].clientX, e.touches[0].clientY); }, {passive:true});
    box.addEventListener('touchmove', function(e){ if(e.touches && e.touches[0]) move(e.touches[0].clientX, e.touches[0].clientY); }, {passive:true});
    if(window.PointerEvent){
      box.addEventListener('pointerdown', function(e){ move(e.clientX, e.clientY); }, {passive:true});
      box.addEventListener('pointermove', function(e){ move(e.clientX, e.clientY); }, {passive:true});
      box.addEventListener('pointerleave', function(){ hide(box); }, {passive:true});
    }
  }
  function init(){
    var boxes = document.querySelectorAll('.chart-box[data-chart]');
    for(var i=0; i<boxes.length; i++) attach(boxes[i]);
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
</script>
""".strip()'''


def replace_render_news(text: str) -> str:
    replacement = r'''def render_news(data: Mapping[str, Any]) -> str:
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
        desc = article_desc_for_display(a)
        desc_html = f'<div class="news-link-desc">{esc(desc)}</div>' if desc else ''
        # 중요: 긴 URL 텍스트는 출력하지 않고, 제목에만 href를 건다.
        # 설명은 제목 반복이 아니라 실제 요약/대체 요약만 노출한다.
        rows.append(f'<a class="news-link" href="{esc(url)}" rel="noopener" target="_blank"><div class="news-link-title">{esc(title)}</div><div class="news-link-press">{esc(press)}</div>{desc_html}</a>')
    if not rows:
        rows.append('<div class="news-link"><div class="news-link-title">대표 기사 데이터 확인 필요</div><div class="news-link-press">-</div><div class="news-link-desc">조간 기사 후보가 report JSON에 반영되지 않음</div></div>')
    return f'<div class="news-body"><div class="news-trend">{esc(summary)}</div><div class="news-separator"></div><div class="news-links-title">대표 기사</div>{"".join(rows)}</div><div class="fact-note">※ 조간 트렌드는 웹 확인 가능한 기준일 오전 보도 중 정유·석유화학·LNG 업계 관련성이 높은 기사 중심 작성. 기사 내용 밖의 업계 영향 평가는 작성자 해석</div>'
'''
    pattern = r'def render_news\(data: Mapping\[str, Any\]\) -> str:\n.*?\n(?=TOOLTIP_SCRIPT\s*=)'
    new_text, n = re.subn(pattern, replacement + "\n", text, flags=re.S)
    if n != 1:
        raise RuntimeError(f"render_news 함수 교체 실패: match={n}")
    return new_text


def main() -> int:
    if not TARGET.exists():
        raise FileNotFoundError(f"대상 파일을 찾을 수 없습니다: {TARGET}")
    text = TARGET.read_text(encoding="utf-8")

    if "def article_desc_for_display" not in text:
        anchor = "def render_news(data: Mapping[str, Any]) -> str:"
        if anchor not in text:
            raise RuntimeError("render_news 함수를 찾지 못했습니다.")
        text = text.replace(anchor, NEWS_HELPERS + "\n\n" + anchor, 1)

    text = replace_render_news(text)

    tooltip_pattern = r'TOOLTIP_SCRIPT\s*=\s*r""".*?"""\.strip\(\)'
    text, n = re.subn(tooltip_pattern, TOOLTIP_SCRIPT, text, count=1, flags=re.S)
    if n != 1:
        raise RuntimeError(f"TOOLTIP_SCRIPT 교체 실패: match={n}")

    TARGET.write_text(text, encoding="utf-8")
    print(f"[OK] 패치 완료: {TARGET}")
    print("[OK] 대표 기사 설명 반복 제거 + 간단 요약 대체 + 그래프 tooltip 유지")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
