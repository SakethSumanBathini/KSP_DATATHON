"""
Component 7 — Orchestrator (the brain).
Flow: query -> intent classification -> retrieval dispatch (Component 6) -> narration
(Component 7a) -> CITATION attachment -> AUDIT log (pre+post) -> response.

The orchestrator enforces two trust invariants on EVERY query:
  1. CITATIONS: every response carries the source FIR ids the answer is built from.
  2. AUDIT: every query + response is logged (who, when, intent, cases touched).
(Component 8 extends this with full RBAC + immutable audit store. Here the hooks are in place.)

Intent classification here is RULE-BASED (keyword routing) — transparent and debuggable.
Production may add an LLM intent classifier behind the same interface.
"""
import sys, os, json, re, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"02_relational_layer"))
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"03_graph_construction"))
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"04_extraction"))
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"05_entity_resolution"))
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"06_retrieval"))
from loader import RelationalStore
from graph_store import NetworkXGraphStore
from build_graph import build
from extract import enrich
from resolve import resolve
from retrieval import Retriever
from llm_interface import LLMNarrator, get_narrator

class AuditLog:
    """Hook for the immutable audit store (Component 8 / Catalyst NoSQL). Here: in-memory list."""
    def __init__(self): self.entries = []
    def record(self, user, role, query, intent, cases_touched, response_summary):
        self.entries.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "user": user, "role": role, "query": query, "intent": intent,
            "cases_touched": cases_touched, "response_chars": len(response_summary)})
    def dump(self): return self.entries

class Orchestrator:
    def __init__(self, store, graph, resolved_groups):
        self.R = Retriever(store, graph, resolved_groups)
        self.llm = get_narrator()  # Catalyst served model if configured, else template fallback
        self.audit = AuditLog()
        self.store = store

    def classify_intent(self, query):
        q = query.lower()
        if any(w in q for w in ["similar", "same modus", "same mo", "like this case", "matching"]):
            return "similar_cases"
        if any(w in q for w in ["network", "connected", "linked", "associates", "gang", "who else"]):
            return "network"
        if any(w in q for w in ["history", "prior", "record of", "all cases for", "same person", "aliases"]):
            return "identity_history"
        if any(w in q for w in ["how many", "list", "burglaries in", "cases in"]):
            return "filter"
        return "similar_cases"  # default to semantic

    def handle(self, query, user="officer_01", role="station_officer", context_case=None):
        intent = self.classify_intent(query)
        citations = []; payload = {}; cases_touched = []

        if intent == "similar_cases":
            results = self.R.similar_cases(query, k=5)
            payload = {"results": results}
            citations = [r["case_id"] for r in results]
            narration = self.llm.narrate("similar_cases", payload)

        elif intent == "network":
            cid = context_case or (citations[0] if citations else None)
            if cid is None:
                # if no case in context, use semantic to find the most relevant case first
                top = self.R.similar_cases(query, k=1)
                cid = top[0]["case_id"] if top else None
            if cid:
                net = self.R.network_around_case(cid)
                payload = {"network": net}
                citations = [cid] + net["linked_cases"]
                narration = self.llm.narrate("network", payload)
            else:
                narration = "No case context available for network analysis."

        elif intent == "identity_history":
            # identity_history REQUIRES a person handle: an explicit case context, OR a name in the query.
            target_amid = None
            if context_case:
                acc = self.store.get_accused_for_case(context_case)
                if acc: target_amid = acc[0]["AccusedMasterID"]
            if target_amid is None:
                # try to find a name mentioned in the query among accused (incl. Kannada script)
                for a in self.store.all_accused():
                    nm = a["AccusedName"]
                    if nm and (nm.lower() in query.lower() or nm in query):
                        target_amid = a["AccusedMasterID"]; break
            if target_amid is not None:
                hist = self.R.cases_for_identity(target_amid)
                if isinstance(hist, dict) and hist.get("member_count",0) > 1:
                    payload = {"history": hist}
                    citations = [c["case_id"] for c in hist["cases"]]
                    narration = self.llm.narrate("identity_history", payload)
                elif isinstance(hist, dict):
                    narration = (f"This individual appears in only one case in the records "
                                 f"(no cross-case identity established). Name-only matches, if any, "
                                 f"are flagged for human review rather than asserted.")
                    citations = [c["case_id"] for c in hist.get("cases",[])]
                else:
                    narration = "No cross-case identity found for this individual."
            else:
                narration = ("Identity history needs a specific person: click a person/case or name "
                             "the individual. A contextless history query cannot identify whom to look up.")

        elif intent == "filter":
            # crude parse for district + burglary
            district = None
            for d in ["Bengaluru Urban","Mysuru","Belagavi","Mangaluru","Kalaburagi"]:
                if d.lower() in query.lower(): district = d
            cases = self.R.filter_cases(district_name=district, crime_subhead=1, limit=20)
            citations = cases
            narration = f"Found {len(cases)} burglary cases" + (f" in {district}" if district else "") + \
                        f": {', '.join('FIR '+str(c) for c in cases[:15])}" + (" …" if len(cases)>15 else "")

        cases_touched = citations
        response = {"query": query, "intent": intent, "answer": narration,
                    "citations": sorted(set(citations)),
                    "trust_note": "Every claim above is derived from the cited FIRs. A human officer verifies before action."}
        # AUDIT (post)
        self.audit.record(user, role, query, intent, cases_touched, narration)
        return response


if __name__ == "__main__":
    store = RelationalStore(":memory:"); store.build(verbose=False)
    graph = NetworkXGraphStore(); build(store, graph); enrich(store, graph)
    _,_,_,groups,_ = resolve(store, graph)
    orch = Orchestrator(store, graph, groups)
    gt = json.load(open("../01_data_generator/ground_truth.json", encoding="utf-8"))
    setA = gt["seeded_connections"]["set_A_mysuru_cluster"]

    queries = [
        ("Show me cases with a similar modus operandi to night-time ground floor burglary with glass breaking", None),
        ("Show the criminal network connected to this case", setA["fir_ids"][0]),
        ("What is the prior history of this individual across cases", None),
        ("How many burglaries in Mysuru", None),
    ]
    for q, ctx in queries:
        print("="*75)
        print(f"QUERY: {q}")
        r = orch.handle(q, context_case=ctx)
        print(f"[intent: {r['intent']}]")
        print(r["answer"])
        print(f"CITATIONS: {r['citations']}")
        print()

    print("="*75)
    print("AUDIT LOG (every query recorded):")
    for e in orch.audit.dump():
        print(f"  {e['timestamp'][:19]} | {e['user']} ({e['role']}) | intent={e['intent']} | cases={len(e['cases_touched'])}")
    store.close()
