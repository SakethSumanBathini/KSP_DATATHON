"""
Component 4 — Entity extraction from BriefFacts free text.
Extracts phones, vehicles, UPI IDs (validated by regex BEFORE node creation),
creates Phone/Vehicle/FinancialAccount nodes with SOURCE-SPAN citations,
links them to FIRs/Persons. Measures hit-rate against ground_truth.json.
"""
import re, sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "02_relational_layer"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "03_graph_construction"))
from loader import RelationalStore
from graph_store import NetworkXGraphStore
from build_graph import build, fir_id, person_id

# ---- validated extraction patterns ----
# phone: +91 followed by 10 digits, OR 10-digit possibly spaced as 3-3-4
RE_PHONE_PLUS = re.compile(r'\+91(\d{10})')
RE_PHONE_SPACED = re.compile(r'\b(\d{3})\s(\d{3})\s(\d{4})\b')
RE_VEHICLE = re.compile(r'\bKA-\d{2}-[A-Z]{2}-\d{4}\b')
RE_UPI = re.compile(r'\b([a-z0-9._-]{2,})@(okaxis|oksbi|okhdfc|paytm)\b', re.IGNORECASE)

def normalize_phone(raw_digits):
    return "+91" + raw_digits

def extract_from_text(text):
    """Return list of (type, canonical_value, matched_span_text, start, end)."""
    found = []
    for m in RE_PHONE_PLUS.finditer(text):
        found.append(("phone", normalize_phone(m.group(1)), m.group(0), m.start(), m.end()))
    for m in RE_PHONE_SPACED.finditer(text):
        digits = m.group(1)+m.group(2)+m.group(3)
        # only treat as phone if it looks like a mobile (starts 6-9)
        if digits[0] in "6789":
            found.append(("phone", normalize_phone(digits), m.group(0), m.start(), m.end()))
    for m in RE_VEHICLE.finditer(text):
        found.append(("vehicle", m.group(0), m.group(0), m.start(), m.end()))
    for m in RE_UPI.finditer(text):
        found.append(("upi", m.group(0).lower(), m.group(0), m.start(), m.end()))
    return found

def phone_node(v): return f"Phone:{v}"
def vehicle_node(v): return f"Vehicle:{v}"
def account_node(v): return f"FinancialAccount:{v}"

def enrich(store, graph):
    extracted = {"phone":0, "vehicle":0, "upi":0}
    for c in store.get_all_cases():
        cid = c["CaseMasterID"]
        text = c["BriefFacts"] or ""
        # accused persons in this case (to link entities to a person where sensible)
        accused = store.get_accused_for_case(cid)
        for (etype, val, span, start, end) in extract_from_text(text):
            if etype == "phone":
                nid = phone_node(val)
                if not graph.get_node(nid):
                    graph.add_node(nid, "Phone", value=val)
                # citation stored on the EDGE: which case + exact source span
                graph.add_edge(fir_id(cid), nid, "USED_PHONE",
                               source_case_id=cid, source_span=span, span_start=start, span_end=end)
                for a in accused:
                    graph.add_edge(person_id(a["AccusedMasterID"]), nid, "PERSON_USED_PHONE",
                                   source_case_id=cid, source_span=span)
                extracted["phone"] += 1
            elif etype == "vehicle":
                nid = vehicle_node(val)
                if not graph.get_node(nid):
                    graph.add_node(nid, "Vehicle", value=val)
                graph.add_edge(fir_id(cid), nid, "VEHICLE_SEEN",
                               source_case_id=cid, source_span=span, span_start=start, span_end=end)
                for a in accused:
                    graph.add_edge(person_id(a["AccusedMasterID"]), nid, "OWNS_VEHICLE",
                                   source_case_id=cid, source_span=span)
                extracted["vehicle"] += 1
            elif etype == "upi":
                nid = account_node(val)
                if not graph.get_node(nid):
                    graph.add_node(nid, "FinancialAccount", value=val)
                graph.add_edge(fir_id(cid), nid, "TRANSACTED_VIA",
                               source_case_id=cid, source_span=span, span_start=start, span_end=end)
                extracted["upi"] += 1
    return extracted

def measure(store, graph, gt):
    """Hit-rate: of ground-truth entity->FIR links, how many did extraction find at the right FIR?"""
    truth = gt["entity_to_fir"]
    by_type = {}
    for t in truth:
        by_type.setdefault(t["type"], {"total":0, "found":0, "misses":[]})
        by_type[t["type"]]["total"] += 1
        # does the graph have an edge from that FIR to that entity value?
        entity_node = {"phone":"Phone", "vehicle":"Vehicle", "upi":"FinancialAccount"}[t["type"]] + ":" + t["value"]
        fnode = fir_id(t["case_id"])
        hit = False
        if graph.get_node(entity_node):
            for nb, d in graph.neighbors(fnode):
                if nb == entity_node:
                    hit = True; break
        if hit: by_type[t["type"]]["found"] += 1
        else: by_type[t["type"]]["misses"].append({"value":t["value"], "case_id":t["case_id"]})
    return by_type


if __name__ == "__main__":
    store = RelationalStore(db_path=":memory:"); store.build(verbose=False)
    graph = NetworkXGraphStore(); build(store, graph)
    gt = json.load(open("../01_data_generator/ground_truth.json", encoding="utf-8"))

    counts = enrich(store, graph)
    print("=== COMPONENT 4: ENTITY EXTRACTION ===")
    print("Entity nodes/edges created:")
    for k,v in counts.items(): print(f"  {k}: {v} extractions")
    ng = graph.node_count_by_label()
    print(f"Graph now has Phone={ng.get('Phone',0)} Vehicle={ng.get('Vehicle',0)} FinancialAccount={ng.get('FinancialAccount',0)} unique nodes")

    print("\n=== HIT-RATE vs GROUND TRUTH (honest, incl. misses) ===")
    m = measure(store, graph, gt)
    for t, r in m.items():
        pct = 100*r["found"]/r["total"] if r["total"] else 0
        print(f"  {t}: {r['found']}/{r['total']} found ({pct:.1f}%)  misses: {len(r['misses'])}")
        for miss in r["misses"][:3]:
            print(f"      MISS: {miss['value']} in case {miss['case_id']}")
    store.close()
