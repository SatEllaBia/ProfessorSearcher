from .report import degree_summary

def shortlist(con,*,area=None,min_fit=2,degree=None,status=None):
    results=[]
    for p in con.execute('''SELECT p.*,r.id review_id FROM professors p
                         LEFT JOIN current_reviews r ON r.professor_id=p.id ORDER BY p.name''').fetchall():
        matches=con.execute('SELECT area,topic,raw_topic,match_strength FROM research_matches WHERE review_id=?',(p['review_id'],)).fetchall()
        matching=[dict(m) for m in matches if m['match_strength']>=min_fit and (not area or m['area']==area)]
        if not matching:
            continue
        if degree and status is not None:
            # Exact usable-status set, not MAX(status); conflicts and known past signals do not sneak through.
            states={r[0] for r in con.execute("SELECT status FROM recruitment_signals WHERE review_id=? AND degree=? AND temporal_state<>'past' AND status<>0",(p['review_id'],degree))}
            expected={status} if status else set()
            if states != expected:
                continue
        results.append(dict(id=p['id'],name=p['name'],email=p['email'],homepage_url=p['homepage_url'],
                            review_state=p['review_state'],PhD=degree_summary(con,p['review_id'],'PhD'),
                            MPhil=degree_summary(con,p['review_id'],'MPhil'),research_matches=matching))
    return results
