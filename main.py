"""
KAVERI Backend — Web API (the "front door" for Catalyst AppSail).

Wraps the existing pipeline (components 1-9) as HTTP endpoints. The heavy pipeline
(generate -> load -> graph -> extract -> resolve) runs ONCE at startup and is held in
memory; every request queries the already-built graph (fast).

Endpoints:
  GET  /                      -> health check + info
  GET  /health               -> simple health check
  POST /query                -> natural-language query {"query": "...", "role": "...", "case_id": N}
  GET  /investigate/<case_id> -> full investigation brief for a case
  GET  /identity/<accused_id> -> cross-case identity history for an accused

Catalyst serves this via the startup command (gunicorn/python). Reads PORT from env
(Catalyst sets X_ZOHO_CATALYST_LISTEN_PORT), defaults to 9000 for local testing.
"""
import os, sys, json

# --- make the sibling component folders importable (same pattern as the components) ---
BASE = os.path.dirname(os.path.abspath(__file__))

# VENDORED DEPENDENCIES — Catalyst AppSail does NOT run `pip install -r requirements.txt`.
# Third-party libraries must be bundled with the app, so they live in ./vendor and we put that
# on sys.path BEFORE importing anything third-party (flask, networkx, jellyfish).
sys.path.insert(0, os.path.join(BASE, "vendor"))

for sub in ["01_data_generator","02_relational_layer","03_graph_construction","04_extraction",
            "05_entity_resolution","06_retrieval","07_orchestrator","08_trust_layer","09_burglary_playbook"]:
    sys.path.insert(0, os.path.join(BASE, sub))

from flask import Flask, request, jsonify

# --- import the pipeline pieces ---
from loader import RelationalStore
from graph_store import NetworkXGraphStore
from build_graph import build
from extract import enrich
from resolve import resolve
from orchestrator import Orchestrator
from playbook import BurglaryPlaybook
from trust import AccessControl

app = Flask(__name__)

# ============================================================================
# BUILD THE SYSTEM ONCE AT STARTUP (not per-request)
# ============================================================================
print("[KAVERI] Building the crime intelligence system (one-time startup)...")

# IMPORTANT (Catalyst constraint): AppSail RESTRICTS file writes in the app directory at runtime.
# Therefore the synthetic data CSVs are GENERATED AT BUILD TIME and SHIPPED with the deploy.
# Do NOT generate data here — writing files would fail on Catalyst.
_gen_dir = os.path.join(BASE, "01_data_generator")
if not os.path.exists(os.path.join(_gen_dir, "CaseMaster.csv")):
    raise RuntimeError(
        "Data CSVs missing from 01_data_generator/. Generate them BEFORE deploying "
        "(cd 01_data_generator && python generate.py) and ship them with the app — "
        "Catalyst AppSail does not permit writing files in the app directory at runtime.")

STORE = RelationalStore(db_path=":memory:")
STORE.build(verbose=False)
GRAPH = NetworkXGraphStore()
build(STORE, GRAPH)
enrich(STORE, GRAPH)
_, _, _, GROUPS, _ = resolve(STORE, GRAPH)
ORCH = Orchestrator(STORE, GRAPH, GROUPS)
PLAYBOOK = BurglaryPlaybook(STORE, GRAPH, GROUPS)
ACCESS = AccessControl(STORE)
print(f"[KAVERI] System ready. {len(STORE.get_all_cases())} cases, {len(GROUPS)} resolved identity groups.")


@app.route("/")
def home():
    return jsonify({
        "service": "KAVERI — AI Investigation Copilot for Karnataka State Police",
        "status": "live",
        "cases_loaded": len(STORE.get_all_cases()),
        "resolved_identity_groups": len(GROUPS),
        "endpoints": {
            "POST /query": 'natural-language query — body: {"query":"...","role":"scrb_analyst","case_id":1}',
            "GET /investigate/<case_id>": "full investigation brief for a case",
            "GET /identity/<accused_id>": "cross-case identity history",
            "GET /health": "health check",
        }
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/query", methods=["POST"])
def query():
    data = request.get_json(force=True, silent=True) or {}
    q = data.get("query", "").strip()
    role = data.get("role", "scrb_analyst")
    case_id = data.get("case_id")
    if not q:
        return jsonify({"error": "missing 'query' in request body"}), 400
    try:
        result = ORCH.handle(q, role=role, context_case=case_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"query failed: {type(e).__name__}: {e}"}), 500


@app.route("/investigate/<int:case_id>")
def investigate(case_id):
    try:
        if not STORE.get_case(case_id):
            return jsonify({"error": f"case {case_id} not found"}), 404
        brief = PLAYBOOK.investigate(case_id)
        # brief may contain sets (citations) — make JSON-safe
        return app.response_class(
            json.dumps(brief, default=str, ensure_ascii=False),
            mimetype="application/json")
    except Exception as e:
        return jsonify({"error": f"investigate failed: {type(e).__name__}: {e}"}), 500


@app.route("/identity/<int:accused_id>")
def identity(accused_id):
    try:
        hist = PLAYBOOK.R.cases_for_identity(accused_id)
        return app.response_class(
            json.dumps(hist, default=str, ensure_ascii=False),
            mimetype="application/json")
    except Exception as e:
        return jsonify({"error": f"identity lookup failed: {type(e).__name__}: {e}"}), 500


if __name__ == "__main__":
    # Catalyst provides the port via env var; default 9000 for local testing.
    port = int(os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT", os.environ.get("PORT", 9000)))
    app.run(host="0.0.0.0", port=port)
