PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS sources(
 id INTEGER PRIMARY KEY, url TEXT NOT NULL, final_url TEXT NOT NULL,
 fetched_at TEXT NOT NULL, published_at TEXT, http_status INTEGER,
 fetch_method TEXT NOT NULL CHECK(fetch_method IN ('http','playwright','web_extract','manual')),
 state TEXT NOT NULL CHECK(state IN ('ok','failed')),
 content_hash TEXT, html_path TEXT, text_path TEXT, error TEXT,
 UNIQUE(url, content_hash, fetch_method)
);
CREATE TABLE IF NOT EXISTS professors(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL,
 identity_url TEXT NOT NULL UNIQUE, email TEXT, homepage_url TEXT,
 profile_source_id INTEGER REFERENCES sources(id),
 review_state TEXT NOT NULL DEFAULT 'pending' CHECK(review_state IN ('pending','partial','reviewed')),
 notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS affiliations(
 id INTEGER PRIMARY KEY, professor_id INTEGER NOT NULL REFERENCES professors(id),
 university TEXT NOT NULL, school TEXT, department TEXT NOT NULL,
 title TEXT NOT NULL, appointment_year INTEGER,
 official_profile_url TEXT NOT NULL, source_id INTEGER NOT NULL REFERENCES sources(id),
 UNIQUE(professor_id, university, department)
);
CREATE TABLE IF NOT EXISTS professor_sources(
 professor_id INTEGER NOT NULL REFERENCES professors(id),
 source_id INTEGER NOT NULL REFERENCES sources(id), role TEXT NOT NULL,
 PRIMARY KEY(professor_id, source_id, role)
);
CREATE TABLE IF NOT EXISTS topics(
 area TEXT NOT NULL, topic TEXT NOT NULL, PRIMARY KEY(area,topic)
);
CREATE TABLE IF NOT EXISTS reviews(
 id INTEGER PRIMARY KEY, professor_id INTEGER NOT NULL REFERENCES professors(id),
 reviewed_at TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('partial','reviewed')),
 notes TEXT NOT NULL, payload_hash TEXT NOT NULL,
 UNIQUE(professor_id,payload_hash)
);
CREATE TABLE IF NOT EXISTS review_sources(
 review_id INTEGER NOT NULL REFERENCES reviews(id), source_id INTEGER NOT NULL REFERENCES sources(id),
 PRIMARY KEY(review_id,source_id)
);
CREATE TABLE IF NOT EXISTS recruitment_signals(
 id INTEGER PRIMARY KEY, review_id INTEGER NOT NULL REFERENCES reviews(id),
 professor_id INTEGER NOT NULL REFERENCES professors(id),
 degree TEXT NOT NULL CHECK(degree IN ('PhD','MPhil','unspecified')),
 status INTEGER NOT NULL CHECK(status IN (-1,0,1,2)),
 intake TEXT, temporal_state TEXT NOT NULL CHECK(temporal_state IN ('undated','current','past','unclear')),
 source_id INTEGER NOT NULL REFERENCES sources(id), evidence_quote TEXT NOT NULL,
 reasoning TEXT NOT NULL,
 CHECK(status=0 OR length(trim(evidence_quote))>0)
);
CREATE TABLE IF NOT EXISTS research_matches(
 id INTEGER PRIMARY KEY, review_id INTEGER NOT NULL REFERENCES reviews(id),
 professor_id INTEGER NOT NULL REFERENCES professors(id),
 area TEXT NOT NULL, topic TEXT NOT NULL, raw_topic TEXT NOT NULL,
 match_strength INTEGER NOT NULL CHECK(match_strength BETWEEN 0 AND 3),
 source_id INTEGER NOT NULL REFERENCES sources(id), evidence_quote TEXT NOT NULL CHECK(length(trim(evidence_quote))>0),
 reasoning TEXT NOT NULL,
 FOREIGN KEY(area,topic) REFERENCES topics(area,topic)
);
CREATE INDEX IF NOT EXISTS source_url_idx ON sources(url);
CREATE INDEX IF NOT EXISTS review_professor_idx ON reviews(professor_id,id);
CREATE VIEW IF NOT EXISTS current_reviews AS
 SELECT * FROM reviews WHERE id IN (SELECT max(id) FROM reviews GROUP BY professor_id);
