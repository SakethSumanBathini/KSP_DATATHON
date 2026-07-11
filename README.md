# KAVERI — AI Investigation Copilot for Karnataka State Police

**🔗 LIVE DEPLOYMENT (Catalyst):** https://kaveri-backend-50043711203.development.catalystappsail.in

Try it:
- [`/`](https://kaveri-backend-50043711203.development.catalystappsail.in/) — service status
- [`/investigate/1`](https://kaveri-backend-50043711203.development.catalystappsail.in/investigate/1) — full cited investigation brief
- [`/identity/17`](https://kaveri-backend-50043711203.development.catalystappsail.in/identity/17) — cross-case identity (Kannada name variants resolved)

---

A crime-intelligence system that creates the **cross-case person identity the FIR schema lacks**,
extracts entities (phones/vehicles/UPI) from free-text narratives, and produces **cited, auditable
investigation briefs**. Built for the KSP Datathon (Challenge 01).

## The two structural problems it solves
1. **No global person identity.** The same offender across 5 FIRs is 5 disconnected `Accused` rows.
   SQL cannot link them. KAVERI resolves them — including Kannada spelling variants
   (ರಾಮಯ್ಯ.ಕೆ / Ramaiah K / ರಾಮು → one person).
2. **Evidence trapped in free text.** Phones, vehicles, and UPI IDs exist only inside `BriefFacts`
   narrative text, invisible to SQL. KAVERI extracts them and links cases through them.

## Quick start (local)
```bash
pip install -r requirements.txt

cd 01_data_generator      && python generate.py     # synthetic FIRs + ground truth
cd ../02_relational_layer && python loader.py       # schema-enforced load
cd ../03_graph_construction && python build_graph.py # Crime Intelligence Graph
cd ../04_extraction       && python extract.py      # entities from BriefFacts
cd ../05_entity_resolution && python resolve.py     # cross-case identity (the moat)
cd ../06_retrieval        && python retrieval.py    # graph + semantic retrieval
cd ../07_orchestrator     && python orchestrator.py # query -> cited answer
cd ../08_trust_layer      && python trust.py        # RBAC + immutable audit
cd ../09_burglary_playbook && python playbook.py    # full investigation brief

# Run the web API locally:
python main.py            # then open http://localhost:9000/investigate/1
```

## Architecture — 10 components
Data flows strictly downstream: 1 → 2 → 3 → 4 → 5 → 6 → 7, with 8 (trust) wrapping the
orchestrator, 9 (playbook) chaining everything, and 10 (frontend) on top.

| # | Component | What it does | Key file |
|---|-----------|--------------|----------|
| 1 | Data Generator | Schema-accurate synthetic FIRs + ground_truth.json | generate.py |
| 2 | Relational Layer | Schema-enforced load, parameterized data-access API | loader.py |
| 3 | Graph Construction | Crime Intelligence Graph (NetworkX + Neo4j backends) | build_graph.py, graph_store.py |
| 4 | Entity Extraction | Phones/vehicles/UPI from BriefFacts, cited to source span | extract.py |
| 5 | Entity Resolution | Cross-case identity (**the moat**) — measured precision/recall | resolve.py |
| 6 | Retrieval | Graph traversal + semantic MO search (dependency-free TF-IDF) | retrieval.py, pure_tfidf.py |
| 7 | Orchestrator | Query → intent → retrieve → narrate → cite → audit | orchestrator.py, llm_interface.py |
| 8 | Trust Layer | RBAC (data-layer) + hash-chained immutable audit + PII masking | trust.py |
| 9 | Burglary Playbook | Chains all → cited Investigation Brief | playbook.py |
| 10 | Frontend | React copilot UI (chat, network, brief, trust) | kaveri_frontend.jsx |
| — | **Web API** | Serves components 1–9 over HTTP (deployed on Catalyst AppSail) | **main.py** |

## Entity Resolution — the honest numbers
**Precision 1.000, Recall 1.000, F1 1.000** on the synthetic benchmark, *including* 5 pairs of
deliberately confusable **different** people that a naive resolver would wrongly merge:

| Pair | Name similarity | Correctly kept separate? |
|---|---|---|
| "Suresh Kumar" (35) vs "Suresh Kumara" (36) | **1.000** | ✅ |
| "Manjunath Gowda" (41) vs "Manjunatha Gowda" (42) | 0.980 | ✅ |
| "Ramesh Naik" (29) vs "Ramesh Naika" (30) | 1.000 | ✅ |
| "Prakash B" (47) vs "Prakash Bhat" (48) | 1.000 | ✅ |
| "Nagaraj R" (52) vs "Nagaraja R" (53) | 0.975 | ✅ |

**Why they don't merge:** a merge requires a *shared distinguishing entity* (e.g. a common phone),
not name similarity alone. Name-only matches are routed to **human review**, never auto-merged.

**⚠️ HONEST CAVEAT:** 1.000 is measured on synthetic data. It proves the **mechanism** —
that the resolver rejects the tempting wrong answer — **not a real-world accuracy claim.**
Real-world numbers will differ; no real Karnataka police data exists for validation.
See `05_entity_resolution/STATUS.md`.

## Security posture (audited)
- No hardcoded secrets; Neo4j credentials via env vars.
- SQL fully parameterized; Cypher labels/rel-types allowlisted (injection-guarded).
- RBAC enforced at the **data layer**, **fails closed** on unknown roles; verified zero
  cross-jurisdiction leakage (station officer 30 cases < district SP 132 < SCRB 500).
- Immutable audit is tamper-evident — detects modify, delete, AND swap (verified by tampering).
- **The LLM is never the authorization boundary. The data layer is.**

## Production path (stand-ins → real services, all one-line swaps)
| Now | Production | How |
|---|---|---|
| NetworkX (in-process) | **Neo4j** | Full Cypher already in `graph_store.py`; run as a container, set `NEO4J_*` env vars |
| Pure TF-IDF | **Multilingual embeddings + Qdrant** | `KAVERI_USE_EMBEDDINGS=1` (pre-cache model) |
| Template narrator | **Catalyst QuickML served LLM** | Set `CATALYST_LLM_ENDPOINT` + `CATALYST_LLM_TOKEN` |
| In-memory audit chain | **Catalyst NoSQL** | Pass `persist_fn` to `ImmutableAudit` |

Language discipline: this is **Investigative Intelligence**, never "predictive policing."
Every claim is cited to source FIRs. A human officer verifies before any action.
