"""Reproduce the first manually reviewed HKU pass from saved, immutable evidence.

Classification below is authored after reading the sources; it is not a keyword
classifier. `review-import` validates every reference and quotation before writing.
"""
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from faculty_atlas.db import connect,dump_json
from faculty_atlas.review import contact_norm,import_review

ROOT=Path('data')
con=connect(ROOT)
profiles=json.loads((ROOT/'profile-index.json').read_text())
by_key={p['key']:p for p in profiles}
associated={p['professor_id']:{p['source_id']} for p in profiles}
home={p['professor_id']:p['homepage_url'] for p in profiles}
for index in ['home-index.json','extra-index1.json','extra-index2.json','extra-index3.json']:
    for record in json.loads((ROOT/index).read_text()):
        if isinstance(record['key'],int):
            pid=by_key[record['key']]['professor_id']
            associated[pid].add(record['source_id'])
            con.execute('INSERT OR IGNORE INTO professor_sources VALUES(?,?,?)',(pid,record['source_id'],'homepage_or_related'))
con.commit()
# Empty lab landing page returned no page body; keep the failed retrieval visible.
con.execute("UPDATE sources SET state='failed',error='No usable page text returned',text_path=NULL WHERE id=70")
con.commit()
home.update({3:'https://daibo.info/',5:'https://web26.edu.hku.hk/faculty-academics/dgasevic',
             15:'https://yingyuliang.github.io/',17:'https://www.bio8.cs.hku.hk/',
             30:'https://taoyds.github.io/',34:'https://difanzou.github.io/'})

def attach(pid,sid):
    associated[pid].add(sid)
    con.execute('INSERT OR IGNORE INTO professor_sources VALUES(?,?,?)',(pid,sid,'recruitment_context'))

for pid in [2,9,24,31]:attach(pid,63)
for pid in [8,10,15,30,3]:attach(pid,73)
con.commit()

matches={}
signals={}
def match(pid,area,topic,sid,quote,raw,strength,reason):
    matches.setdefault(pid,[]).append(dict(area=area,topic=topic,source_id=sid,evidence_quote=quote,
                                         raw_topic=raw,match_strength=strength,reasoning=reason))
def signal(pid,degree,status,sid,quote,reason,intake=None,temporal='undated'):
    signals.setdefault(pid,[]).append(dict(degree=degree,status=status,source_id=sid,evidence_quote=quote,
                                         reasoning=reason,intake=intake,temporal_state=temporal))

match(1,'other','other',2,'Learning Theory','Learning theory and high-dimensional statistics',0,'Foundational ML; the checked interests do not establish a direct agents, visual generation, or AI graphics focus.')
signal(1,'PhD',2,36,'I am looking for highly motivated Ph.D. students','Explicit PhD invitation; no intake or funding commitment stated.')

match(2,'other','other',3,'Graph Analytics','Databases, graph analytics and uncertain data',0,'Data systems focus; not a direct match to the requested research areas.')
for degree in ['PhD','MPhil']:
    signal(2,degree,2,74,'openings for PhD (4 years) and MPhil (2 years) this year','Both degrees are named. “This year” has no publication date to anchor it; confirm the intake.',intake='this year (year not established)',temporal='unclear')

match(3,'generation','video_generation',75,'AnimateDiff, a pioneering work and milestone in video generation','Video generation / AnimateDiff',3,'The institutional biography explicitly identifies video generation.')
match(3,'ai_graphics','neural_rendering',75,'city-scale scene reconstruction and rendering','City-scale learned scene reconstruction and rendering',3,'The cited biography identifies a rendering research series including CityNeRF and Scaffold-GS; the neural-rendering tag is an interpretation of that series.')
match(3,'agents','embodied_agents',4,'Embodied AI','Generative AI applied to embodied AI',2,'Embodied AI is explicitly listed; particular agent architectures are not established in this profile.')
signal(3,'PhD',2,59,'Looking for researchers/interns/phds/post-docs.','The personal homepage explicitly lists PhDs; undated.')

match(4,'generation','image_generation',60,'image generation','Image generation and visual understanding',3,'The biography explicitly lists image generation. Another research-interest block on the same page lists unrelated medical topics; this inconsistency is flagged in the notes.')
match(5,'other','other',6,'human-AI interaction','Learning analytics and human–AI interaction in education',1,'AI interaction and educational use of generative models are adjacent; the checked evidence does not establish visual content generation or agent construction as the main focus.')
for degree in ['PhD','MPhil']:
    signal(5,degree,2,65,'I am available to supervise PhD/MPhil students and would welcome enquiries for supervision.','Explicit supervision invitation for both degrees on the Education profile. Confirm whether the application should be through Education or CDS.')
match(6,'other','other',7,'satellite remote sensing data','AI for remote sensing, sustainability and environmental health',0,'Applied remote sensing does not itself establish a direct match to the requested areas.')

match(7,'generation','other',8,'generative AI','Generative AI and spatial intelligence',2,'Explicit generative-AI focus; specific modalities are separately supported by homepage publications.')
match(7,'generation','video_generation',38,'Joint Video-Audio Generation and Editing','Joint video/audio generation and editing (JoVA)',3,'The homepage lists the named 2026 video/audio generation work.')
match(7,'generation','3d_generation',38,'Generating 4D Shapes via Sparse-Attention Diffusion Transformers','4D shape generation (Sculpt4D)',3,'Time-varying 3D shapes fit the 3D generation topic; the raw description preserves 4D.')
signal(7,'PhD',2,38,'PhD / Postdoc / RA','Listed under Openings with an invitation to strong candidates. No cohort-specific intake stated.')

match(8,'agents','llm_agents',39,'Large Language Models,  Autonomous Agents','Autonomous agents and LLM applications',3,'The lab explicitly lists both LLMs and autonomous agents, and links agent projects. The LLM-agent tag interprets this combined focus.')
signal(8,'PhD',2,73,'I am looking for self-motivated Ph.D. students/Research (Remote) Interns','Explicit invitation in the Chao Huang section. The shared institutional page is undated and contains older material.')
match(9,'other','other',10,'Database Management Systems, Data Mining','Databases and data mining',0,'The checked profile is primarily database and information retrieval research; homepage retrieval failed.')
match(10,'other','other',11,'Network Science, Complex Systems, Statistical Physics, Statistical Inference','Network science and statistical inference',0,'No direct requested-area match established by the checked description.')
signal(10,'PhD',2,73,'I am looking for PhD students and Research Assistants','Explicit invitation in the Alec Kirkley section of an undated institutional page.')

match(11,'ai_graphics','learned_animation',12,'application of machine learning techniques for animation synthesis','Machine learning for character animation synthesis',3,'An explicit AI-plus-animation direction; this is distinguishable from the profile’s conventional simulation work.')
match(11,'generation','motion_generation',12,'Unified synthesis of physical human-scene interactions through task tokenization','Human–scene interaction and motion synthesis',3,'The listed 2025 publication supports learned interaction synthesis.')
signal(11,'PhD',2,42,'PhD and Postdoc positions available!','The homepage explicitly announces PhD positions, without intake dates.')

match(12,'agents','other',13,'generative AI agents','Generative AI agents for decision-making and social impact',3,'Direct agent research, preserved under agents.other because the profile spans generative policies and decisions.')
match(12,'agents','planning',43,'long-horizon planning under uncertainty','Long-horizon planning with generative policies',3,'The homepage explicitly describes planning with reinforcement learning, diffusion models and LLMs.')
match(12,'agents','multi_agent',43,'Multi-Agent Systems','Human-in-the-loop multi-agent cooperation',3,'Named research thread on the personal homepage.')
signal(12,'PhD',2,43,'[PhD/RA/Intern + Year]','The student invitation asks PhD applicants to use this subject line. No particular intake is promised.')

match(13,'generation','other',44,'generative models','Generative models for NLP and representation learning',2,'Generative models are explicit, but this evidence is language-oriented rather than visual generation.')
match(14,'agents','embodied_agents',15,'Embodied AI, Autonomous Driving, Robotic Manipulation, Humanoids, VLA and World Models','Embodied agents, VLA, robotic manipulation and world models',3,'Explicit research interests directly fit embodied agents.')
for degree in ['PhD','MPhil']:
    signal(14,degree,1,45,'Post-doc / Ph.D. / MPhil: No need to contact me first.','A degree-specific prospective-applicant route and selection expectations are given, but this does not explicitly promise an open vacancy. Use the academic-assistant route described on the page.')

match(15,'generation','other',64,'NRFlow: Towards Noise-Robust Generative Modeling via High-Order Mechanism','Generative modeling foundations',2,'A generative-modeling publication is listed, alongside a broader theoretical ML focus.')
for degree in ['PhD','MPhil']:
    signal(15,degree,1,73,'If you are interested in joining my research group, please drop me an email to discuss further.','The Yingyu Liang section invites group enquiries but does not specify a degree. Degree-specific availability is therefore only possible, not explicit.')
signal(15,'unspecified',2,73,'If you are interested in joining my research group, please drop me an email to discuss further.','Explicit invitation to discuss joining; no degree or intake specified.')

match(16,'agents','other',17,'solve complex tasks with larger autonomy','Autonomous learning systems and reinforcement learning',1,'Autonomy and reinforcement learning are stated; the checked official page is not sufficient to establish a specific LLM-agent project.')
signal(16,'PhD',2,17,'I am recruiting a number of Postdocs, PhDs, and RAs.','Explicit PhD recruitment on the official profile. The linked personal homepage timed out, so currency needs follow-up.')
match(17,'other','other',18,'bioinformatics algorithms and clinical informatics','Bioinformatics algorithms and clinical informatics',0,'This evidence supports bioinformatics rather than one of the three requested research areas.')
for degree in ['PhD','MPhil']:
    signal(17,degree,1,71,'We are looking for dedicated and self-motivated students and postdocs','The lab recruits students without naming the degree; individual degree availability remains inferred.')
signal(17,'unspecified',2,71,'We are looking for dedicated and self-motivated students and postdocs','Explicit student recruitment, degree unspecified.')

match(18,'other','other',19,'Computer vision, high-dimensional data analysis, and intelligent systems','Foundations of vision and representation learning',1,'Adjacent foundations; the checked profile does not establish the requested agent or generation specialization.')
match(19,'agents','embodied_agents',20,'agentic physical systems','Agentic physical systems and robot intelligence',3,'The research statement explicitly targets agentic robot systems.')
match(19,'agents','planning',20,'Language-Augmented Symbolic Planner for Open-World Task Planning','Language-augmented open-world planning',3,'The profile lists this RSS 2024 publication.')
match(19,'generation','motion_generation',20,'Text-Guided Synthesis of Crowd Animation','Text-guided crowd animation synthesis',3,'The profile lists a SIGGRAPH 2024 synthesis publication, distinct from conventional graphics.')
for degree in ['PhD','MPhil']:
    signal(19,degree,1,20,'Express your interest here','The Prospective Students section provides an interest form, without naming a degree or guaranteeing an opening. It asks applicants not to email directly.')

match(20,'agents','other',21,'Bandits and reinforcement learning','Interactive decision-making theory and reinforcement learning',1,'Relevant foundations for agents; a concrete deployed or LLM-agent focus is not established.')
signal(20,'PhD',2,48,'I am looking for motivated PhD students and RAs','Explicit PhD invitation. The homepage still labels the appointment Incoming, unlike the official directory.')
match(21,'generation','image_generation',49,'image synthesis/generation','Medical image synthesis/generation',3,'A targeted research direction for the explicitly stated 2027 intake.')
signal(21,'PhD',2,49,'Ph.D. students, and remote interns to join my group in Spring 2027/Fall 2027.','Explicit upcoming recruitment. Medical imaging and healthcare VLM/LLM interests are emphasized.',intake='Spring 2027 / Fall 2027',temporal='current')

match(22,'other','other',23,'pure mathematics and interdisciplinary applications','Mathematics, interdisciplinary applications and AI education',0,'The leadership biography does not establish direct target-area fit.')
match(23,'generation','other',24,'Understanding modern generative models','Generative-model theory and latent variable models',2,'Explicit generative-model research, without a particular visual modality established here.')

match(24,'generation','image_generation',50,'Image Generation and Improved Visual Representation Capabilities','Image generation using binary latent codes (BiGR)',3,'The homepage lists a 2025 image-generation publication.')
match(24,'generation','video_generation',50,'Dual-Expert Consistency Model for Efficient and High-Quality Video Generation','Efficient video generation',3,'The homepage lists this video-generation work.')
match(24,'ai_graphics','neural_rendering',50,'Neural Inverse Rendering','Neural inverse rendering',3,'The homepage lists PS-NeRF; the tag is supported by the publication title.')
signal(24,'PhD',2,63,'I am looking for PhD candidates','Explicit PhD invitation in K.K.Y. Wong’s section of an undated departmental messages page.')

match(25,'agents','llm_agents',51,'LLM-powered agentic tools','LLM agents for spatial biology',3,'The homepage explicitly describes LLM-powered agents for biological data interpretation.')
signal(25,'PhD',2,51,'I am seeking enthusiastic PhD candidates and postdoctoral researchers','Explicit PhD invitation; no intake stated.')
match(26,'other','other',27,'autonomous driving, AR/VR, video compression','Vision, multimedia and AR/VR',1,'Adjacent visual computing; an AI graphics or generative specialization is not established by the accessible profile. Homepage retrieval failed.')

match(27,'agents','embodied_agents',28,'robots and autonomous agents','Embodied agents and robot manipulation',3,'The profile explicitly centers embodied agents and manipulation policies.')
match(27,'ai_graphics','neural_rendering',28,'neural rendering and real-time reconstruction','Neural rendering and real-time reconstruction',3,'An explicit research direction combining learning and graphics.')
signal(27,'PhD',2,53,'We are now considering applications for 2026/2027 enrollment','The PhD recruitment section states 2026/2027 enrollment. The profile and homepage also describe scholarship routes; no guaranteed award is implied.',intake='2026/2027 enrollment (as written)',temporal='current')

match(28,'other','other',29,'Legal AI, Natural language processing, Computational social science, AI for social good','Legal AI and NLP evaluation',1,'Adjacent use of language models; no agent-construction or visual-generation focus is established in the checked profiles.')
match(29,'agents','other',55,'LLM/VLM/Agentic AI for Healthcare','Agentic AI for healthcare',3,'The homepage explicitly identifies agentic AI as a recent focus.')
match(29,'generation','3d_generation',55,'AssetFormer: Modular 3D Assets Generation with Autoregressive Transformer','Autoregressive modular 3D asset generation',3,'The homepage lists this generation publication; broader lab focus remains medical AI.')
signal(29,'PhD',2,55,'We are looking for self-motivated PhD/RA/Interns/visiting students','Explicit PhD invitation; the page requests an email and a brief Google form.')

match(30,'agents','tool_use',62,'creating computer use agents','Computer-use agents and digital environments',3,'The homepage explicitly describes agents using screens, clicks and typing.')
match(30,'agents','embodied_agents',62,'embodied AI agents','Agents spanning digital and physical environments',3,'The research statement explicitly covers grounded actions and robotics.')
for degree in ['PhD','MPhil']:
    signal(30,degree,1,62,'We are actively looking for strong and motivated students to join our group!','Explicit student invitation and application form, but the invitation does not name the degree. Do not convert lab members’ degrees into a current vacancy.')
signal(30,'unspecified',2,62,'We are actively looking for strong and motivated students to join our group!','Clear invitation, degree unspecified. The page requests a form with proposed extensions of recent papers and warns that individual emails may not receive replies.')

match(31,'generation','other',57,'AI based multimedia content generation','AI-based multimedia content generation',3,'The personal homepage explicitly lists content generation. Its displayed last-modified date is 2023, so current project emphasis needs checking.')
for degree in ['PhD','MPhil']:
    signal(31,degree,1,63,'I am looking for smart, resourceful and hardworking postgraduate students','The Y.Z. Yu section invites postgraduate students but does not specify a degree. The page is undated.')
signal(31,'unspecified',2,63,'I am looking for smart, resourceful and hardworking postgraduate students','Explicit postgraduate invitation, degree unspecified.')
match(32,'agents','other',33,'hallucinations and reasoning limitations in LLMs','LLM reliability, hallucination diagnosis and reasoning',1,'Enabling work for agents; the checked statement does not establish agent construction as the main focus.')

match(33,'agents','embodied_agents',34,'Embodied AI','Embodied intelligent systems',3,'The official profile explicitly names embodied AI.')
match(33,'generation','video_generation',58,'fast video generation','Fast video generation and editing',3,'The homepage lists SURF and other recent video-generation projects.')
match(33,'generation','3d_generation',58,'Controllable 3D anime character generation.','Controllable 3D anime character generation',3,'The homepage lists the ICLR 2026 Anime-Ready project.')
signal(33,'PhD',2,58,'actively looking for self-motivated Ph.D. students','Explicit prospective-student invitation on the personal homepage, without intake dates.')
match(34,'generation','other',61,'Physics-Informed Distillation of Diffusion Models for PDE-Constrained Generation','Physics-constrained diffusion generation',2,'The homepage lists a 2026 physics-informed generation work. Preserve the particular topic rather than forcing it into a visual modality.')
signal(34,'PhD',2,61,'I welcome enquiries from prospective PhD students','Explicit PhD enquiries welcome under Open positions; no intake or funding commitment stated.')

notes={
4:'The IDS page has inconsistent interest blocks: its biography says 3D reconstruction/image generation/video understanding, while another block lists medical informatics. Match uses the biography; needs a personal research-page cross-check.',
5:'Recruitment evidence comes from the Faculty of Education. Verify the appropriate degree home and CDS supervision arrangements.',
6:'Courtesy appointment retained. Only the official research biography was established; a personal research homepage and recruitment statement remain unresolved.',
9:'Personal homepage failed through both www.cs and i.cs routes. Official profile and departmental student-message section were checked.',
13:'The linked NLP group landing page returned no usable text; personal homepage and official profile were readable.',
14:'Recruitment page prioritizes HKPFS/HKU Presidential Scholarship-level candidates and directs informal contact to the academic assistant. Degree routes are evidence of possible availability, not a confirmed opening.',
16:'AI division directory/profile say Professor; the school directory lists Associate Professor. Rank retained from AI source. Personal homepage timed out; official PhD invitation is undated. The Gmail recruitment contact on the official profile differs from the institutional contact field.',
18:'Official page contains extensive research material but no separate personal homepage was established. Recruitment remains unknown.',
19:'Use the linked prospective-student interest form; the profile explicitly requests not to email directly. Degree-specific recruitment is inferred only.',
20:'Homepage heading says Incoming while the official AI directory lists Assistant Professor; both sources retained.',
22:'The directory links to an institutional leadership profile rather than a department profile. Rank retained from directory; a personal research homepage and recruitment evidence remain unresolved.',
23:'Official profile lists generative-model theory. A separate personal homepage/recruitment page was not established.',
26:'Both personal-homepage routes were inaccessible. Generative or AI-graphics specialization cannot be decided from the official profile alone.',
28:'Directory displays Fan, Yu, while the linked Law profile displays Yu Fan; official cross-link anchors the identity. Joint Law/CDS appointment.',
30:'The official homepage redirects to taoyds.github.io. A related XLANG lab page was inaccessible. Student invitation is explicit but degree unspecified.',
31:'Personal homepage displays last modified 30/08/2023. Keep its research emphasis and the undated postgraduate invitation as potentially stale.',
32:'The official profile’s More details hyperlink is malformed. The intended HackMD URL was also inaccessible. The author’s current recruitment status remains unresolved.'}
partial={4,6,9,13,16,18,22,23,26,30,31,32}
reviews=[]
for profile in profiles:
    pid=profile['professor_id'];sid=profile['source_id']
    text=(ROOT/con.execute('SELECT text_path FROM sources WHERE id=?',(sid,)).fetchone()[0]).read_text()
    # Read contact information only before shared site navigation/footer.
    body=text.split('Division of AI & Data Science,')[0]
    normalized=contact_norm(body)
    email_match=re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',normalized)
    email=email_match[0] if email_match else None
    if pid==18:email='mayi@hku.hk'  # Research contact instead of the director's office mailbox.
    checked=[s for s in sorted(associated[pid]) if con.execute('SELECT state FROM sources WHERE id=?',(s,)).fetchone()[0]=='ok']
    for degree in ['PhD','MPhil']:
        if degree not in {s['degree'] for s in signals.get(pid,[])}:
            signal(pid,degree,0,sid,'',f'No usable degree-specific {degree} invitation or closure was found in the sources reviewed. This does not mean the professor is closed.')
    review=dict(professor_id=pid,review_state='partial' if pid in partial else 'reviewed',checked_source_ids=checked,
                profile_source_id=sid,email=email,homepage_url=home[pid],
                notes='First-pass review of retrieved profile/homepage text and selected research/recruitment sections; not a complete publication audit. '+notes.get(pid,''),
                recruitment_signals=signals[pid],research_matches=matches.get(pid,[]))
    # Evidence sources should be explicit even for shared institutional pages.
    for item in [*review['recruitment_signals'],*review['research_matches']]:
        if item['source_id'] not in review['checked_source_ids']:
            attach(pid,item['source_id']);review['checked_source_ids'].append(item['source_id'])
    con.commit()
    reviews.append(review)
dump_json(ROOT/'reviews'/'hku-ai-first-pass.json',reviews)
for review in reviews:
    try:import_review(con,ROOT,review)
    except Exception as e:raise RuntimeError(f"Professor {review['professor_id']}: {e}") from e
print(f'Imported {len(reviews)} reviewed faculty records')
con.close()
