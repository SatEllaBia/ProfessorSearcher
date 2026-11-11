"""Local web interface adapting PhD Scout's directory and application workflow.

All routes use Atlas's single SQLite database; there is no parallel Scout DB or
paid model client. Run on loopback and make network collection an explicit action.
"""
import json
import logging
import re
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from .db import connect
from . import records

_discovery_lock=threading.Lock()
_log=logging.getLogger(__name__)

class ThreadingHTTPServer(socketserver.ThreadingMixIn,HTTPServer):
    daemon_threads=True

class Handler(BaseHTTPRequestHandler):
    def do_GET(self): self.dispatch('GET')
    def do_POST(self): self.dispatch('POST')
    def do_PUT(self): self.dispatch('PUT')
    def do_DELETE(self): self.dispatch('DELETE')

    def dispatch(self,method):
        parsed=urlparse(self.path);path=parsed.path
        params={k:v[0] for k,v in parse_qs(parsed.query).items()}
        con=None
        try:
            if method!='GET':
                origin=self.headers.get('Origin')
                if origin and urlparse(origin).netloc!=self.headers.get('Host'):
                    return self.respond({'error':'Cross-origin writes are not allowed'},403)
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    return self.respond({'error':'Use application/json'},415)
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=1_000_000:
                    return self.respond({'error':'Body must be 1 byte to 1 MB'},413)
                body=json.loads(self.rfile.read(length))
            root=self.server.data_root
            con=connect(root)
            if path=='/' and method=='GET':
                return self.respond((Path(__file__).parent/'static/index.html').read_bytes(),content_type='text/html; charset=utf-8')
            if path=='/static/scout.css' and method=='GET':
                return self.respond((Path(__file__).parent/'static/scout.css').read_bytes(),content_type='text/css; charset=utf-8')
            if path=='/api/review-schema' and method=='GET':
                from .review import Review
                return self.respond(Review.model_json_schema())
            if path=='/api/professors' and method=='GET':
                degree=params.get('degree') or None
                if degree not in (None,'PhD','MPhil'):raise ValueError('Unknown degree')
                status=int(params['status']) if params.get('status') else None
                if status not in (None,-1,0,1,2):raise ValueError('Unknown recruitment status')
                if status is not None and not degree:raise ValueError('Status filtering requires a degree')
                rows=records.directory(con,q=params.get('q',''),area=params.get('area') or None,
                    degree=degree,status=status,min_fit=int(params.get('min_fit',0)),exclude=params.get('exclude',''))
                if params.get('semantic','').strip():
                    from .semantic import rank
                    rows=rank(con,root,rows,params['semantic'])
                return self.respond(rows)
            m=re.fullmatch(r'/api/professors/(\d+)',path)
            if m and method=='GET':return self.respond(records.detail(con,int(m[1])))
            if path=='/api/status' and method=='GET':
                return self.respond({'professors':con.execute('SELECT count(*) FROM professors').fetchone()[0],
                    'reviews':con.execute('SELECT count(*) FROM reviews').fetchone()[0],
                    'shortlisted':con.execute('SELECT count(*) FROM application_list').fetchone()[0],
                    'sources':con.execute('SELECT count(*) FROM sources').fetchone()[0],
                    'schema_version':con.execute('SELECT max(version) FROM schema_version').fetchone()[0]})
            if path=='/api/apply' and method=='GET':
                return self.respond(sorted([r for r in records.directory(con) if r['application_rank'] is not None],key=lambda r:r['application_rank']))
            if path=='/api/apply' and method in ('POST','PUT'):
                records.save_application(con,int(body['professor_id']),body.get('notes'))
                return self.respond({'ok':True})
            if path=='/api/apply/order' and method=='PUT':
                records.reorder_applications(con,body['ids']);return self.respond({'ok':True})
            m=re.fullmatch(r'/api/apply/(\d+)',path)
            if m and method=='DELETE':
                with con:con.execute('DELETE FROM application_list WHERE professor_id=?',(int(m[1]),))
                return self.respond({'ok':True})
            if path=='/api/interests/source' and method=='POST':
                sid=records.source_interest(con,root,int(body['professor_id']),int(body['source_id']),body['text'],'manual')
                return self.respond({'id':sid})
            if path=='/api/reviews/import' and method=='POST':
                from .review import import_review
                return self.respond({'review_id':import_review(con,root,body)})
            if path=='/api/prepare' and method=='POST':
                from .collect import prepare
                destination=root/'review-packets';prepare(con,root,destination)
                return self.respond({'path':str(destination.resolve()),'count':con.execute('SELECT count(*) FROM professors').fetchone()[0]})
            if path=='/api/csrankings' and method=='POST':
                from .discovery import search
                with _discovery_lock:rows=search(root,body.get('filters',{}),bool(body.get('refresh',False)))
                return self.respond(rows)
            if path=='/api/csrankings/import' and method=='POST':
                from .discovery import import_candidates
                if not isinstance(body,list):raise ValueError('Expected an array of candidates')
                return self.respond({'professor_ids':import_candidates(con,root,body)})
            m=re.fullmatch(r'/api/sources/(\d+)/(text|html)',path)
            if m and method=='GET':
                source=con.execute('SELECT * FROM sources WHERE id=?',(int(m[1]),)).fetchone()
                if not source or not source[f'{m[2]}_path']:return self.respond({'error':'No saved snapshot'},404)
                file=(root/source[f'{m[2]}_path']).resolve()
                if not file.is_relative_to(root.resolve()):raise ValueError('Invalid snapshot path')
                # Serve saved HTML as literal text so source scripts cannot execute.
                return self.respond(file.read_bytes(),content_type='text/plain; charset=utf-8')
            return self.respond({'error':'Not found'},404)
        except (ValueError,KeyError,TypeError) as exc:
            return self.respond({'error':str(exc)},400)
        except RuntimeError as exc:
            return self.respond({'error':str(exc)},503)
        except Exception:
            _log.exception('Request failed')
            return self.respond({'error':'Request failed; see server log'},500)
        finally:
            if con is not None:con.close()

    def respond(self,value,status=200,content_type='application/json; charset=utf-8'):
        body=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(body)

    def log_message(self,*args):pass

def make_server(root,port=8080):
    root=Path(root).resolve()
    con=connect(root);con.close()
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.data_root=root
    return server

def run(root,port=8080):
    server=make_server(root,port)
    print(f'Faculty Atlas: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
