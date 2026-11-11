import tempfile
import unittest
from unittest.mock import patch
import httpx
from pathlib import Path
from faculty_atlas.db import connect,store_source,add_professor
from faculty_atlas.review import import_review
from faculty_atlas.report import degree_summary,export
from faculty_atlas.collect import discover,fetch
from faculty_atlas.query import shortlist

class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.con=connect(self.root)
        self.sid=store_source(self.con,self.root,url='https://example.edu/a',text='Email: a@example.edu. I welcome PhD students. Generative smoke simulation.')
        self.pid=add_professor(self.con,name='A',title='Assistant Professor',profile_url='https://example.edu/a',source_id=self.sid)
        self.payload={'professor_id':self.pid,'review_state':'reviewed','checked_source_ids':[self.sid],'profile_source_id':self.sid,'email':'a@example.edu',
                      'recruitment_signals':[{'degree':'PhD','status':2,'source_id':self.sid,'evidence_quote':'I welcome PhD students.','reasoning':'Explicit but undated.'},
                                             {'degree':'MPhil','status':0,'source_id':self.sid,'reasoning':'Not stated.'}],
                      'research_matches':[{'area':'ai_graphics','topic':'other','raw_topic':'Generative smoke simulation','match_strength':3,'source_id':self.sid,'evidence_quote':'Generative smoke simulation.','reasoning':'AI simulation fit.'}]}
    def tearDown(self):self.con.close();self.tmp.cleanup()
    def test_idempotence_and_export(self):
        rid=import_review(self.con,self.root,self.payload)
        self.assertEqual(rid,import_review(self.con,self.root,self.payload))
        self.assertEqual(degree_summary(self.con,rid,'PhD'),'2 (undated)')
        self.assertEqual(degree_summary(self.con,rid,'MPhil'),'0')
        export(self.con,self.root/'report.md')
        self.assertIn('ai_graphics.other',(self.root/'report.md').read_text())
        self.assertIn('| Review |\n|---', (self.root/'report.md').read_text())
    def test_reject_unsubstantiated_quote_atomically(self):
        self.payload['research_matches'][0]['evidence_quote']='Imaginary research.'
        with self.assertRaises(ValueError):import_review(self.con,self.root,self.payload)
        self.assertEqual(self.con.execute('SELECT count(*) FROM reviews').fetchone()[0],0)
    def test_failed_source_not_checked(self):
        failed=store_source(self.con,self.root,url='https://example.edu/b',state='failed',error='DNS')
        self.payload['checked_source_ids'].append(failed)
        with self.assertRaises(ValueError):import_review(self.con,self.root,self.payload)
    def test_conflicts_and_old_intake(self):
        self.payload['recruitment_signals'][0]['temporal_state']='past'
        rid=import_review(self.con,self.root,self.payload)
        self.assertEqual(degree_summary(self.con,rid,'PhD'),'0 (past signal only)')
        self.payload['recruitment_signals'][0]['temporal_state']='undated'
        self.payload['recruitment_signals'].append({'degree':'PhD','status':-1,'source_id':self.sid,'evidence_quote':'PhD students','reasoning':'Conflict test fixture.'})
        rid=import_review(self.con,self.root,self.payload)
        self.assertEqual(degree_summary(self.con,rid,'PhD'),'conflict: -1,2')
        self.assertEqual(self.con.execute('SELECT count(*) FROM current_reviews').fetchone()[0],1)
        self.assertEqual(shortlist(self.con,area='ai_graphics',degree='PhD',status=2),[])
    def test_taxonomy_and_email_validation(self):
        self.payload['research_matches'][0]['topic']='invented'
        with self.assertRaises(ValueError):import_review(self.con,self.root,self.payload)
        self.payload['research_matches'][0]['topic']='other';self.payload['email']='guessed@example.edu'
        with self.assertRaises(ValueError):import_review(self.con,self.root,self.payload)
    def test_directory_excludes_lecturers_and_honorary(self):
        html='<h1>Academic Staff</h1><h4><a href="/a">A</a></h4><h4>Assistant Professor</h4><h4><a href="/b">B</a></h4><h4>Lecturer</h4><h1>Honorary Professors</h1><h4><a href="/c">C</a></h4><h4>Professor</h4>'
        sid=store_source(self.con,self.root,url='https://example.edu/people',text='staff',html=html)
        self.assertEqual([r['name'] for r in discover(self.con,self.root,sid)],['A'])
    def test_http_fetch_does_not_reuse_text_only_extract(self):
        url='https://example.edu/page'
        extracted=store_source(self.con,self.root,url=url,text='partial text',fetch_method='web_extract')
        response=httpx.Response(200,text='<html><body>'+('Research and students. '*20)+'</body></html>',headers={'content-type':'text/html'},request=httpx.Request('GET',url))
        with patch('httpx.Client.get',return_value=response) as get:
            sid=fetch(self.con,self.root,url)
            self.assertNotEqual(sid,extracted)
            self.assertEqual(fetch(self.con,self.root,url),sid)
            self.assertEqual(get.call_count,1)
        row=self.con.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        self.assertTrue((self.root/row['html_path']).exists())
    def test_failed_http_fetch_records_status(self):
        url='https://example.edu/missing'
        response=httpx.Response(404,request=httpx.Request('GET',url))
        with patch('httpx.Client.get',return_value=response):sid=fetch(self.con,self.root,url)
        row=self.con.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        self.assertEqual((row['state'],row['http_status']),('failed',404))
        self.assertIsNone(row['text_path'])
    def test_obfuscated_email_is_decoded_without_shared_footer_address(self):
        sid=store_source(self.con,self.root,url='https://example.edu/a2',text='Email: a [AT] example [DOT] edu')
        self.payload['profile_source_id']=sid;self.payload['checked_source_ids'].append(sid)
        self.assertIsInstance(import_review(self.con,self.root,self.payload),int)

if __name__=='__main__':unittest.main()
