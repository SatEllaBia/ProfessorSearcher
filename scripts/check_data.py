"""Validate snapshot integrity, stored review references and evidence, without network."""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from faculty_atlas.db import connect
from faculty_atlas.review import Review,norm

root=Path(sys.argv[1]) if len(sys.argv)>1 else Path('data')
con=connect(root)
assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
assert not con.execute('PRAGMA foreign_key_check').fetchall()
for s in con.execute("SELECT * FROM sources WHERE state='ok'"):
    path=root/(s['html_path'] or s['text_path'])
    assert hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest()==s['content_hash'],s['id']
for p in con.execute('SELECT id FROM professors'):
    review=con.execute('SELECT id FROM current_reviews WHERE professor_id=?',(p['id'],)).fetchone()
    assert review,f"Pending professor {p['id']}"
    degrees={r[0] for r in con.execute('SELECT degree FROM recruitment_signals WHERE review_id=?',(review['id'],))}
    assert {'PhD','MPhil'}<=degrees
for table in ['research_matches','recruitment_signals','interest_evidence','homepage_findings']:
    for r in con.execute(f'SELECT r.*,s.text_path,s.state FROM {table} r JOIN sources s ON s.id=r.source_id'):
        assert r['state']=='ok'
        assert norm(r['evidence_quote']) in norm((root/r['text_path']).read_text())
        assert con.execute('SELECT 1 FROM review_sources WHERE review_id=? AND source_id=?',(r['review_id'],r['source_id'])).fetchone()
for r in con.execute('SELECT i.*,s.text_path,s.state FROM source_interests i JOIN sources s ON s.id=i.source_id'):
    assert r['state']=='ok'
    assert norm(r['text']) in norm((root/r['text_path']).read_text())
for r in con.execute("SELECT id FROM reviews WHERE length(trim(interests_ai))>0"):
    assert con.execute('SELECT 1 FROM interest_evidence WHERE review_id=?',(r['id'],)).fetchone()
for review in json.loads((root/'reviews/hku-ai-first-pass.json').read_text()):Review.model_validate(review)
for file in (root/'reviews').glob('*v2*.json'):
    for review in json.loads(file.read_text()):Review.model_validate(review)
print('Database, foreign keys, snapshot hashes, degree coverage, original interests, AI/homepage evidence: OK')
con.close()
