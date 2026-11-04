#!/usr/bin/env python3
"""Index MAFF's 47 official prefecture pages. No inferred recipes or historical edges."""
import csv, hashlib, json, os, re, time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

BASE="https://www.maff.go.jp/j/keikaku/syokubunka/k_ryouri/search_menu/area/"
GROUPS=[
("北海道","hokkaido",27),("青森県","aomori",29),("岩手県","iwate",30),("宮城県","miyagi",29),
("秋田県","akita",29),("山形県","yamagata",29),("福島県","fukushima",30),
("茨城県","ibaraki",30),("栃木県","tochigi",30),("群馬県","gunma",27),("埼玉県","saitama",29),
("千葉県","chiba",28),("東京都","tokyo",30),("神奈川県","kanagawa",23),
("新潟県","niigata",30),("富山県","toyama",30),("石川県","ishikawa",30),("福井県","fukui",29),
("山梨県","yamanasi",30),("長野県","nagano",29),("岐阜県","gifu",30),("静岡県","shizuoka",28),
("愛知県","aichi",30),("三重県","mie",30),("滋賀県","shiga",30),("京都府","kyoto",30),
("大阪府","osaka",30),("兵庫県","hyogo",30),("奈良県","nara",30),("和歌山県","wakayama",27),
("鳥取県","tottori",27),("島根県","shimane",28),("岡山県","okayama",28),("広島県","hiroshima",30),
("山口県","yamaguchi",30),("徳島県","tokushima",30),("香川県","kagawa",30),("愛媛県","ehime",25),
("高知県","kochi",30),("福岡県","fukuoka",30),("佐賀県","saga",25),("長崎県","nagasaki",30),
("熊本県","kumamoto",29),("大分県","oita",30),("宮崎県","miyazaki",30),("鹿児島県","kagoshima",30),
("沖縄県","okinawa",30)]
assert len(GROUPS)==47 and sum(p[2] for p in GROUPS)==1365
UA="CulinaryLineageResearch/1.1 (+https://github.com/TaishiNemoto/localcuisine; index only)"

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.href=None; self.parts=[]; self.links=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="a" and self.href is None:
            self.href=a.get("href",""); self.parts=[]
        elif tag=="img" and self.href is not None:
            t=a.get("alt","").strip()
            if t and len(t)<60 and not any(w in t.lower() for w in ["写真","画像","image","ロゴ","logo"]):
                self.parts.append(t)
    def handle_data(self,data):
        if self.href is not None and data.strip():
            self.parts.append(re.sub(r"\s+"," ",data.strip()))
    def handle_endtag(self,tag):
        if tag=="a" and self.href is not None:
            self.links.append((self.href,self.parts[:]))
            self.href=None; self.parts=[]

def normalize(text):
    import unicodedata
    return unicodedata.normalize("NFKC",text).strip()

def fetch(url, robots):
    if not robots.can_fetch(UA,url): raise PermissionError("robots disallow "+url)
    req=Request(url,headers={"User-Agent":UA,"Accept":"text/html"})
    with urlopen(req,timeout=40) as response:
        return response.read().decode("utf-8","replace")

def extract(html,pref,slug):
    page=BASE+slug+".html"; links=LinkParser(); links.feed(html)
    seen=set(); rows=[]
    for href,parts in links.links:
        url=urljoin(page,href)
        p=urlparse(url)
        if p.netloc!="www.maff.go.jp" or "/k_ryouri/search_menu/menu/" not in p.path or not p.path.endswith(".html") or url in seen:continue
        seen.add(url)
        candidate=[normalize(s) for s in parts if normalize(s)]
        name=next((s for s in candidate if 1<=len(s)<=54 and not any(c in s for c in "。！？")),None)
        if not name: name=p.path.rsplit("/",1)[-1][:-5]
        if len(name)>65: name=name[:65]
        rows.append({
          "id":hashlib.sha256((pref+"|"+url).encode()).hexdigest()[:14],
          "name":name,"prefecture":pref,"source_url":url,"source_index_url":page,
          "source_name":"農林水産省・うちの郷土料理",
          "record_status":"index_extracted_needs_review",
          "category":"未分類","ingredients":[],"techniques":[],"aliases":[],
          "lineage_status":"not_assessed","taxonomy":None})
    return rows

def main():
    robots=RobotFileParser("https://www.maff.go.jp/robots.txt")
    robots.read()
    if robots.mtime()==0:raise RuntimeError("Cannot verify robots.txt; collection stopped")
    items=[]; report=[]; cache=Path(".cache/maff");cache.mkdir(parents=True,exist_ok=True)
    for i,(pref,slug,expected) in enumerate(GROUPS,1):
        page=BASE+slug+".html"; dest=cache/(slug+".html")
        try:
            html=dest.read_text(encoding="utf-8") if dest.exists() else fetch(page,robots)
            if not dest.exists():dest.write_text(html,encoding="utf-8")
            found=extract(html,pref,slug)
            ok=len(found)==expected
            report.append({"prefecture":pref,"expected":expected,"actual":len(found),"ok":ok,"url":page})
            items.extend(found)
            print(f"[{i}/47] {pref}: {len(found)}/{expected} {'ok' if ok else 'mismatch'}",flush=True)
        except Exception as exc:
            report.append({"prefecture":pref,"expected":expected,"actual":0,"ok":False,"url":page,"error":str(exc)})
            print(f"[{i}/47] ERROR {pref}: {exc}",flush=True)
        if i<47 and not dest.exists():time.sleep(2)
    urls=[x["source_url"] for x in items]
    complete=(len(items)==1365 and len(set(urls))==1365 and all(r["ok"] for r in report))
    out=Path("data");out.mkdir(exist_ok=True)
    payload={"meta":{
      "title":"郷土料理系統図","target_count":1365,"actual_count":len(items),
      "verified_prefectures":sum(r["ok"] for r in report),"import_complete":complete,
      "retrieved_at":datetime.now(timezone.utc).isoformat(),
      "source_url":"https://www.maff.go.jp/j/keikaku/syokubunka/k_ryouri/search_menu/",
      "evidence_note":"Index records only. Historical lineage is not asserted.",
      "source_attribution":"出典: 農林水産省 うちの郷土料理 (加工して作成)"},
      "prefectures":[{"name":p,"slug":s,"expected":n} for p,s,n in GROUPS],
      "dishes":items,"relations":[],"import_report":report}
    (out/"maff.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    with (out/"maff.csv").open("w",encoding="utf-8-sig",newline="") as fh:
        writer=csv.DictWriter(fh,fieldnames=["id","name","prefecture","source_url","record_status"])
        writer.writeheader()
        for x in items:writer.writerow({k:x[k] for k in writer.fieldnames})
    (out/"import_report.json").write_text(json.dumps({"complete":complete,"total":len(items),"prefectures":report},ensure_ascii=False,indent=2),encoding="utf-8")
    print("SUCCESS" if complete else "INCOMPLETE",len(items),"/1365")
    if not complete:raise SystemExit(2)
if __name__=="__main__":main()
