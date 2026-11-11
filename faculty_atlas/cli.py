from __future__ import annotations
import argparse
import json
from pathlib import Path
from .collect import DIRECTORY,collect,discover,extract,fetch,prepare
from .db import add_professor,connect,store_source
from .report import export
from .review import import_review
from .query import shortlist

def main():
    p=argparse.ArgumentParser(description='Evidence-backed faculty collection and review')
    p.add_argument('--data',type=Path,default=Path('data'))
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    sub.add_parser('status')
    s=sub.add_parser('list');s.add_argument('--area',choices=['agents','generation','ai_graphics','other']);s.add_argument('--min-fit',type=int,choices=range(4),default=2);s.add_argument('--degree',choices=['PhD','MPhil']);s.add_argument('--status',type=int,choices=[-1,0,1,2])
    s=sub.add_parser('fetch');s.add_argument('url');s.add_argument('--refresh',action='store_true');s.add_argument('--browser',action='store_true')
    s=sub.add_parser('source-add');s.add_argument('file',type=Path);s.add_argument('--url',required=True);s.add_argument('--html',action='store_true');s.add_argument('--method',choices=['manual','web_extract'],default='manual')
    s=sub.add_parser('source-import');s.add_argument('file',type=Path,help='JSON source snapshots with text and optional html')
    s=sub.add_parser('seed-import');s.add_argument('file',type=Path,help='JSON array with name,title,profile_url,source_id')
    s=sub.add_parser('discover');s.add_argument('--source',type=int);s.add_argument('--browser',action='store_true')
    s=sub.add_parser('collect');s.add_argument('--limit',type=int);s.add_argument('--refresh',action='store_true');s.add_argument('--browser',action='store_true')
    s=sub.add_parser('prepare');s.add_argument('--out',type=Path,default=Path('work/batches'))
    s=sub.add_parser('review-import');s.add_argument('file',type=Path)
    s=sub.add_parser('export');s.add_argument('--out',type=Path,default=Path('reports/hku-ai.md'))
    s=sub.add_parser('serve');s.add_argument('--port',type=int,default=8080)
    s=sub.add_parser('interests-add');s.add_argument('professor_id',type=int);s.add_argument('--source',type=int,required=True);s.add_argument('--text',required=True)
    s=sub.add_parser('discovery');s.add_argument('--country',default='hk');s.add_argument('--query',default='University of Hong Kong');s.add_argument('--refresh',action='store_true');s.add_argument('--out',type=Path,default=Path('work/discovery.json'))
    s=sub.add_parser('discovery-import');s.add_argument('file',type=Path)
    s=sub.add_parser('review-schema');s.add_argument('--out',type=Path,default=Path('work/review-schema.json'))
    s=sub.add_parser('source-link');s.add_argument('professor_id',type=int);s.add_argument('source_id',type=int);s.add_argument('--role',default='review_candidate')
    args=p.parse_args()
    if args.command=='list' and args.status is not None and args.degree is None:
        p.error('--status requires --degree')
    if args.command=='serve':
        from .serve import run
        run(args.data,args.port);return
    con=connect(args.data)
    try:
        if args.command=='init': print(args.data/'faculty.sqlite')
        elif args.command=='list':
            print(json.dumps(shortlist(con,area=args.area,min_fit=args.min_fit,degree=args.degree,status=args.status),indent=2,ensure_ascii=False))
        elif args.command=='status':
            print(json.dumps({'professors':con.execute('SELECT count(*) FROM professors').fetchone()[0],
                              'states':[dict(r) for r in con.execute('SELECT review_state,count(*) count FROM professors GROUP BY review_state')],
                              'sources':[dict(r) for r in con.execute('SELECT fetch_method,state,count(*) count FROM sources GROUP BY fetch_method,state')],
                              'integrity':con.execute('PRAGMA integrity_check').fetchone()[0],
                              'foreign_key_errors':[tuple(r) for r in con.execute('PRAGMA foreign_key_check')]},indent=2))
        elif args.command=='fetch': print(fetch(con,args.data,args.url,refresh=args.refresh,browser=args.browser))
        elif args.command=='source-add':
            content=args.file.read_text(encoding='utf-8')
            print(store_source(con,args.data,url=args.url,text=extract(content) if args.html else content,html=content if args.html else None,fetch_method=args.method))
        elif args.command=='source-import':
            for source in json.loads(args.file.read_text()):
                print(source['url'],store_source(con,args.data,**source))
        elif args.command=='seed-import':
            for record in json.loads(args.file.read_text()):
                print(add_professor(con,**record))
        elif args.command=='discover':
            sid=args.source or fetch(con,args.data,DIRECTORY,browser=args.browser)
            print(json.dumps(discover(con,args.data,sid),indent=2))
        elif args.command=='collect': collect(con,args.data,limit=args.limit,refresh=args.refresh,browser=args.browser)
        elif args.command=='prepare': prepare(con,args.data,args.out);print(args.out)
        elif args.command=='review-import':
            payload=json.loads(args.file.read_text())
            for review in payload if isinstance(payload,list) else [payload]:
                print(import_review(con,args.data,review))
        elif args.command=='export': export(con,args.out);print(args.out)
        elif args.command=='interests-add':
            from .records import source_interest
            print(source_interest(con,args.data,args.professor_id,args.source,args.text))
        elif args.command=='discovery':
            from .discovery import search
            from .db import dump_json
            dump_json(args.out,search(args.data,{'country':args.country,'q':args.query},args.refresh));print(args.out)
        elif args.command=='discovery-import':
            from .discovery import import_candidates
            print(import_candidates(con,args.data,json.loads(args.file.read_text())))
        elif args.command=='review-schema':
            from .db import dump_json
            from .review import Review
            dump_json(args.out,Review.model_json_schema());print(args.out)
        elif args.command=='source-link':
            with con:
                con.execute('INSERT OR IGNORE INTO professor_sources VALUES(?,?,?)',(args.professor_id,args.source_id,args.role))
            print(args.source_id)
    finally:
        con.close()

if __name__=='__main__':main()
