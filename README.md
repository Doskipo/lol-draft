# lol-draft

Draft recommendation for professional League of Legends: an interpretable,
patch-generalizing win-probability model with fearless-draft awareness.
Built as a learning project (SQL, ML pipelines) and portfolio piece, potentially 
an end-to-end product.

**Status: Phase 0 (data & infrastructure).** Oracle's Elixir ingest is live:
9,534 games / 190,680 ordered draft actions in a normalized DuckDB schema.
Modeling phases not started yet.

## Design docs

- [`PROJECT_SPEC.md`](PROJECT_SPEC.md) — architecture & roadmap (the why/how)
- [`TASKS.md`](TASKS.md) — living task tracker (the what/now)
- [`DECISIONS.md`](DECISIONS.md) — one-line log of design decisions & rationale

## Rebuilding the database

The DB (`data/lol.duckdb`) is derived and disposable — the CSVs are the source
of truth. One command rebuilds it from any state (missing file, dirty DB):

    python src/etl/ingest_oracle.py

Requires:
1. An Oracle's Elixir match CSV in `data/` ([oracleselixir.com](https://oracleselixir.com))
2. A cached Data Dragon snapshot — run once: `python src/etl/fetch_ddragon.py`

The ingest applies `src/db/schema.sql` itself (idempotent), wipes the tables
it owns, and rebuilds. Source-data holes are reported and skipped; broken
pipeline assumptions crash loudly by design.

## Data sources

- **Oracle's Elixir** — pro match data incl. pick/ban order (backbone)
- **Riot Data Dragon** — static champion attributes (pinned snapshot)
- **Leaguepedia** — series structure & player metadata (planned, Phase 0.4)