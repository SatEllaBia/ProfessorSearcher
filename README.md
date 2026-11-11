# Faculty Atlas

A local faculty application workspace combining Atlas's evidence database with
PhD Scout's directory, shortlist, CSRankings discovery, publication fetchers and
optional local embeddings. SQLite is the single source of truth. AI review uses
your agent and saved pages; no Anthropic or Bedrock account is required.

The supplied HKU AI & Data Science first pass contains **34 faculty: 22 reviewed,
12 partial**, with 77 saved sources. A first-pass review is not a complete
publication audit. Courtesy appointments in the main list are retained; honorary,
emeritus, adjunct and lecturer sections were excluded. Recruitment invitations
and ranks need rechecking for a specific application cycle.

## Start

From this project directory:

```bash
uv sync --locked
uv run faculty serve --port 8080
```

Open http://127.0.0.1:8080. The server binds only to this computer. Directory,
shortlist notes, source viewing and offline review work with the base install.
The lockfile was generated and installation, wheel packaging and real HTTP
integration tests were exercised under Python 3.12.16.

Optional features:

```bash
uv sync --locked --extra semantic       # local embeddings, no paid API
uv sync --locked --extra publications   # upstream public-data fetcher dependencies
uv sync --locked --extra browser        # JavaScript page collection
uv run playwright install chromium
```

Local semantic search downloads the embedding model once into the data directory
unless FASTEMBED_CACHE_PATH is set, then reuses it. It does not rewrite queries or
remove exclusions. The separate exclusion input is an exact phrase filter;
semantic similarity alone does not reliably enforce a negative preference.

## Interest fields and homepage evidence

| Data | Storage | Meaning |
|---|---|---|
| Source interests | `source_interests.text` | Verbatim wording from a saved source; no AI paraphrase |
| AI interests | `reviews.interests_ai` | AI-authored interpretation, supported by `interest_evidence` |
| Topic matches | `research_matches` | Area/topic, raw subject, fit and explained interpretation |
| Institutional profile | `affiliations.official_profile_url` | The university/department's profile |
| Homepage findings | `homepage_findings` | AI-reviewed personal, lab or institutional page with URL evidence |
| Selected homepage | `professors.homepage_url` | Best current homepage choice; its evidence state is displayed |
| My shortlist notes | `application_list.notes` | User notes, independent of AI review notes |

“Source” describes the wording, not a promise that AI never selected the excerpt.
Selection methods are retained: parser, manual, verbatim selection, or legacy
quote. CSRankings-derived areas are attributed to the downloaded metadata; they
are not presented as the professor's own research statement.

A personal homepage can be hosted at HKU, including a `~username` page. The
reviewer establishes page identity from its contents and institutional links;
it does not classify pages by domain. Official profile, personal and lab pages
remain separate, even on the same host. A new version 2 selected homepage needs
a finding with an exact quote and a URL present in a checked text/HTML link or
in the identity-confirmed source's URL. Use an institutional profile as a labeled
fallback if a separate personal site cannot be established.

Migration preserves all version 1 reviews and source snapshots. Existing quoted
research evidence is exposed as original source wording with `legacy_quote`;
existing topic explanations are exposed as AI interests with their original
evidence. Existing homepage links are retained as `legacy_unverified` until a
version 2 finding establishes their evidence. No original source text is rewritten.

## Review downloaded pages with your agent

The project instructions are in `skills/review-faculty/SKILL.md`. They travel with
the project and do not require installing a global skill or connecting an API.

```bash
uv run faculty prepare --out work/review-packets
```

Each `NNN.json` packet contains the professor, current assessment, saved page
text, absolute local text/HTML paths, resolved HTML links, source IDs, retrieval
times and hashes. `review-schema.json` defines the output. Absolute paths are
machine-specific; regenerate packets after moving or extracting the project.

Example instruction for an agent:

> Use skills/review-faculty/SKILL.md to review professor 3 in
> work/review-packets/003.json. Read the downloaded sources first and return a
> complete version 2 review JSON. Fetch only genuinely missing or stale sources.

Then validate and import:

```bash
uv run faculty review-import work/review.json
uv run faculty export --out reports/hku-ai.md
```

A review is a complete replacement of the current assessment, not a patch.
Previous reviews remain stored. `interests_source` holds source ID + exact
`evidence_quote`; `interests_ai` requires separate `interest_evidence`.
`homepages` holds URL, kind, source ID, quote and reasoning. Keep separate PhD
and MPhil signals. The browser's AI review tab prepares packets and imports the
same schema through the same validator.

## Collection and caching

```bash
uv run faculty fetch https://example.edu/profile
uv run faculty source-link PROFESSOR_ID SOURCE_ID --role profile
uv run faculty collect --limit 5
uv run faculty prepare --out work/review-packets
```

Successful downloaded HTML is reused unless `--refresh` is requested. Existing
web extracts can be read offline by reviewers; `fetch` obtains raw HTML when an
HTML collection operation specifically needs it. Failed downloads remain distinct
from unknown recruitment. To import a page saved with another tool:

```bash
uv run faculty source-add saved-page.html --url https://example.edu/profile --html
uv run faculty source-link PROFESSOR_ID SOURCE_ID --role homepage_candidate
```

Use `--browser` with fetch/collect for JavaScript pages. The collector is bounded:
profile plus at most four linked homepage/recruitment candidates. It saves raw
HTML and extracted text and records failures instead of treating challenge pages
as evidence. Original first-pass snapshots labeled `web_extract` are retrieved
text, not raw HTML, and can omit parts of long pages.

## Discover and import candidates

Use Discover in the browser, or:

```bash
uv run faculty discovery --country hk --query 'University of Hong Kong' --out work/discovery.json
uv run faculty discovery-import work/discovery.json
```

Inspect the candidates before import. Downloaded CSVs are saved in
`data/discovery-cache/` and reused until `discovery --refresh`. Same-homepage
aliases within an institution are grouped; exact known homepage/profile URLs
and known Scholar IDs reuse existing identities. Do not rely on fuzzy name
merging. Distinct URLs can still require manual identity review.

CSRankings is a discovery source, not a list of confirmed current AI-division
professors. Imported candidates are pending and their rank/department are marked
as not supplied. Its homepage does not automatically become an official profile.
All source-derived interests remain attributed to the saved candidate record.

The reused optional publication fetchers are in `faculty_atlas/scout/fetchers.py`.
Their OpenAlex fallback and surname-only arXiv lookup can mix people. They are
retained for future verified enrichment, and are not automatically invoked on
import or treated as verified publications. The paid Claude synthesis pipeline
and the separate Scout database are not used.

## CLI reference

Global `--data PATH` must precede the subcommand; default is `data/`.

| Command | Purpose |
|---|---|
| `init`, `status` | Initialize/migrate or inspect the database |
| `serve --port 8080` | Run the local web interface |
| `list --area agents --degree PhD --status 2` | Filter current supported research matches |
| `fetch URL [--refresh] [--browser]` | Cache a public page or record failure |
| `discover [--source ID]` | Enumerate HKU faculty from a saved directory |
| `collect [--limit N]` | Fetch profiles and bounded linked pages |
| `source-add FILE --url URL [--html]` | Add a downloaded source |
| `source-link PROFESSOR_ID SOURCE_ID` | Associate a source with a professor |
| `source-import FILE`, `seed-import FILE` | Import source records or directory records |
| `interests-add PROFESSOR_ID --source ID --text TEXT` | Add an exact original source excerpt |
| `prepare --out PATH` | Prepare offline packets and the review schema |
| `review-schema --out FILE` | Export the current JSON schema |
| `review-import FILE` | Validate and import complete reviewed JSON |
| `discovery`, `discovery-import FILE` | Preview/cache and import CSRankings candidates |
| `export --out FILE` | Generate a Markdown report |

Recruitment: `-1` explicitly closed, `0` unknown after review, `1` possible,
`2` explicit invitation. PhD and MPhil are independent; generic invitations can
also use `unspecified`. Preserve dated and contradictory evidence. A failed or
unchecked page is not status 0. Invitations do not guarantee funded vacancies.
Fit is 0 outside the requested interests, 1 adjacent, 2 clear, 3 direct. Every
area has an `other` topic. AI for smoke-simulation acceleration can therefore be
`ai_graphics.other` without losing the specific original research description.

## Verify and restore

```bash
uv run python -m unittest discover -s tests -v
uv run python scripts/check_data.py
uv run python scripts/rebuild_database.py --out work/restored.sqlite
```

Keep `data/snapshots/` with the database/dump. Rebuild refuses to overwrite an
existing database. `schema_version` tracks additive migrations; version 2 adds
interest separation, homepage findings, application notes and local embeddings.

## Code provenance

`faculty_atlas/scout/` reuses PhD Scout's MIT-licensed discovery, publication and
embedding modules. The UI reuses its stylesheet and directory/shortlist workflow;
the server adapts its threaded HTTP approach to Atlas's schema. Attribution,
upstream commit and license are in `third_party/phd-scout/`. The original project
and the evaluation checkout outside this combined directory are unchanged.
