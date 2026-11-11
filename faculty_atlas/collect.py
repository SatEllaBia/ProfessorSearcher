from __future__ import annotations
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import httpx
from bs4 import BeautifulSoup
from .db import add_professor, dump_json, store_source

DIRECTORY='https://ai.hku.hk/people/academic-staff'
MESSAGES='https://ai.hku.hk/programmes/research-based/mphil-phd-msg'

def extract(html):
    soup=BeautifulSoup(html,'html.parser')
    for e in soup(['script','style','noscript','nav','footer']):
        e.decompose()
    return '\n'.join(s.strip() for s in soup.get_text('\n').splitlines() if s.strip())

def links(html,url):
    soup=BeautifulSoup(html,'html.parser')
    return [{'text':a.get_text(' ',strip=True),'url':urljoin(url,a['href'])}
            for a in soup.select('a[href]') if urlsplit(urljoin(url,a['href'])).scheme in ('http','https')]

def fetch(con,root,url,*,refresh=False,browser=False):
    method='playwright' if browser else 'http'
    if not refresh:
        old=con.execute("SELECT id FROM sources WHERE url=? AND state='ok' AND fetch_method=? AND html_path IS NOT NULL ORDER BY id DESC LIMIT 1",(url,method)).fetchone()
        if old:
            return old[0]
    try:
        if browser:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as e:
                raise RuntimeError('Install optional browser dependencies: uv sync --extra browser; uv run playwright install chromium') from e
            with sync_playwright() as p:
                b=p.chromium.launch(headless=True)
                try:
                    page=b.new_page()
                    response=page.goto(url,wait_until='networkidle',timeout=45000)
                    if response and response.status >= 400:
                        raise RuntimeError(f'HTTP {response.status}')
                    html=page.content()
                    final=page.url
                    status=response.status if response else None
                finally:
                    b.close()
        else:
            with httpx.Client(follow_redirects=True,timeout=30,headers={'User-Agent':'FacultyAtlas/0.1 (public academic research)'}) as client:
                response=client.get(url)
                response.raise_for_status()
                if 'html' not in response.headers.get('content-type','').lower():
                    raise ValueError('Expected HTML; use source-add for extracted documents')
                html=response.text
                final=str(response.url)
                status=response.status_code
        text=extract(html)
        if len(text)<100 or any(s in text.lower() for s in ['just a moment...','enable javascript and cookies to continue','verify you are human']):
            raise ValueError('Empty page or access challenge; inspect in browser')
        return store_source(con,root,url=url,final_url=final,text=text,html=html,fetch_method=method,http_status=status)
    except Exception as e:
        return store_source(con,root,url=url,state='failed',fetch_method=method,error=str(e),
                            http_status=getattr(getattr(e,'response',None),'status_code',None))

def discover(con,root,sid):
    row=con.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
    if not row or row['state']!='ok' or not row['html_path']:
        raise ValueError('Discovery needs a successful HTML snapshot; use seed-import for extracted directory records')
    soup=BeautifulSoup((root / row['html_path']).read_text(),'html.parser')
    # Only the main Academic Staff block; do not silently include honorary/adjunct staff.
    heading=next((h for h in soup.find_all(re.compile('^h[1-6]$')) if h.get_text(strip=True)=='Academic Staff'),None)
    if heading is None:
        raise ValueError('Academic Staff heading not found: inspect directory layout')
    records=[]
    active=False
    for node in heading.find_all_next(re.compile('^h[1-6]$')):
        label=node.get_text(' ',strip=True)
        if re.search(r'Honorary|Part-time|Postdoctoral|Senior Research',label,re.I):
            break
        anchor=node.find('a',href=True)
        if anchor:
            active={'name':label,'profile_url':urljoin(row['final_url'],anchor['href'])}
        elif active and 'professor' in label.lower():
            if not re.search(r'honorary|adjunct|emeritus',label,re.I):
                records.append({**active,'title':label})
            active=False
        elif active and re.search(r'lecturer|instructor',label,re.I):
            active=False
    if not records:
        raise ValueError('No faculty parsed; inspect saved HTML before importing')
    for record in records:
        add_professor(con,source_id=sid,**record)
    return records

def collect(con,root,*,limit=None,refresh=False,browser=False):
    """Bounded traversal: directory -> profile -> homepage/recruitment links; no open-ended crawling."""
    rows=con.execute('SELECT * FROM professors ORDER BY id').fetchall()
    results=[]
    for person in rows[:limit] if limit else rows:
        sid=fetch(con,root,person['identity_url'],refresh=refresh,browser=browser)
        con.execute('INSERT OR IGNORE INTO professor_sources VALUES(?,?,?)',(person['id'],sid,'profile'))
        con.commit()
        source=con.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        candidates=[]
        if source['state']=='ok' and source['html_path']:
            html=(root/source['html_path']).read_text()
            candidates=[l for l in links(html,source['final_url'])
                        if re.search(r'home\s?page|personal\s+(web|page)|recruit|opening|join.*(lab|group)',l['text'],re.I)]
            for link in candidates[:4]:
                time.sleep(0.5)
                child=fetch(con,root,link['url'],refresh=refresh,browser=browser)
                con.execute('INSERT OR IGNORE INTO professor_sources VALUES(?,?,?)',(person['id'],child,'homepage_candidate'))
                con.commit()
        results.append({'professor_id':person['id'],'name':person['name'],'source_id':sid,'state':source['state'],'links':candidates})
        print(f"{person['id']}: {person['name']}: {source['state']}",flush=True)
        time.sleep(0.5)
    dump_json(root/'collection-log.json',results)
    return results

def prepare(con,root,destination):
    from .review import Review
    from .records import detail
    root=root.resolve()
    destination.mkdir(parents=True,exist_ok=True)
    dump_json(destination/'review-schema.json',Review.model_json_schema())
    for p in con.execute('SELECT * FROM professors ORDER BY id').fetchall():
        pages=[dict(s) for s in con.execute('''SELECT DISTINCT s.* FROM sources s JOIN professor_sources ps ON s.id=ps.source_id
                     WHERE ps.professor_id=? ORDER BY s.id''',(p['id'],))]
        for s in pages:
            s['text']=(root/s['text_path']).read_text() if s['text_path'] else None
            if s['html_path']:
                s['links']=links((root/s['html_path']).read_text(),s['final_url'])
            s['local_text_path']=str(root/s['text_path']) if s['text_path'] else None
            s['local_html_path']=str(root/s['html_path']) if s['html_path'] else None
        dump_json(destination/f"{p['id']:03d}.json",{'professor':dict(p),'data_root':str(root),
            'current_assessment':detail(con,p['id']),'sources':pages,
            'instructions':'Use skills/review-faculty/SKILL.md. Return format_version=2 Review JSON. Prefer the downloaded text/HTML and links in this packet; no network is needed for saved successful sources. Preserve original wording in source interests; write interpretations only in interests_ai and research_matches. Cite exact snapshot quotes and verified homepage URLs, including HKU-hosted personal pages. Unknown=0 only after reading successful sources. Failed material pages require partial review. Keep each area.other and raw_topic. Do not age-filter faculty.'})
