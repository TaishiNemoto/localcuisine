#!/usr/bin/env python3
"""Stratified source-detail enrichment of the MAFF official catalogue.

One indexed item and one likely ambiguous item per prefecture. Output remains
MACHINE-EXTRACTED and must not be treated as verified culinary genealogy.
"""
import json,re,time
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
from bs4 import BeautifulSoup

LABELS=[
'主な伝承地域','主な使用食材','歴史・由来・関連行事',
'食習の機会や時季','飲食方法','保存・継承の取組','材料','作り方']
CONTEXT=('北前船','鯖街道','街道','交易','商人','港','海運','航路','渡来',
'伝来','移住','黒潮','海岸','漁','雪','山','川','河川','神事','祭り','正月','盆')
PATTERNS={
'煮る':r'煮る|煮込|煮付|煮て|煮立',
'焼く':r'焼く|焼き|焼いて',
'蒸す':r'蒸す|蒸し',
'揚げる':r'揚げ|揚げる',
'漬ける':r'漬け|塩漬',
'包む':r'包む|包んで',
'巻く':r'巻く|巻いて',
'炊く':r'炊く|炊いて',
'発酵':r'発酵|熟成|寝かせ',
'干す':r'干す|乾燥|干して'}
UA='CulinaryLineageAcademicAudit/1.4 (+https://github.com/TaishiNemoto/localcuisine)'
PENDING=re.compile(r'ラーメン|いちご煮|しそ巻き|さつま|がめ煮|しっぽく|こづゆ|あざら|ざくざく|いりちー|イリチー|ちゃんちゃん|ずんだ|がんづき|だし$|ごんぼ|すみつかれ|みみ$|しもつかれ|いもぼた|おくずかけ|けいらん')

def section(lines,label):
    i=next((i for i,s in enumerate(lines) if s==label),None)
    if i is None:return ''
    end=len(lines)
    for j in range(i+1,min(i+100,len(lines))):
        if any(lines[j]==x or lines[j].startswith(x+'（') for x in LABELS):
            end=j;break
    return ' '.join(lines[i+1:end])[:6000]

def decode(html):
    soup=BeautifulSoup(html,'html.parser')
    for tag in soup(['script','style','nav','footer','header']):
        tag.decompose()
    lines=[t.strip() for t in soup.get_text('\n',strip=True).splitlines() if t.strip()]
    materials=section(lines,'主な使用食材')[:250]
    ingr=[v.strip(' 。・\t') for v in re.split(r'[,，、／/]',materials)]
    ingr=[v for v in ingr if 1<=len(v)<=26 and not any(w in v for w in ['画像','主な伝承','歴史・由来','レシピ'])]
    ingr=list(dict.fromkeys(ingr))[:15]
    history=section(lines,'歴史・由来・関連行事')
    method=section(lines,'作り方')
    if not method:
        method=section(lines,'飲食方法')
    tech=[k for k,p in PATTERNS.items() if re.search(p,method)]
    return {
      'ingredients':ingr,'techniques':tech,
      'traditional_area':section(lines,'主な伝承地域')[:100],
      'historical_context_terms':[k for k in CONTEXT if k in history],
      'sections':{'main_ingredients':bool(materials),'history':bool(history),'method':bool(method)},
      'extraction_status':'machine_extracted_needs_review'
    }

def main():
    src=json.loads(Path('data/maff.json').read_text(encoding='utf-8'))
    robots=RobotFileParser('https://www.maff.go.jp/robots.txt');robots.read()
    if robots.mtime()==0:raise RuntimeError('Could not verify robots policy')
    choice=[]
    for pref in src['prefectures']:
        rows=[d for d in src['dishes'] if d['prefecture']==pref['name']]
        if not rows:raise RuntimeError('Missing prefecture '+pref['name'])
        a=rows[0]
        b=next((d for d in rows[1:] if PENDING.search(d['name'])),None)
        if not b:b=rows[-1]
        choice += [a,b]
    out=[];fail=[];cache=Path('.cache/detail_sample');cache.mkdir(parents=True,exist_ok=True)
    for i,d in enumerate(choice,1):
        u=d['source_url'];path=urlparse(u)
        if path.netloc!='www.maff.go.jp' or '/search_menu/menu/' not in path.path:
            fail.append({'id':d['id'],'reason':'bad url'});continue
        if not robots.can_fetch(UA,u):
            fail.append({'id':d['id'],'reason':'robots disallow'});continue
        c=cache/(d['id']+'.html')
        try:
            if c.exists(): html=c.read_text(encoding='utf-8')
            else:
                with urlopen(Request(u,headers={'User-Agent':UA,'Accept':'text/html'}),timeout=30) as f:
                    html=f.read().decode('utf-8','replace')
                c.write_text(html,encoding='utf-8')
            obj={k:d[k] for k in ['id','name','prefecture','source_url']}
            obj.update(decode(html))
            obj['record_status']='detail_extracted_needs_review'
            obj['checked_at']=datetime.now(timezone.utc).isoformat()
            if not obj['ingredients']:fail.append({'id':d['id'],'name':d['name'],'reason':'ingredients empty'})
            out.append(obj)
            print(f'{i}/{len(choice)} {d["prefecture"]} {d["name"]} ingredients={len(obj["ingredients"])}',flush=True)
        except Exception as e:
            fail.append({'id':d['id'],'name':d['name'],'reason':str(e)[:170]})
            print(f'{i}/{len(choice)} FAILED {d["name"]}: {str(e)[:90]}',flush=True)
        if i<len(choice):time.sleep(1.1)
    Path('data/detail_sample.json').write_text(json.dumps({
        'meta':{'scope':'two records per prefecture, STRATIFIED SAMPLE ONLY',
                'expected':94,'fetched':len(out),'machine_extraction':True,
                'historical_relations_verified':0,
                'created_at':datetime.now(timezone.utc).isoformat()},
        'records':out,'issues':fail},ensure_ascii=False,indent=2),encoding='utf-8')
    print('COMPLETED',len(out),'/',len(choice),'issues',len(fail))
    if len(out)<90:raise SystemExit(2)

if __name__=='__main__':main()
