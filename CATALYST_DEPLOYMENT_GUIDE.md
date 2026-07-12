# KAVERI — Catalyst Deployment & Validation Guide

## The big question: deploy now, or after the frontend?

**Answer: deploy the BACKEND now (this week). Deploy the FRONTEND after your friend restyles it.**

Reason: they're independent. The backend (components 1–9) is an API/service — your friend's
frontend restyling can't affect it, and getting the backend deployed early de-risks the mandatory
requirement. The frontend deploys separately (Catalyst Slate/Web Client Hosting) once it's styled.
Doing backend-first means: if deployment hits snags (it will — container limits, timeouts), you find
out with 3 weeks left, not 3 days. **Deployment is pass/fail for the whole submission — treat it as
the critical path, not the last step.**

Sequence:
1. NOW → deploy backend to Catalyst, get the API live (this guide).
2. TOMORROW → hand frontend to your friend; he restyles `10_frontend/kaveri_frontend.jsx`.
3. LATER → point his styled frontend at the live backend API, deploy frontend to Slate.
4. Record demo, write brief + deck.

---

## Gap closures — what's code (done) vs what's deployment (you do)

All gap code is written with a PRODUCTION path + safe FALLBACK. Setting env vars + deploying
flips each from fallback to production. No code changes needed.

| Gap | Code status | To activate in production |
|-----|-------------|---------------------------|
| 1 Neo4j | ✅ written (graph_store.py) | Run Neo4j container on AppSail; set NEO4J_URI/USER/PASSWORD; use Neo4jGraphStore() |
| 2 Embeddings | ✅ written (retrieval.py) | Open internet auto-downloads multilingual model; optionally back with Qdrant |
| 3 LLM | ✅ written (llm_interface.py) | Set CATALYST_LLM_ENDPOINT + CATALYST_LLM_TOKEN; narration goes live |
| 4 Audit persist | ✅ written (trust.py) | Pass persist_fn writing to Catalyst NoSQL; add infra append-only |
| 5 ER benchmark | ✅ CLOSED (hardened) | Nothing — done. Present with STATUS.md framing |

---

## Step-by-step Catalyst deployment (backend)

### 0. Prereqs
- Claim Catalyst credits: https://catalyst.zoho.com/promotions.html?cn=KSPH26
- Install Catalyst CLI, `catalyst login`.

### 1. Neo4j container on AppSail (Gap 1)
- Package Neo4j as a Docker image, deploy to Catalyst AppSail (custom OCI runtime).
- Note the 30-second function/AppSail request timeout — Neo4j itself is fine (it's a service);
  just ensure heavy graph BUILDS run as a Job (step 4), not in a request.
- Set env vars in Catalyst console: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD.
- In build_graph.py, switch `NetworkXGraphStore()` → `Neo4jGraphStore()`.

### 2. Data Store (relational) — Component 2
- Create Catalyst Data Store tables matching schema.py.
- Point the loader at Data Store instead of SQLite (the data-access API stays identical).

### 3. Serve the LLM (Gap 3)
- Use Catalyst QuickML to serve the model; copy the inference endpoint + token.
- Set CATALYST_LLM_ENDPOINT + CATALYST_LLM_TOKEN. Narration goes live automatically.
- Adjust the response-key parsing in CatalystLLMNarrator.narrate() to match your endpoint's JSON.

### 4. Heavy pipeline as a Job (the timeout rule)
- The full generate→load→graph→extract→resolve pipeline exceeds 30s. Run it as a Catalyst
  Job (Job Scheduling, 15-min limit), triggered once to seed the graph. The API then serves
  queries against the already-built graph (fast, under 30s).

### 5. Orchestrator as the API (Component 7)
- Deploy the orchestrator as an AppSail web app / Function behind API Gateway.
- Each query (similar/network/identity/filter) returns in well under 30s against the built graph.

### 6. Auth + RBAC (Component 8)
- Wire Catalyst Authentication for login; map users to roles (station_officer, etc.).
- Audit: pass persist_fn = write-to-Catalyst-NoSQL. (Gap 4)

### 7. Embeddings (Gap 2)
- On Catalyst (open internet), the multilingual model downloads on first run. For scale, stand up
  Qdrant as a container and store vectors there (optional; in-process works for the demo).

---

## How to RUN it (locally, before deploying)
```bash
pip install -r requirements.txt
cd 01_data_generator && python3 generate.py
cd ../02_relational_layer && python3 loader.py
cd ../03_graph_construction && python3 build_graph.py
cd ../04_extraction && python3 extract.py
cd ../05_entity_resolution && python3 resolve.py
cd ../06_retrieval && python3 retrieval.py
cd ../07_orchestrator && python3 orchestrator.py
cd ../08_trust_layer && python3 trust.py
cd ../09_burglary_playbook && python3 playbook.py
```

## How to VALIDATE it (the checks that matter)
1. **ER score**: `cd 05_entity_resolution && python3 resolve.py` → expect PRECISION=1.000 RECALL=1.000,
   and "Hard decoys wrongly merged: 0/5". If those hold, resolution is sound.
2. **Security**: `cd 08_trust_layer && python3 trust.py` → expect RBAC hierarchy PASS, cross-jurisdiction
   DENIED, tampering "detected", uncited claim "BLOCKED".
3. **Full brief**: `cd 09_burglary_playbook && python3 playbook.py` → expect a complete Investigation
   Brief with network, near-repeat, repeat offender, and cited FIRs.
4. **Determinism**: run generate.py twice → CSVs identical (reproducible).
5. **No secrets**: `grep -rniE "password|token|secret.*=.*['\"]" --include="*.py" .` → only env-var refs.

## How to CHECK before pushing to GitHub
- `.gitignore` is in place (no __pycache__, no .env, no secrets).
- Confirm no real credentials anywhere: the repo should have ZERO tokens/keys.
- README.md + this guide + each component's README/STATUS are present.
