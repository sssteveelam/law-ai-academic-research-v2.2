# Database Schema

The initial SQLAlchemy schema is deliberately broader than the first adapter
so later milestones do not require a destructive migration.

Core tables:

- `papers`: canonical paper metadata and provenance, including
  `metadata_sources` and raw external identifiers.
- `authors`, `paper_authors`: normalized author relationships.
- `journals`: normalized journal identity and ISSN values.
- `search_sessions`, `search_results`: reproducible search/run membership.
- `target_journals`: editable whitelist entries and groups.
- `journal_rankings`: imported ranking facts with year/source/subject.
- `download_tasks`, `downloaded_files`: full-text workflow state.
- `keyword_presets`: reusable topic configurations.

No quartile is inferred by the schema. Unknown values remain nullable or
explicitly represented at the domain layer.

M1 persistence creates one `search_sessions` row per run and one
`search_results` row per canonical result. A paper is upserted by normalized
DOI first, then by source identity; author rows are reused by display name.

M2 adds ranking provenance and quality decision fields to `papers`, while
`journal_rankings` stores imported SCImago facts without turning missing data
into a guessed quartile.
Whitelist ISSNs, ISSN-L, aliases, group, and enabled state are persisted in
`target_journals`.

M3 stores download status, source, attempts, progress, error, local path,
checksum, and size in the download tables when a caller persists queue events.
