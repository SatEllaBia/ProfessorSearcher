import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from faculty_atlas.db import connect,add_professor,store_source
from faculty_atlas.review import import_review
from faculty_atlas.records import source_interest,detail,save_application,reorder_applications
from faculty_atlas.collect import prepare
from faculty_atlas import discovery
from faculty_atlas.serve import make_server

class CombinedTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.con=connect(self.root)
        self.sid=store_source(self.con,self.root,url='https://example.edu/people/a',
            text='Professor A. Personal homepage. AI for accelerating smoke simulation. I welcome PhD students.',
            html='<p>Professor A. <a href="/~a/">Personal homepage</a>. AI for accelerating smoke simulation. I welcome PhD students.</p>')
        self.pid=add_professor(self.con,name='A',title='Assistant Professor',profile_url='https://example.edu/people/a',source_id=self.sid)
        self.payload={'format_version':2,'professor_id':self.pid,'review_state':'reviewed',
            'checked_source_ids':[self.sid],'profile_source_id':self.sid,'homepage_url':'https://example.edu/~a/',
            'homepages':[{'url':'https://example.edu/~a/','kind':'personal','source_id':self.sid,'evidence_quote':'Personal homepage','reasoning':'Linked by the identified institutional profile.'}],
            'interests_source':[{'source_id':self.sid,'evidence_quote':'AI for accelerating smoke simulation.'}],
            'interests_ai':'Uses learned methods to accelerate simulation.',
            'interest_evidence':[{'source_id':self.sid,'evidence_quote':'AI for accelerating smoke simulation.'}],
            'recruitment_signals':[{'degree':'PhD','status':2,'source_id':self.sid,'evidence_quote':'I welcome PhD students.','reasoning':'Explicit undated invitation.'},
                {'degree':'MPhil','status':0,'source_id':self.sid,'reasoning':'No MPhil statement.'}],
            'research_matches':[{'area':'ai_graphics','topic':'other','raw_topic':'AI-accelerated smoke simulation','match_strength':3,'source_id':self.sid,'evidence_quote':'AI for accelerating smoke simulation.','reasoning':'AI simulation rather than traditional graphics.'}]}
    def tearDown(self):
        self.con.close();self.tmp.cleanup()
    def test_source_and_ai_interests_are_separate(self):
        import_review(self.con,self.root,self.payload)
        p=detail(self.con,self.pid)
        self.assertEqual(p['interests_source'][0]['text'],'AI for accelerating smoke simulation.')
        self.assertEqual(p['interests_ai'],'Uses learned methods to accelerate simulation.')
        self.assertNotIn(p['interests_ai'],p['interests_source'][0]['text'])
        with self.assertRaises(ValueError):source_interest(self.con,self.root,self.pid,self.sid,'A paraphrase instead of the original wording')
    def test_ai_interpretation_needs_checked_evidence(self):
        self.payload['interest_evidence']=[]
        with self.assertRaises(ValueError):import_review(self.con,self.root,self.payload)
        self.assertEqual(self.con.execute('SELECT count(*) FROM reviews').fetchone()[0],0)
    def test_institution_hosted_personal_homepage_keeps_kind(self):
        import_review(self.con,self.root,self.payload)
        p=detail(self.con,self.pid)
        self.assertEqual(p['homepages'][0]['kind'],'personal')
        self.assertEqual(p['homepage_evidence_state'],'reviewed')
    def test_invented_homepage_rejected_atomically(self):
        self.payload['homepages'][0]['url']=self.payload['homepage_url']='https://example.edu/~invented/'
        with self.assertRaises(ValueError):import_review(self.con,self.root,self.payload)
        self.assertEqual(self.con.execute('SELECT count(*) FROM source_interests').fetchone()[0],0)
    def test_migration_and_old_payload_remain_idempotent(self):
        legacy=dict(self.payload)
        for key in ['format_version','homepages','interests_source','interests_ai','interest_evidence']:legacy.pop(key)
        rid=import_review(self.con,self.root,legacy)
        self.con.close();self.con=connect(self.root)
        self.assertEqual(import_review(self.con,self.root,legacy),rid)
        self.assertEqual(self.con.execute('SELECT max(version) FROM schema_version').fetchone()[0],2)
    def test_packet_contains_absolute_offline_sources_and_schema(self):
        destination=self.root/'packets';prepare(self.con,self.root,destination)
        packet=json.loads((destination/f'{self.pid:03d}.json').read_text())
        self.assertTrue(Path(packet['sources'][0]['local_html_path']).is_absolute())
        self.assertEqual(packet['sources'][0]['links'][0]['url'],'https://example.edu/~a/')
        self.assertTrue((destination/'review-schema.json').exists())
    def test_shortlist_notes_and_complete_reorder(self):
        p2=add_professor(self.con,name='B',title='Professor',profile_url='https://example.edu/b',source_id=self.sid)
        save_application(self.con,self.pid,'My private note');save_application(self.con,p2)
        reorder_applications(self.con,[p2,self.pid])
        self.assertEqual(detail(self.con,self.pid)['application_notes'],'My private note')
        self.assertEqual(detail(self.con,self.pid)['application_rank'],1)
        with self.assertRaises(ValueError):reorder_applications(self.con,[p2,p2])
    def test_discovery_uses_disk_cache_and_groups_aliases(self):
        def fetch(url):
            if 'institutions' in url:return 'institution,region,countryabbrv\nHKU,Asia,hk\n'
            if 'generated-author' in url:return 'name,area,count,adjustedcount\nAlpha,aaai,3,2\n'
            return 'name,affiliation,homepage,scholarid\nAlpha,HKU,https://example.edu/a,ID\nAlpha Alias,HKU,https://example.edu/a,ID\n'
        with patch.object(discovery.scout,'_fetch_url',side_effect=fetch) as get:
            first=discovery.search(self.root,{})
            second=discovery.search(self.root,{})
            self.assertEqual(get.call_count,3)
        self.assertEqual(len(first),1);self.assertEqual(first,second)
        ids=discovery.import_candidates(self.con,self.root,first)
        self.assertEqual(ids,discovery.import_candidates(self.con,self.root,first))
        self.assertEqual(self.con.execute('SELECT official_profile_url FROM affiliations WHERE professor_id=?',(ids[0],)).fetchone()[0],'')

class HTTPTest(unittest.TestCase):
    def test_real_http_directory_review_import_and_notes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);con=connect(root)
            sid=store_source(con,root,url='https://example.edu/a',text='Professor A. Agents.')
            pid=add_professor(con,name='A',title='Assistant Professor',profile_url='https://example.edu/a',source_id=sid)
            con.close()
            server=make_server(root,0)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            def req(path,method='GET',body=None,origin=None):
                headers={'Content-Type':'application/json'}
                if origin:headers['Origin']=origin
                request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
                    data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
                with urllib.request.urlopen(request,timeout=10) as response:return response.status,response.read()
            try:
                code,body=req('/');self.assertEqual(code,200);self.assertIn(b'Source interests',body)
                code,body=req('/api/professors');self.assertEqual(json.loads(body)[0]['name'],'A')
                review={'format_version':2,'professor_id':pid,'review_state':'reviewed','profile_source_id':sid,
                    'checked_source_ids':[sid],'interests_ai':'Agent research.',
                    'interests_source':[{'source_id':sid,'evidence_quote':'Agents.'}],
                    'interest_evidence':[{'source_id':sid,'evidence_quote':'Agents.'}],
                    'recruitment_signals':[{'degree':d,'status':0,'source_id':sid,'reasoning':'No invitation stated.'} for d in ['PhD','MPhil']]}
                code,body=req('/api/reviews/import','POST',review)
                self.assertGreater(json.loads(body)['review_id'],0)
                code,body=req('/api/professors');self.assertEqual(json.loads(body)[0]['interests_ai'],'Agent research.')
                req('/api/apply','POST',{'professor_id':pid,'notes':'Keep this note'})
                code,body=req('/api/apply');self.assertEqual(json.loads(body)[0]['application_notes'],'Keep this note')
                code,body=req(f'/api/sources/{sid}/text');self.assertIn(b'Professor A',body)
                with self.assertRaises(urllib.error.HTTPError) as e:req('/api/apply','POST',{'professor_id':pid},'https://unrelated.example')
                self.assertEqual(e.exception.code,403)
                code,body=req('/api/prepare','POST',{});self.assertEqual(json.loads(body)['count'],1)
            finally:server.shutdown();server.server_close()

class LegacyMigrationTest(unittest.TestCase):
    def test_v1_upgrade_preserves_sources_and_review_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            con=sqlite3.connect(root/'faculty.sqlite');con.row_factory=sqlite3.Row
            schema=Path(__file__).resolve().parents[1]/'faculty_atlas/schema.sql'
            con.executescript(schema.read_text())
            sid=store_source(con,root,url='https://example.edu/a',text='Original interests: agents.',fetched_at='2024-01-01T00:00:00+00:00')
            pid=add_professor(con,name='Legacy A',title='Professor',profile_url='https://example.edu/a',source_id=sid)
            con.execute("INSERT INTO topics VALUES('agents','other')")
            con.execute("UPDATE professors SET homepage_url='https://example.edu/~a/' WHERE id=?",(pid,))
            rid=con.execute("INSERT INTO reviews(professor_id,reviewed_at,state,notes,payload_hash) VALUES(?,'2024-01-02','reviewed','Keep notes','legacy-hash')",(pid,)).lastrowid
            con.execute('INSERT INTO review_sources VALUES(?,?)',(rid,sid))
            con.execute('''INSERT INTO research_matches(review_id,professor_id,area,topic,raw_topic,match_strength,source_id,evidence_quote,reasoning)
                VALUES(?,?,'agents','other','Agent research',2,?,'agents.','AI interpretation')''',(rid,pid,sid))
            con.commit();con.close()
            for _ in range(2):
                con=connect(root)
                self.assertEqual(con.execute('SELECT count(*) FROM reviews').fetchone()[0],1)
                self.assertEqual(con.execute('SELECT payload_hash FROM reviews').fetchone()[0],'legacy-hash')
                self.assertEqual(con.execute('SELECT fetched_at FROM sources').fetchone()[0],'2024-01-01T00:00:00+00:00')
                self.assertEqual(con.execute('SELECT method FROM source_interests').fetchone()[0],'legacy_quote')
                self.assertEqual(con.execute('SELECT count(*) FROM interest_evidence').fetchone()[0],1)
                self.assertEqual(detail(con,pid)['homepage_evidence_state'],'legacy_unverified')
                con.close()

if __name__=='__main__':unittest.main()
