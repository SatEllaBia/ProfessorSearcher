from __future__ import annotations
from .db import now

def esc(s):
    return str(s or '—').replace('|','\\|').replace('\n',' ')

def degree_summary(con,rid,degree):
    rows=con.execute('SELECT status,temporal_state FROM recruitment_signals WHERE review_id=? AND degree=?',(rid,degree)).fetchall()
    if not rows:
        return 'not checked'
    usable=[r for r in rows if r['temporal_state']!='past' and r['status']!=0]
    states={r['status'] for r in usable}
    if len(states)>1:
        return 'conflict: '+','.join(map(str,sorted(states)))
    if states:
        return str(next(iter(states))) + (' (unclear timing)' if any(r['temporal_state']=='unclear' for r in usable) else ' (undated)' if any(r['temporal_state']=='undated' for r in usable) else '')
    if any(r['temporal_state']=='past' and r['status']!=0 for r in rows):
        return '0 (past signal only)'
    return '0'

def export(con,path):
    quote_budgets={}
    quote_seen=set()
    def excerpt(sid,quote):
        if not quote or (sid,quote) in quote_seen:
            return ''
        quote_seen.add((sid,quote))
        words=quote.split()
        available=25-quote_budgets.get(sid,0)
        selected=words[:max(0,available)]
        quote_budgets[sid]=quote_budgets.get(sid,0)+len(selected)
        return ' '.join(selected)+(' …' if selected and len(selected)<len(words) else '')
    people=con.execute('''SELECT p.*, a.title,a.department,a.official_profile_url,r.id rid,r.reviewed_at
        FROM professors p JOIN affiliations a ON a.professor_id=p.id
        LEFT JOIN current_reviews r ON r.professor_id=p.id ORDER BY p.name''').fetchall()
    counts={s:con.execute('SELECT count(*) FROM professors WHERE review_state=?',(s,)).fetchone()[0] for s in ['pending','partial','reviewed']}
    out=['# HKU AI & Data Science — application research',f'Generated: {now()}',
         f"Coverage: {len(people)} affiliation records; reviewed {counts['reviewed']}, partial {counts['partial']}, pending {counts['pending']}.",
         'Recruitment: -1 explicitly closed; 0 unknown; 1 possibly welcoming; 2 explicitly welcoming. PhD and MPhil are independent. Undated invitations do not confirm a current funded vacancy. Past-only evidence is retained without marking a current opening. A partial review can have unknown findings for pages actually checked while other pages failed.',
         'Research fit: 0 outside the requested interests; 1 adjacent; 2 clear match; 3 direct match. AI interpretations and matches are separate from verbatim source interests. All source snapshots and original descriptions remain available in SQLite.',
         '| Name | Rank | Email | PhD | MPhil | Topics | Review |',
         '|---|---|---|---|---|---|---|']
    for p in people:
        matches=con.execute('SELECT area,topic,raw_topic FROM research_matches WHERE review_id=?',(p['rid'],)).fetchall()
        topics='; '.join(f"{m['area']}.{m['topic']}: {m['raw_topic']}" for m in matches)
        target=p['official_profile_url'] or p['homepage_url']
        name=f"[{esc(p['name'])}]({target})" if target else esc(p['name'])
        out.append(f"| {name} | {esc(p['title'])} | {esc(p['email'])} | {degree_summary(con,p['rid'],'PhD')} | {degree_summary(con,p['rid'],'MPhil')} | {esc(topics)} | {p['review_state']} |")
    out+=['','## Evidence and review notes']
    for p in people:
        out += ['',f"### {p['name']}",f"{p['title']} · {p['department']}",f"Official profile: {p['official_profile_url']}",f"Homepage: {p['homepage_url'] or 'not established'}",f"Email: {p['email'] or 'not established'}",f"Review: {p['review_state']}; checked {p['reviewed_at'] or 'not checked'}."]
        if p['notes']:
            out.append(p['notes'])
        original=con.execute('SELECT text,source_id,method FROM source_interests WHERE professor_id=?',(p['id'],)).fetchall()
        out+=['','**Source interests (original wording)**']
        for item in original:
            quote=excerpt(item['source_id'],item['text'])
            if quote: out.append(f"- “{quote}” (source {item['source_id']}; {item['method']})")
        summary=con.execute('SELECT interests_ai FROM reviews WHERE id=?',(p['rid'],)).fetchone()
        out+=['','**AI interests (interpretation)**',summary['interests_ai'] if summary and summary['interests_ai'] else 'Not extracted.']
        homes=con.execute('SELECT * FROM homepage_findings WHERE review_id=?',(p['rid'],)).fetchall()
        out+=['','**Homepage findings**']
        if p['homepage_url'] and not any(h['url']==p['homepage_url'] for h in homes):
            out.append('Legacy homepage link: not yet revalidated with a version 2 homepage finding.')
        for h in homes:
            out.append(f"- {h['kind']}: {h['url']} (source {h['source_id']}). {h['reasoning']}")
        for s in con.execute('''SELECT x.*,s.url,s.fetched_at FROM recruitment_signals x JOIN sources s ON s.id=x.source_id WHERE x.review_id=?''',(p['rid'],)):
            out+=['',f"- **{s['degree']} {s['status']}** ({s['temporal_state']}; intake: {s['intake'] or 'not stated'}). {s['reasoning']}"]
            quote=excerpt(s['source_id'],s['evidence_quote'])
            if quote:
                out.append(f"  Evidence excerpt: “{quote}”")
            out.append(f"  [Source {s['source_id']}]({s['url']}) · retrieved {s['fetched_at']}")
        for m in con.execute('''SELECT m.*,s.url FROM research_matches m JOIN sources s ON s.id=m.source_id WHERE m.review_id=?''',(p['rid'],)):
            quote=excerpt(m['source_id'],m['evidence_quote'])
            evidence=f'Excerpt: “{quote}” ' if quote else ''
            out+=['',f"- **{m['area']}.{m['topic']}** · fit {m['match_strength']}/3 · {m['raw_topic']}. {m['reasoning']}",f"  {evidence}([source {m['source_id']}]({m['url']}))"]
        pages=con.execute('''SELECT DISTINCT s.id,s.url,s.state,s.error,s.fetch_method FROM sources s JOIN professor_sources ps ON s.id=ps.source_id WHERE ps.professor_id=?''',(p['id'],)).fetchall()
        out+=['','Sources: '+ '; '.join(f"[{s['id']}]({s['url']}) ({s['fetch_method']}, {s['state']})" for s in pages)]
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('\n\n'.join(out[:5])+'\n\n'+'\n'.join(out[5:])+'\n',encoding='utf-8')
