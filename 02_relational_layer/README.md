# Component 2 — Relational Data Layer

Loads Component 1's CSVs into a schema-enforced relational store with FK integrity,
and exposes a clean parameterized data-access API for Components 3 & 4.

## Run
```
python3 loader.py          # load + contract check + FK integrity report
```
Default target is in-memory SQLite. For a persistent DB: `RelationalStore(db_path="ksp.db")`.
Designed to swap to Catalyst Data Store for deployment (same access-API surface).

## Boundary contract (the seam guard)
Before loading, `_check_contract()` validates every CSV's column header against the
expected column list in `schema.py`. If Component 1's output columns don't match what
Component 2 expects, it raises `ContractViolation` and HALTS — no silent assumption.
Verified result on Component 1 output: **all contract checks passed, 0 FK violations, 3085 rows.**

## Data-access API (Components 3 & 4 use ONLY this — never raw CSV)
`get_all_cases, get_case, get_accused_for_case, get_victims_for_case,
get_complainants_for_case, get_sections_for_case, get_arrests_for_accused,
get_station, get_district_for_case, all_accused`
All queries parameterized (no string-concatenated SQL).

## What this component proves about the architecture
The relational layer can show two cases share an accused NAME but cannot know they are the
same PERSON (different AccusedMasterIDs). Creating that cross-case identity is the job of
the graph (Component 3) and entity resolution (Component 5). This limitation is the reason
the graph layer exists.

## Security notes (carried forward)
- Parameterized queries only (injection-safe at this layer).
- Per-table scopes/permissions and query-level RBAC are enforced in the orchestrator (Component 7/8), not here.
- No secrets in code; DB path/credentials via env vars when targeting Catalyst.
