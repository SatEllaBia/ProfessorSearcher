"""Additive, idempotent upgrades preserving the v1 evidence and review history."""
import json

def migrate(con):
    if not con.execute('SELECT 1 FROM schema_version WHERE version=2').fetchone():
        with con:
            cols = {r[1] for r in con.execute('PRAGMA table_info(reviews)')}
            if 'interests_ai' not in cols:
                con.execute("ALTER TABLE reviews ADD COLUMN interests_ai TEXT NOT NULL DEFAULT ''")
            con.executescript('''
                CREATE TABLE IF NOT EXISTS source_interests(
                    id INTEGER PRIMARY KEY, professor_id INTEGER NOT NULL REFERENCES professors(id),
                    source_id INTEGER NOT NULL REFERENCES sources(id), text TEXT NOT NULL CHECK(length(trim(text))>0),
                    method TEXT NOT NULL CHECK(method IN ('parser','manual','verbatim_selection','legacy_quote')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(professor_id,source_id,text));
                CREATE TABLE IF NOT EXISTS interest_evidence(
                    review_id INTEGER NOT NULL REFERENCES reviews(id), source_id INTEGER NOT NULL REFERENCES sources(id),
                    evidence_quote TEXT NOT NULL, PRIMARY KEY(review_id,source_id,evidence_quote));
                CREATE TABLE IF NOT EXISTS homepage_findings(
                    id INTEGER PRIMARY KEY, review_id INTEGER NOT NULL REFERENCES reviews(id),
                    professor_id INTEGER NOT NULL REFERENCES professors(id), url TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('personal','lab','institutional_profile')),
                    source_id INTEGER NOT NULL REFERENCES sources(id), evidence_quote TEXT NOT NULL,
                    reasoning TEXT NOT NULL, UNIQUE(review_id,url,kind));
                CREATE TABLE IF NOT EXISTS application_list(
                    professor_id INTEGER PRIMARY KEY REFERENCES professors(id), rank INTEGER NOT NULL,
                    notes TEXT NOT NULL DEFAULT '', added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS semantic_embeddings(
                    professor_id INTEGER NOT NULL REFERENCES professors(id), model TEXT NOT NULL,
                    content_hash TEXT NOT NULL, embedding BLOB NOT NULL,
                    PRIMARY KEY(professor_id,model));
                CREATE TABLE IF NOT EXISTS external_ids(
                    scheme TEXT NOT NULL, value TEXT NOT NULL, professor_id INTEGER NOT NULL REFERENCES professors(id),
                    PRIMARY KEY(scheme,value));
            ''')
            # These are old AI-selected quotations, not newly authored source descriptions.
            con.execute('''INSERT OR IGNORE INTO source_interests(professor_id,source_id,text,method)
                SELECT DISTINCT professor_id,source_id,evidence_quote,'legacy_quote'
                FROM research_matches WHERE length(trim(evidence_quote))>0''')
            for row in con.execute('SELECT id FROM reviews').fetchall():
                matches = con.execute('SELECT raw_topic,reasoning,source_id,evidence_quote FROM research_matches WHERE review_id=?',(row['id'],)).fetchall()
                con.execute('UPDATE reviews SET interests_ai=? WHERE id=?',
                    ('\n'.join(f"{m['raw_topic']}: {m['reasoning']}" for m in matches),row['id']))
                con.executemany('INSERT OR IGNORE INTO interest_evidence VALUES(?,?,?)',
                    [(row['id'],m['source_id'],m['evidence_quote']) for m in matches])
            con.execute('INSERT INTO schema_version VALUES(2)')

