#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""뉴스 후보 JSON을 리포트 JSON의 조간 신문 트렌드와 Summary에 반영합니다.

원칙
- 새 뉴스 후보가 1건 이상 있을 때만 기존 news_trend를 대체한다.
- Google News RSS 오류/무결과로 기존 정상 기사 3건을 빈 값으로 덮어쓰지 않는다.
- 기사 후보가 없으면 '찾지 못함'으로만 명시하고, 임의 기사/요약을 만들지 않는다.
"""
from __future__ import annotations
import argparse, json, re, tempfile
from pathlib import Path
from typing import Any, Dict, List

BAD_TITLES=["오늘의 주요일정","주요일정","대표 기사 데이터 없음","자동 수집 미적용"]
BAD_SUMMARY_PHRASES=["자동 수집된 대표 기사 없음", "가격 데이터 중심", "원문 데이터", "fallback"]
PRICE_SUMMARY_RE=re.compile(r"\s*가격 그래프는 기준일 전일 기준 과거 2개월\([^)]*\)만 표시하며, 값이 0인 가격은 제외\.?,?", re.U)

def parse_args():
    p=argparse.ArgumentParser(description="뉴스 후보를 리포트 JSON에 반영")
    p.add_argument("--date", required=True)
    p.add_argument("--report-dir", default="data/reports")
    p.add_argument("--news-dir", default="data/news")
    p.add_argument("--max-articles", type=int, default=3)
    return p.parse_args()

def read_json(path:Path)->Dict[str,Any]:
    if not path.exists(): return {}
    return json.loads(path.read_text(encoding="utf-8"))

def atomic_write_json(path:Path,payload:Dict[str,Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    text=json.dumps(payload,ensure_ascii=False,indent=2)
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=str(path.parent),delete=False,prefix=f".{path.name}.",suffix=".tmp") as tmp:
        tmp.write(text); tmp_path=Path(tmp.name)
    tmp_path.replace(path)

def clean(v:Any)->str:
    return re.sub(r"\s+"," ","" if v is None else str(v)).strip()

def valid_article(item:Dict[str,Any])->bool:
    title=clean(item.get("title")); url=clean(item.get("url"))
    return bool(title and url and not any(b in title for b in BAD_TITLES))

def normalize_article(item:Dict[str,Any])->Dict[str,str]:
    title=clean(item.get("title")); snippet=clean(item.get("summary") or item.get("snippet"))
    if snippet:
        snippet=re.sub(r" - [^ ]+(?:\s|$)"," ",snippet)
        snippet=re.sub(r"\s+"," ",snippet).strip()
        summary=snippet[:147]+"..." if len(snippet)>150 else snippet
    else:
        summary="원문 링크 확인 후 세부 내용 검수가 필요합니다."
    return {
        "title": title,
        "press": clean(item.get("press") or item.get("source")) or "Google News",
        "url": clean(item.get("url")),
        "summary": summary,
        "published_at_kst": clean(item.get("published_at_kst")),
    }

def existing_valid_articles(report:Dict[str,Any])->List[Dict[str,Any]]:
    news=report.get("news_trend",{}) if isinstance(report.get("news_trend"),dict) else {}
    articles=news.get("articles",[]) if isinstance(news.get("articles"),list) else []
    return [a for a in articles if isinstance(a,dict) and valid_article(a)]

def build_news_summary(news:Dict[str,Any], articles:List[Dict[str,Any]])->str:
    topics=[clean(t) for t in news.get("topics",[]) if clean(t)]
    if topics:
        return "주요 매체는 " + ", ".join(topics[:4]) + " 등을 중심으로 정유·석유화학·LNG 업계 관련 이슈를 다뤘습니다."
    provided=clean(news.get("summary"))
    if provided and not any(x in provided for x in ["찾지 못했습니다", "오류", "실패"]):
        return provided
    if articles:
        titles=", ".join(a.get("title","") for a in articles[:3])
        return f"정유·석유화학·LNG 관련 조간 기사 후보로 {titles} 등이 수집됐습니다."
    return "정유·석유화학·LNG 관련 조간 기사 후보를 찾지 못했습니다."

def update_summary(report:Dict[str,Any], news_summary:str):
    existing=report.get("summary",[]) if isinstance(report.get("summary"),list) else []
    cleaned=[]
    for item in existing:
        if not isinstance(item,dict) or item.get("type")=="news_trend": continue
        text=PRICE_SUMMARY_RE.sub("", clean(item.get("text"))).strip()
        if not text: continue
        item=dict(item); item["text"]=text; cleaned.append(item)
    while len(cleaned)<2:
        typ="stakeholder" if len(cleaned)==0 else "today"
        label="주요 이해관계자 동향" if typ=="stakeholder" else "금일 주요 일정"
        cleaned.append({"type":typ,"text":f"{label}: 관련 자료 찾지 못함."})
    cleaned=cleaned[:2]
    cleaned.append({"type":"news_trend","text":"조간 보도: "+news_summary})
    report["summary"]=cleaned

def main():
    a=parse_args()
    report_path=Path(a.report_dir)/f"{a.date}.report.json"
    news_path=Path(a.news_dir)/f"{a.date}.json"
    report=read_json(report_path)
    if not report:
        print(f"[WARN] 리포트 JSON이 없어 뉴스 반영을 건너뜁니다: {report_path}"); return 0

    news=read_json(news_path)
    raw_articles=news.get("articles",[]) if isinstance(news.get("articles"),list) else []
    new_articles=[normalize_article(i) for i in raw_articles if isinstance(i,dict) and valid_article(i)][:a.max_articles]
    old_articles=existing_valid_articles(report)[:a.max_articles]

    if new_articles:
        articles=new_articles
        news_summary=build_news_summary(news,articles)
        source="Google News RSS"
        status="updated"
    elif old_articles:
        articles=[normalize_article(i) for i in old_articles]
        old_news=report.get("news_trend",{}) if isinstance(report.get("news_trend"),dict) else {}
        old_summary=clean(old_news.get("summary"))
        news_summary=old_summary if old_summary and not any(p in old_summary for p in BAD_SUMMARY_PHRASES) else build_news_summary({},articles)
        source=clean(old_news.get("source")) or "existing report"
        status="preserved_existing"
    else:
        articles=[]
        news_summary="정유·석유화학·LNG 관련 조간 기사 후보를 찾지 못했습니다."
        source="Google News RSS"
        status="no_articles"

    report["news_trend"]={"summary":news_summary,"articles":articles,"source":source,"needs_review":True}
    update_summary(report,news_summary)
    report.setdefault("automation",{})["news"]={"source_file":str(news_path),"article_count":len(articles),"source":source,"status":status,"needs_review":True}
    atomic_write_json(report_path,report)
    print(f"[OK] 뉴스 후보 반영 완료: {report_path} / status={status} / articles={len(articles)}")
    return 0
if __name__=="__main__": raise SystemExit(main())
