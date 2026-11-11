from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

TOPICS = {
    'agents': ['llm_agents','tool_use','planning','multi_agent','embodied_agents','other'],
    'generation': ['image_generation','video_generation','3d_generation','motion_generation','other'],
    'ai_graphics': ['neural_rendering','learned_animation','generative_graphics','other'],
    'other': ['other'],
}

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def connect(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / 'faculty.sqlite')
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.executescript(Path(__file__).with_name('schema.sql').read_text())
    from .migrations import migrate
    migrate(con)
    con.executemany('INSERT OR IGNORE INTO topics VALUES(?,?)',
                    [(a,t) for a,ts in TOPICS.items() for t in ts])
    con.commit()
    return con

def store_source(con, root, *, url, text='', html=None, final_url=None,
                 fetch_method='manual', http_status=None, state='ok', error=None,
                 fetched_at=None, published_at=None):
    """Snapshots are immutable and failed retrievals never count as checked evidence."""
    digest = hashlib.sha256((html if html is not None else text).encode()).hexdigest() if state == 'ok' else None
    if digest:
        row = con.execute('SELECT id FROM sources WHERE url=? AND content_hash=? AND fetch_method=?',
                          (url,digest,fetch_method)).fetchone()
        if row:
            return row['id']
    base = Path('snapshots') / (hashlib.sha256(url.encode()).hexdigest()[:12] + '-' + (digest[:16] if digest else hashlib.sha256(now().encode()).hexdigest()[:16]))
    (root / base).parent.mkdir(parents=True,exist_ok=True)
    html_path = str(base.with_suffix('.html')) if html is not None else None
    text_path = str(base.with_suffix('.txt')) if state == 'ok' else None
    if html_path:
        (root / html_path).write_text(html,encoding='utf-8')
    if text_path:
        (root / text_path).write_text(text,encoding='utf-8')
    cur = con.execute('''INSERT INTO sources(url,final_url,fetched_at,published_at,http_status,fetch_method,state,
                        content_hash,html_path,text_path,error) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                      (url,final_url or url,fetched_at or now(),published_at,http_status,fetch_method,state,
                       digest,html_path,text_path,error))
    con.commit()
    return cur.lastrowid

def add_professor(con, *, name, title, profile_url, source_id, university='HKU',
                  department='AI & Data Science', school='School of Computing and Data Science'):
    con.execute('INSERT INTO professors(name,identity_url) VALUES(?,?) ON CONFLICT(identity_url) DO UPDATE SET name=excluded.name',
                (name,profile_url))
    pid=con.execute('SELECT id FROM professors WHERE identity_url=?',(profile_url,)).fetchone()[0]
    con.execute('''INSERT INTO affiliations(professor_id,university,school,department,title,official_profile_url,source_id)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(professor_id,university,department) DO UPDATE SET
                   title=excluded.title,source_id=excluded.source_id''',
                (pid,university,school,department,title,profile_url,source_id))
    con.execute('INSERT OR IGNORE INTO professor_sources VALUES(?,?,?)',(pid,source_id,'directory'))
    con.commit()
    return pid

def dump_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
