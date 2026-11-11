"""Import saved web-retrieval results. Extracted text is never mislabeled as raw HTML.

Used for this collection because host DNS is unavailable. Ordinary recollection uses
`faculty collect`; this adapter keeps retrieved evidence reproducible offline.
"""
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from faculty_atlas.db import connect,store_source,add_professor,dump_json

def clean(raw):
    lines=re.findall(r'^L\d+: ?(.*)$',raw,re.M)
    text='\n'.join(lines) if lines else raw
    return re.sub(r'【\d+†([^†】]+)(?:†[^】]+)?】',r'\1',text)

def ingest(path,root=Path('data'),profile=False):
    con=connect(root)
    directory=con.execute('SELECT * FROM sources WHERE url=? ORDER BY id LIMIT 1',('https://ai.hku.hk/people/academic-staff',)).fetchone()
    directory_text=(root/directory['text_path']).read_text()
    metadata={}
    for m in re.finditer(r'#### 【(\d+)†([^†】]+)(?:†[^】]+)?】(.*?)(?=L\d+: #### 【|L\d+: # Honorary|\Z)',directory_text,re.S):
        title=re.search(r'#### ([^\n]*[Pp]rofessor[^\n]*)',m[3])
        if title:metadata[int(m[1])]={'name':m[2],'title':title[1].replace('Assistant Professors','Assistant Professor')}
    index=[]
    for record in json.loads(path.read_text()):
        if 'error' in record:
            print('ERROR',record);continue
        result=record['result']
        raw='\n'.join(c['text'] for c in result['content'] if c['type']=='text')
        url=re.search(r'^.*?\((https?://[^\n)]+)\)',raw)
        if not url:
            failed_url=re.search(r'(?:URL |fetch )(https?://[^\s]+)',raw)
            if failed_url:
                sid=store_source(con,root,url=failed_url[1].rstrip(':;'),state='failed',fetch_method='web_extract',error=raw)
                index.append({'key':record['key'],'source_id':sid,'url':failed_url[1].rstrip(':;'),'failed':True})
            else:
                print('ERROR no URL',record['key'],raw[:200])
            continue
        url=url[1].split(' ; ')[0]
        final_match=re.search(r'Redirected to URL: (https?://[^;\s]+)',raw)
        final=final_match[1] if final_match else url
        text=clean(raw)
        if not re.findall(r'^L\d+: ?\S',raw,re.M):
            sid=store_source(con,root,url=url,state='failed',fetch_method='web_extract',error='No usable page text returned')
            index.append({'key':record['key'],'source_id':sid,'url':url,'failed':True})
            continue
        sid=store_source(con,root,url=url,final_url=final,text=text,fetch_method='web_extract')
        ref=re.search(r'【(turn\d+\w+\d+)】',raw)
        item={'key':record['key'],'source_id':sid,'url':url,'ref':ref[1] if ref else None}
        if profile:
            meta=metadata[record['key']]
            pid=add_professor(con,source_id=directory['id'],profile_url=url,**meta)
            con.execute('INSERT OR IGNORE INTO professor_sources VALUES(?,?,?)',(pid,sid,'profile'))
            con.commit()
            item.update(meta,professor_id=pid)
            home=re.search(r'(?:Hom[e]?page|Web|Personal Page):\s*(?:【\d+†)?(https?://[^\s†】]+)',raw,re.I)
            item['homepage_url']=home[1] if home else None
        index.append(item)
    con.close()
    return index

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('files',nargs='+',type=Path);p.add_argument('--profiles',action='store_true');p.add_argument('--out',type=Path,default=Path('data/import-index.json'))
    args=p.parse_args();items=[]
    for path in args.files:items.extend(ingest(path,profile=args.profiles))
    dump_json(args.out,items)
    print(json.dumps(items,indent=2,ensure_ascii=False))
