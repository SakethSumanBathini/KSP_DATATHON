# KAVERI — AI Investigation Copilot for Karnataka State Police

A crime-intelligence system that creates the cross-case person identity the FIR schema lacks,
extracts entities (phones/vehicles/UPI) from free-text narratives, and produces cited,
auditable investigation briefs. Built for the KSP Datathon (Challenge 01).

## Quick start
```bash
pip install -r requirements.txt
# Run the full pipeline in order (each component prints its verification output):
cd 01_data_generator      && python3 generate.py       # generate synthetic FIRs + ground truth
cd ../02_relational_layer && python3 loader.py          # load into schema-enforced DB
cd ../03_graph_construction && python3 build_graph.py   # build the Crime Intelligence Graph
cd ../04_extraction       && python3 extract.py         # extract entities from BriefFacts
cd ../05_entity_resolution && python3 resolve.py        # resolve cross-case identities (the moat)
cd ../06_retrieval        && python3 retrieval.py       # hybrid graph + semantic retrieval
cd ../07_orchestrator     && python3 orchestrator.py    # query -> cited answer
cd ../08_trust_layer      && python3 trust.py           # RBAC + immutable audit
cd ../09_burglary_playbook && python3 playbook.py       # full investigation brief
# Frontend (component 10): open 10_frontend/kaveri_frontend.jsx in any React environment.
```

## Architecture — 10 components, a clean pipeline
Each component is a self-contained folder. Data flows strictly downstream: 1 → 2 → 3 → 4 → 5 → 6 → 7,
with 8 (trust) wrapping the orchestrator, 9 (playbook) chaining everything, and 10 (frontend) on top.

| # | Component | What it does | Key file |
|---|-----------|--------------|----------|
| 1 | Data Generator | Schema-accurate synthetic FIRs + ground_truth.json | generate.py |
| 2 | Relational Layer | Schema-enforced load, parameterized data-access API | loader.py |
| 3 | Graph Construction | Crime Intelligence Graph (dual backend: NetworkX + Neo4j) | build_graph.py, graph_store.py |
| 4 | Entity Extraction | Phones/vehicles/UPI from BriefFacts, cited to source span | extract.py |
| 5 | Entity Resolution | Cross-case identity (the moat) — measured precision/recall | resolve.py, transliteration.py |
| 6 | Retrieval | Hybrid graph traversal + semantic MO search | retrieval.py |
| 7 | Orchestrator | Query → intent → retrieve → narrate → cite → audit | orchestrator.py, llm_interface.py |
| 8 | Trust Layer | RBAC (data-layer) + hash-chained immutable audit + PII masking | trust.py |
| 9 | Burglary Playbook | Chains all → cited Investigation Brief | playbook.py |
| 10 | Frontend | React copilot UI (chat, network, brief, trust) | kaveri_frontend.jsx |

## How the imports work (read this before moving files)
Each component adds its sibling folders to `sys.path` at the top of its main file, so it can import
upstream components directly (e.g. the orchestrator imports from 02–06). This keeps each folder
runnable on its own. **If you move or rename a folder, update the `sys.path.insert` lines** at the
top of the downstream files. (For a production package, replace this with a proper installable
package / `pyproject.toml` — noted as future work.)

## Verifiable stand-ins vs production (all clearly marked in code)
This repo runs end-to-end WITHOUT external services, using stand-ins that prove the logic. Each has
a documented one-line swap to the production service:
- Graph: NetworkX (in-process) → **Neo4j** on Catalyst AppSail (full Cypher in graph_store.py)
- Transliteration: rule-based → **AI4Bharat IndicXlit**
- Semantic search: TF-IDF → **sentence-transformer/IndicBERT embeddings in Qdrant**
- LLM narration: deterministic template → **Catalyst QuickML served model** (prompt in llm_interface.py)
- Audit store: in-memory hash chain → **Catalyst NoSQL** append-only (hash-chaining logic transfers)

## Honesty on the numbers
Entity resolution scores 1.000 precision/recall **on synthetic data designed to be resolvable** —
this proves the mechanism, NOT a real-world accuracy claim. See 05_entity_resolution/STATUS.md for the
honest framing to present to judges. Extraction hit-rate is 100% on controlled synthetic formats and
will be lower on real FIRs. Every claim in every brief is cited to source FIRs for human verification.

## Security posture (audited)
- No hardcoded secrets; Neo4j credentials via env vars.
- SQL fully parameterized; Cypher labels/rel-types allowlisted (injection-guarded).
- RBAC enforced at the DATA layer, fails closed on unknown roles; verified no cross-jurisdiction leak.
- Immutable audit is tamper-evident (detects modify/delete/swap). Production needs infra-level append-only.
- The LLM is NEVER the authorization boundary — the data layer is.
