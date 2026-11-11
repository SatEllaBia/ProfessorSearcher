"""PhD Scout discovery with a durable CSV cache and exact-identity deduplication."""
import hashlib
import json
from pathlib import Path
from .db import add_professor, store_source
from .records import normalized_url
from .scout import csrankings_fetcher as scout

def search(root,filters,refresh=False):
    cache=root/'discovery-cache'
    cache.mkdir(parents=True,exist_ok=True)
    # Keep immutable source snapshots in addition to Scout's process-local TTL.
    original=scout._fetch_url
    def cached(url):
        path=cache/(hashlib.sha256(url.encode()).hexdigest()+'.csv')
        if path.exists() and not refresh:
            return path.read_text()
        text=original(url)
        path.write_text(text,encoding='utf-8')
        return text
    # Caller serializes this global adapter with a lock in the server.
    scout._fetch_url=cached
    try:
        scout._cache.clear()
        rows=scout.fetch_csrankings(filters)
    finally:
        scout._fetch_url=original
    groups={}
    for r in rows:
        scholar=r.get('scholar_url')
        if scholar and 'NOSCHOLARPAGE' in scholar:
            r['scholar_url']=scholar=None
        home=normalized_url(r.get('homepage_url'))
        key=(r['university'],home or scholar or r['name'].casefold())
        if key in groups:
            groups[key]['aliases'].append(r['name'])
        else:
            groups[key]={**r,'aliases':[]}
    result=list(groups.values())
    (cache/'last-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result

def import_candidates(con,root,rows):
    imported=[]
    known={}
    for p in con.execute('SELECT id,identity_url,homepage_url FROM professors'):
        for url in (p['identity_url'],p['homepage_url']):
            if url: known[normalized_url(url)]=p['id']
    for a in con.execute('SELECT professor_id,official_profile_url FROM affiliations'):
        if a['official_profile_url']:known[normalized_url(a['official_profile_url'])]=a['professor_id']
    for row in rows:
        name=row.get('name','').strip();university=row.get('university','').strip()
        url=row.get('homepage_url')
        if not name or not university or not url or not url.startswith(('https://','http://')):
            raise ValueError('Each candidate requires name, university and a public http(s) homepage URL')
        scholar=row.get('scholar_url')
        existing=known.get(normalized_url(url))
        if scholar and 'NOSCHOLARPAGE' not in scholar:
            found=con.execute("SELECT professor_id FROM external_ids WHERE scheme='scholar' AND value=?",(scholar,)).fetchone()
            if found:
                if existing is not None and existing!=found[0]:
                    raise ValueError('Conflicting homepage and scholar identities; review before importing')
                existing=found[0]
        sid=store_source(con,root,url=scout._URLS['faculty'],text=json.dumps(row,ensure_ascii=False,sort_keys=True),fetch_method='manual')
        if existing is None:
            existing=add_professor(con,name=name,title='Not provided by CSRankings',profile_url=url,
                source_id=sid,university=university,school=None,department='Not provided by CSRankings')
            # CSRankings supplies a homepage, not proof of an official department profile.
            con.execute("UPDATE affiliations SET official_profile_url='' WHERE professor_id=?",(existing,))
            con.execute('UPDATE professors SET homepage_url=? WHERE id=?',(url,existing))
        con.execute('INSERT OR IGNORE INTO professor_sources VALUES(?,?,?)',(existing,sid,'directory'))
        if scholar and 'NOSCHOLARPAGE' not in scholar:
            con.execute("INSERT OR IGNORE INTO external_ids VALUES('scholar',?,?)",(scholar,existing))
        areas=row.get('areas')
        if areas:
            con.execute("INSERT OR IGNORE INTO source_interests(professor_id,source_id,text,method) VALUES(?,?,?,'parser')",(existing,sid,areas))
        con.commit()
        known[normalized_url(url)]=existing
        imported.append(existing)
    return list(dict.fromkeys(imported))
