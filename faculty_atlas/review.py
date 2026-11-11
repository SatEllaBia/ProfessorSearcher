from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field
from .db import now

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Signal(StrictModel):
    degree: Literal['PhD','MPhil','unspecified']
    status: Literal[-1,0,1,2]
    intake: str | None = None
    temporal_state: Literal['undated','current','past','unclear'] = 'undated'
    source_id: int
    evidence_quote: str = ''
    reasoning: str = Field(min_length=1)

class Match(StrictModel):
    area: Literal['agents','generation','ai_graphics','other']
    topic: str
    raw_topic: str = Field(min_length=1)
    match_strength: int = Field(ge=0,le=3)
    source_id: int
    evidence_quote: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)

class Evidence(StrictModel):
    source_id: int
    evidence_quote: str = Field(min_length=1)

class Homepage(Evidence):
    url: str
    kind: Literal['personal','lab','institutional_profile']
    reasoning: str = Field(min_length=1)

class OriginalInterest(Evidence):
    method: Literal['parser','manual','verbatim_selection'] = 'verbatim_selection'

class Review(StrictModel):
    format_version: Literal[1,2] = 1
    professor_id: int
    review_state: Literal['partial','reviewed']
    checked_source_ids: list[int] = Field(min_length=1)
    profile_source_id: int
    email: str | None = None
    homepage_url: str | None = None
    notes: str = ''
    interests_ai: str = ''
    interests_source: list[OriginalInterest] = Field(default_factory=list)
    interest_evidence: list[Evidence] = Field(default_factory=list)
    homepages: list[Homepage] = Field(default_factory=list)
    recruitment_signals: list[Signal] = Field(min_length=1)
    research_matches: list[Match] = []

def norm(text):
    return re.sub(r'\s+',' ',text).strip()

def contact_norm(text):
    text=re.sub(r'\s*(?:\[at\]|\(at\)|\sAT\s)\s*','@',text,flags=re.I)
    return re.sub(r'\s*(?:\[dot\]|\(dot\))\s*','.',text,flags=re.I)

def import_review(con,root: Path,payload):
    review=Review.model_validate(payload)
    if not con.execute('SELECT 1 FROM professors WHERE id=?',(review.professor_id,)).fetchone():
        raise ValueError('Unknown professor_id')
    sources={}
    for sid in set(review.checked_source_ids):
        row=con.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        if not row or row['state'] != 'ok' or not row['text_path']:
            raise ValueError(f'Source {sid} is missing or failed')
        sources[sid]=norm((root / row['text_path']).read_text(encoding='utf-8'))
    if review.profile_source_id not in sources:
        raise ValueError('profile_source_id must be checked')
    if review.email and review.email.lower() not in contact_norm(sources[review.profile_source_id]).lower():
        raise ValueError('Email must occur verbatim in the profile evidence (decode obfuscation separately)')
    if review.homepage_url and urlsplit(review.homepage_url).scheme not in ('http','https'):
        raise ValueError('homepage_url must use http(s)')
    degrees={s.degree for s in review.recruitment_signals}
    if not {'PhD','MPhil'} <= degrees:
        raise ValueError('Explicitly record PhD and MPhil, including unknown=0')
    if review.interests_ai.strip() and not review.interest_evidence:
        raise ValueError('AI interests require source quotations in interest_evidence')
    if review.format_version==2 and review.homepage_url and not any(h.url==review.homepage_url for h in review.homepages):
        raise ValueError('Selected homepage requires a homepage finding with evidence')
    for item in [*review.recruitment_signals,*review.research_matches,*review.interest_evidence,*review.homepages,*review.interests_source]:
        if item.source_id not in sources:
            raise ValueError('Evidence source must be in checked_source_ids')
        quote=norm(item.evidence_quote)
        if quote and quote not in sources[item.source_id]:
            raise ValueError(f'Quote is not present in snapshot {item.source_id}: {quote[:80]}')
        if (not isinstance(item,Signal) or item.status != 0) and not quote:
            raise ValueError('Positive/closed claims and research matches require quotations')
        if isinstance(item,Match) and not con.execute('SELECT 1 FROM topics WHERE area=? AND topic=?',(item.area,item.topic)).fetchone():
            raise ValueError(f'Unknown taxonomy pair: {item.area}.{item.topic}; use this area\'s other')
        if isinstance(item,Homepage):
            from .collect import links
            from .records import normalized_url
            if urlsplit(item.url).scheme not in ('http','https'):
                raise ValueError('Homepage URLs must use http(s)')
            row=con.execute('SELECT * FROM sources WHERE id=?',(item.source_id,)).fetchone()
            candidates={normalized_url(row['url']),normalized_url(row['final_url'])}
            if row['html_path']:
                candidates.update(normalized_url(l['url']) for l in links((root/row['html_path']).read_text(),row['final_url']))
            if normalized_url(item.url) not in candidates and item.url not in sources[item.source_id]:
                raise ValueError('Homepage URL must occur in a checked snapshot or its HTML links')
    hash_payload=review.model_dump()
    if review.format_version==1 and not any([review.interests_ai,review.interest_evidence,review.homepages,review.interests_source]):
        for key in ['format_version','interests_ai','interest_evidence','homepages','interests_source']:
            hash_payload.pop(key)
    digest=hashlib.sha256(json.dumps(hash_payload,sort_keys=True).encode()).hexdigest()
    old=con.execute('SELECT id FROM reviews WHERE professor_id=? AND payload_hash=?',(review.professor_id,digest)).fetchone()
    if old:
        return old[0]
    with con:
        rid=con.execute('INSERT INTO reviews(professor_id,reviewed_at,state,notes,payload_hash,interests_ai) VALUES(?,?,?,?,?,?)',
                        (review.professor_id,now(),review.review_state,review.notes,digest,review.interests_ai)).lastrowid
        con.executemany('INSERT INTO review_sources VALUES(?,?)',[(rid,s) for s in sources])
        for s in review.interests_source:
            con.execute('INSERT OR IGNORE INTO source_interests(professor_id,source_id,text,method) VALUES(?,?,?,?)',
                (review.professor_id,s.source_id,s.evidence_quote,s.method))
        con.executemany('INSERT INTO interest_evidence VALUES(?,?,?)',
            [(rid,e.source_id,e.evidence_quote) for e in review.interest_evidence])
        for h in review.homepages:
            con.execute('''INSERT INTO homepage_findings(review_id,professor_id,url,kind,source_id,evidence_quote,reasoning)
                VALUES(?,?,?,?,?,?,?)''',(rid,review.professor_id,h.url,h.kind,h.source_id,h.evidence_quote,h.reasoning))
        for s in review.recruitment_signals:
            con.execute('''INSERT INTO recruitment_signals(review_id,professor_id,degree,status,intake,temporal_state,
                        source_id,evidence_quote,reasoning) VALUES(?,?,?,?,?,?,?,?,?)''',
                        (rid,review.professor_id,s.degree,s.status,s.intake,s.temporal_state,s.source_id,s.evidence_quote,s.reasoning))
        for m in review.research_matches:
            con.execute('''INSERT INTO research_matches(review_id,professor_id,area,topic,raw_topic,match_strength,
                        source_id,evidence_quote,reasoning) VALUES(?,?,?,?,?,?,?,?,?)''',
                        (rid,review.professor_id,m.area,m.topic,m.raw_topic,m.match_strength,m.source_id,m.evidence_quote,m.reasoning))
        con.execute('UPDATE professors SET email=?,homepage_url=?,profile_source_id=?,review_state=?,notes=? WHERE id=?',
                    (review.email,review.homepage_url,review.profile_source_id,review.review_state,review.notes,review.professor_id))
    return rid
