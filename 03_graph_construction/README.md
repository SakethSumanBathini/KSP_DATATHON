# Component 3 — Crime Intelligence Graph Construction

Builds the graph from Component 2's data-access API. TWO backends, one interface:
- `NetworkXGraphStore` — in-process, runs/verifies in any environment (used to prove logic here).
- `Neo4jGraphStore` — production backend for containerized Neo4j on Catalyst AppSail. Full Cypher included.
  Credentials via env vars NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD — never hardcoded.

## Run (verifiable, no Neo4j needed)
```
python3 build_graph.py
```
To target Neo4j: `pip install neo4j`, set the env vars, swap `NetworkXGraphStore()` for `Neo4jGraphStore()`.

## Nodes / Edges
Nodes: FIR, Person, Location, PoliceStation, District, Section, Victim, Complainant.
Edges: ACCUSED_IN, VICTIM_IN, COMPLAINANT_IN, REGISTERED_AT, OCCURRED_AT, IN_DISTRICT, CHARGED_UNDER.

## CRITICAL BOUNDARY (verified)
One Person node per Accused row. **No cross-case merging.** Verified: 635 Person nodes = 635 Accused rows.
The Kannada-variant person (Set C) is 3 SEPARATE nodes, correctly unmerged — resolution is Component 5's job.
Every Person node retains source_case_id + accused_master_id (provenance for citations & resolution).
