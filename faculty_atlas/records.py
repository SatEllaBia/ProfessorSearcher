"""Shared query and mutation layer for CLI, browser UI and offline reviewers."""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from .review import norm
from .report import degree_summary


def normalized_url(url):
    parts=urlsplit(url or '')
    host=parts.netloc.lower().removeprefix('www.')
    path=parts.path.replace('/index.php/','/').rstrip('/')
    return urlunsplit((parts.scheme.lower(),host,path,parts.query,''))


def source_interest(con,root,professor_id,source_id,text,method='manual'):
    if method not in ('parser','manual','verbatim_selection','legacy_quote'):
        raise ValueError('Unknown source-interest selection method')
    if not con.execute('SELECT 1 FROM professors WHERE id=?',(professor_id,)).fetchone():
        raise ValueError('Unknown professor')
    source=con.execute('SELECT * FROM sources WHERE id=?',(source_id,)).fetchone()
    if not source or source['state']!='ok' or not source['text_path']:
        raise ValueError('Source interests require a successful saved text snapshot')
    if not text.strip() or norm(text) not in norm((root/source['text_path']).read_text()):
        raise ValueError('Source interests must be copied verbatim from the snapshot')
    with con:
        con.execute('INSERT OR IGNORE INTO source_interests(professor_id,source_id,text,method) VALUES(?,?,?,?)',
            (professor_id,source_id,text,method))
        con.execute('INSERT OR IGNORE INTO professor_sources VALUES(?,?,?)',(professor_id,source_id,'interests'))
    return con.execute('SELECT id FROM source_interests WHERE professor_id=? AND source_id=? AND text=?',
        (professor_id,source_id,text)).fetchone()[0]


def directory(con,*,q='',area=None,degree=None,status=None,min_fit=0,exclude=''):
    rows=[]
    for p in con.execute('''SELECT p.*,r.id review_id,r.interests_ai,r.reviewed_at,
        al.rank application_rank,al.notes application_notes FROM professors p
        LEFT JOIN current_reviews r ON r.professor_id=p.id
        LEFT JOIN application_list al ON al.professor_id=p.id ORDER BY p.name''').fetchall():
        item=dict(p)
        item['affiliations']=[dict(a) for a in con.execute('SELECT * FROM affiliations WHERE professor_id=?',(p['id'],))]
        item['interests_source']=[dict(s) for s in con.execute('''SELECT i.*,s.url,s.fetched_at FROM source_interests i
            JOIN sources s ON s.id=i.source_id WHERE i.professor_id=? ORDER BY i.id''',(p['id'],))]
        item['research_matches']=[dict(m) for m in con.execute('SELECT * FROM research_matches WHERE review_id=?',(p['review_id'],))]
        item['homepages']=[dict(h) for h in con.execute('SELECT * FROM homepage_findings WHERE review_id=?',(p['review_id'],))]
        item['homepage_evidence_state']='reviewed' if any(h['url']==p['homepage_url'] for h in item['homepages']) else 'legacy_unverified' if p['homepage_url'] else 'unknown'
        item['PhD']=degree_summary(con,p['review_id'],'PhD')
        item['MPhil']=degree_summary(con,p['review_id'],'MPhil')
        search=' '.join([p['name'],p['email'] or '',p['interests_ai'] or '',
            ' '.join(s['text'] for s in item['interests_source']),
            ' '.join(a['department']+' '+a['university'] for a in item['affiliations'])]).casefold()
        if q and q.casefold() not in search:
            continue
        if exclude and exclude.casefold() in search:
            continue
        if area and not any(m['area']==area and m['match_strength']>=min_fit for m in item['research_matches']):
            continue
        if degree and status is not None:
            states={r[0] for r in con.execute("SELECT status FROM recruitment_signals WHERE review_id=? AND degree=? AND temporal_state<>'past' AND status<>0",(p['review_id'],degree))}
            if p['review_id'] is None or states!=({status} if status else set()):
                continue
        rows.append(item)
    return rows


def detail(con,pid):
    row=next((p for p in directory(con) if p['id']==pid),None)
    if row is None:
        raise ValueError('Unknown professor')
    row['recruitment_signals']=[dict(r) for r in con.execute('SELECT * FROM recruitment_signals WHERE review_id=?',(row['review_id'],))]
    row['interest_evidence']=[dict(r) for r in con.execute('SELECT * FROM interest_evidence WHERE review_id=?',(row['review_id'],))]
    row['sources']=[dict(r) for r in con.execute('''SELECT DISTINCT s.* FROM sources s JOIN professor_sources ps
        ON s.id=ps.source_id WHERE ps.professor_id=? ORDER BY s.id DESC''',(pid,))]
    row['review_history']=[dict(r) for r in con.execute('SELECT id,reviewed_at,state,notes,interests_ai FROM reviews WHERE professor_id=? ORDER BY id DESC',(pid,))]
    return row


def save_application(con,pid,notes=None):
    if not con.execute('SELECT 1 FROM professors WHERE id=?',(pid,)).fetchone():
        raise ValueError('Unknown professor')
    with con:
        rank=con.execute('SELECT COALESCE(max(rank)+1,0) FROM application_list').fetchone()[0]
        con.execute('INSERT OR IGNORE INTO application_list(professor_id,rank) VALUES(?,?)',(pid,rank))
        if notes is not None:
            con.execute('UPDATE application_list SET notes=? WHERE professor_id=?',(notes,pid))


def reorder_applications(con,ids):
    existing={r[0] for r in con.execute('SELECT professor_id FROM application_list')}
    if len(set(ids))!=len(ids) or set(ids)!=existing:
        raise ValueError('Order must contain every shortlisted professor exactly once')
    with con:
        con.executemany('UPDATE application_list SET rank=? WHERE professor_id=?',enumerate(ids))
