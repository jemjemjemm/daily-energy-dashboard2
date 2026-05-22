#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_news_candidates.py v1.0
정유·석유화학·LNG Daily Issue Report용 조간 기사 후보를 수집합니다.
API 키 없이 GitHub Actions에서 실행 가능하도록 Google News RSS를 사용합니다.
"""
from __future__ import annotations
import argparse, email.utils, html, json, re, tempfile, time, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
import requests

KST = timezone(timedelta(hours=9))
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36"
QUERIES = [
    "정유 OR 유가 OR 석유제품 OR 주유소 OR 유류세",
    "석유화학 OR 나프타 OR 에틸렌 OR 프로필렌",
    "LNG OR 가스 OR 전력 OR 에너지 공급망",
    "최고가격제 OR 민생물가 OR 생산자물가 석유",
    "중동 위기 원유 수급 에너지",
]
POSITIVE = {
    "정유":8,"정유사":9,"유가":8,"석유":8,"석유제품":9,"주유소":7,"유류세":7,"휘발유":7,"경유":7,"나프타":8,"항공유":6,
    "석유화학":9,"화학제품":5,"에틸렌":6,"프로필렌":6,"LNG":8,"가스":5,"전력":4,"원전":4,"에너지":5,
    "원유":8,"브렌트":6,"WTI":6,"두바이유":6,"OPEC":5,"중동":6,"호르무즈":8,"공급망":5,"수급":5,
    "물가":5,"생산자물가":7,"최고가격제":10,"가격상한":8,"정부":2,"산업부":5,"기후부":4,"공정위":5,"국회":4,
    "SK이노베이션":6,"SK에너지":6,"GS칼텍스":6,"에쓰오일":6,"현대오일뱅크":6,
}
NEGATIVE = {"오늘의 주요일정":50,"주요일정":40,"인사":20,"부고":20,"동정":15,"특징주":8,"야구":15,"축구":15,"농구":15,"연예":15,"맛집":15,"여행":10,"공연":10,"전시":10}
TOPIC_RULES = [
    ("석유 최고가격제·유류세 등 가격 안정 정책", ["최고가격제","유류세","가격상한","주유소","휘발유","경유"]),
    ("중동 정세와 원유·LNG 수급 리스크", ["중동","호르무즈","원유","LNG","가스","수급","공급망"]),
    ("정유·석유화학 업계 실적·원가·제품 가격", ["정유","정유사","석유화학","나프타","화학제품","원가"]),
    ("물가 지표와 에너지 비용 부담", ["물가","생산자물가","소비자물가","에너지","석유제품"]),
    ("정부·국회 에너지 정책 일정", ["정부","산업부","기후부","공정위","국회","회의","브리핑"]),
]

def parse_args():
    p=argparse.ArgumentParser(description="조간 기사 후보 수집")
    p.add_argument("--date", required=True)
    p.add_argument("--out-dir", default="data/news")
    p.add_argument("--max-items", type=int, default=12)
    p.add_argument("--strict-morning", action="store_true")
    p.add_argument("--force-refresh", action="store_true")
    return p.parse_args()

def atomic_write_json(path:Path,payload:Dict[str,Any]):
    path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(payload,ensure_ascii=False,indent=2)
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=str(path.parent),delete=False,prefix=f".{path.name}.",suffix=".tmp") as tmp:
        tmp.write(text); tmp_path=Path(tmp.name)
    tmp_path.replace(path)

def clean_text(v:str)->str:
    v=html.unescape(v or "")
    v=re.sub(r"<[^>]+>"," ",v)
    return re.sub(r"\s+"," ",v).strip()

def original_url(link:str)->str:
    try:
        qs=parse_qs(urlparse(link).query)
        if qs.get("url"): return unquote(qs["url"][0])
    except Exception: pass
    return link

def parse_pub_date(v:str):
    if not v: return "",""
    try:
        dt=email.utils.parsedate_to_datetime(v)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        k=dt.astimezone(KST)
        return k.strftime("%Y-%m-%d"), k.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "",""

def score_article(title:str,snippet:str,source:str)->int:
    text=f"{title} {snippet} {source}"
    score=sum(w for k,w in POSITIVE.items() if k.lower() in text.lower())
    score-=sum(w for k,w in NEGATIVE.items() if k.lower() in text.lower())
    if any(k in text for k in ["정유","석유","유가","LNG","나프타","주유소"]): score+=5
    if any(k in text for k in ["정부","국회","산업부","공정위","기후부"]): score+=2
    return score

def fetch_google_news(query:str,target:datetime):
    after=target.strftime("%Y-%m-%d"); before=(target+timedelta(days=1)).strftime("%Y-%m-%d")
    q=f"({query}) after:{after} before:{before}"
    url="https://news.google.com/rss/search?q="+quote_plus(q)+"&hl=ko&gl=KR&ceid=KR:ko"
    r=requests.get(url,headers={"User-Agent":USER_AGENT,"Accept-Language":"ko-KR,ko;q=0.9"},timeout=25)
    r.raise_for_status()
    root=ET.fromstring(r.content)
    out=[]
    for item in root.findall("./channel/item"):
        title=clean_text(item.findtext("title", "")); link=original_url(clean_text(item.findtext("link", "")))
        pub_date,pub_kst=parse_pub_date(clean_text(item.findtext("pubDate", "")))
        source_node=item.find("source"); source=clean_text(source_node.text if source_node is not None and source_node.text else "")
        snippet=clean_text(item.findtext("description", ""))
        if not title or not link: continue
        score=score_article(title,snippet,source)
        if score < 8: continue
        out.append({"title":title,"press":source or "Google News","url":link,"published_date":pub_date,"published_at_kst":pub_kst,"snippet":snippet,"score":score,"source_query":query})
    return out

def is_morning(item,target_date):
    pub=item.get("published_at_kst") or ""
    if not pub: return (not item.get("published_date")) or item.get("published_date")==target_date
    if not pub.startswith(target_date): return False
    try:
        h,m=map(int,pub.split()[1].split(":")); return 0 <= h*60+m <= 10*60+30
    except Exception: return True

def dedupe(items):
    seen=set(); out=[]
    for it in sorted(items,key=lambda x:int(x.get("score",0)),reverse=True):
        key=(re.sub(r"\s+","",it.get("title","").lower())[:80], it.get("url",""))
        if key in seen: continue
        seen.add(key); out.append(it)
    return out

def infer_topics(items):
    text=" ".join(f"{i.get('title','')} {i.get('snippet','')}" for i in items)
    topics=[]
    for label,keys in TOPIC_RULES:
        if any(k in text for k in keys): topics.append(label)
    return topics[:4]

def build_summary(topics,items):
    if topics: return "주요 매체는 " + ", ".join(topics) + " 등을 중심으로 정유·석유화학·LNG 업계 관련 이슈를 다뤘습니다."
    if items: return "정유·석유화학·LNG 관련 조간 기사 후보가 수집됐습니다."
    return "정유·석유화학·LNG 관련 조간 기사 후보를 찾지 못했습니다."

def has_existing_articles(path:Path)->bool:
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("articles"))
    except Exception:
        return False

def main():
    a=parse_args(); target=datetime.strptime(a.date,"%Y-%m-%d").replace(tzinfo=KST)
    out_path=Path(a.out_dir)/f"{a.date}.json"
    if out_path.exists() and not a.force_refresh:
        print(f"[OK] 기존 뉴스 후보 JSON 재사용: {out_path}"); return 0
    had_existing_articles=out_path.exists() and has_existing_articles(out_path)
    collected=[]; errors=[]
    for q in QUERIES:
        try:
            collected.extend(fetch_google_news(q,target)); time.sleep(0.25)
        except Exception as e: errors.append(f"{q}: {e}")
    candidates=dedupe(collected)
    morning=[i for i in candidates if is_morning(i,a.date)]
    selected=(morning if morning else candidates)[:a.max_items]
    if not selected and had_existing_articles:
        print(f"[WARN] 새 뉴스 후보가 없어 기존 뉴스 JSON을 보존합니다: {out_path}")
        return 0
    topics=infer_topics(selected)
    payload={"schema_version":"1.0","date":a.date,"collected_at":datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),"source":"Google News RSS","queries":QUERIES,"time_window":"00:00~10:30 KST 우선","summary":build_summary(topics,selected),"topics":topics,"articles":selected,"errors":errors,"success":bool(selected)}
    atomic_write_json(out_path,payload)
    print(f"[OK] 뉴스 후보 저장 완료: {out_path} / articles={len(selected)}")
    if errors: print("[WARN] 일부 검색 오류:", " | ".join(errors[:3]))
    return 0
if __name__=="__main__": raise SystemExit(main())
