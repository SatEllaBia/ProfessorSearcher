# Review output

Read the generated `review-schema.json` for the authoritative model. A complete version 2 object uses:

```json
{
  "format_version": 2,
  "professor_id": 1,
  "review_state": "partial",
  "checked_source_ids": [10],
  "profile_source_id": 10,
  "email": null,
  "homepage_url": null,
  "homepages": [],
  "interests_source": [
    {"source_id": 10, "evidence_quote": "EXACT ORIGINAL WORDING", "method": "verbatim_selection"}
  ],
  "interests_ai": "An interpretation supported by the cited source.",
  "interest_evidence": [
    {"source_id": 10, "evidence_quote": "EXACT ORIGINAL WORDING"}
  ],
  "notes": "Explain material gaps or timing uncertainty.",
  "recruitment_signals": [
    {"degree": "PhD", "status": 0, "source_id": 10, "reasoning": "No degree-specific invitation in the checked source."},
    {"degree": "MPhil", "status": 0, "source_id": 10, "reasoning": "No MPhil statement in the checked source."}
  ],
  "research_matches": []
}
```

This is a structural illustration with placeholder IDs/quotes; replace them with real packet evidence. Leave an unknown original description or AI description empty instead of inventing one. A populated AI description requires `interest_evidence`.

A homepage finding uses:

```json
{
  "url": "https://example.edu/~professor/",
  "kind": "personal",
  "source_id": 10,
  "evidence_quote": "Personal homepage",
  "reasoning": "The identity-confirmed institutional profile links this personal page."
}
```

A research match requires `area`, `topic`, `raw_topic`, `match_strength` (0–3), `source_id`, `evidence_quote`, and `reasoning`. Consult `faculty_atlas/db.py:TOPICS` or the generated schema/database for allowed topics. A fit of 3 means direct, 2 clear, 1 adjacent, 0 outside the requested interests. Never treat a score as an externally established fact.

The existing source text stays unchanged. The `method` describes how an excerpt was selected: `parser`, `manual`, or `verbatim_selection`. `legacy_quote` in the database denotes exact quotations selected during the previous AI-assisted first pass.
