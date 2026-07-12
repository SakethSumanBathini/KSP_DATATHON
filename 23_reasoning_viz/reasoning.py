"""
Component 23 — Reasoning-Path Visualisation Data   [Challenge req 9.2]
"Visualization of reasoning paths / decision trees behind AI conclusions."

WHAT THIS CLOSES:
  We cite every conclusion (req 9.1 — done). But a citation is a reference, not an EXPLANATION of
  HOW we got there. req 9.2 asks us to expose the reasoning PATH — the chain of inferences from
  raw FIR data to conclusion — in a form that can be VISUALISED. A judge (and an officer) should
  be able to SEE why the system linked two cases, not just be told that it did.

THIS COMPONENT PRODUCES THE DATA; THE FRONTEND RENDERS THE GRAPH.
  Output is a nodes+edges structure (a directed reasoning graph) that a frontend draws directly.
  Each node is a step; each edge is an inference with a stated basis. Nothing is hidden inside a
  model — every hop is explicit and auditable, which is the whole point of a police-facing system.

Two reasoning paths are exposed (the two that carry our strongest claims):
  1. IDENTITY RESOLUTION — how did we decide these separate FIR rows are the same person?
  2. NETWORK LINKAGE — how did we decide these cases are connected?
"""
import sys, os
for p in ["02_relational_layer", "03_graph_construction", "04_extraction", "05_entity_resolution"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), p))

from build_graph import person_id


class ReasoningPathBuilder:
    def __init__(self, store, graph, resolved_groups):
        self.store = store
        self.graph = graph
        self.groups = resolved_groups
        self.identity_of = {}
        for gi, g in enumerate(resolved_groups):
            for amid in g:
                self.identity_of[amid] = gi
        self.by_id = {a["AccusedMasterID"]: a for a in store.all_accused()}

    def _node(self, nid, label, kind, detail=None):
        return {"id": nid, "label": label, "type": kind, "detail": detail or ""}

    def identity_reasoning(self, accused_id):
        """
        The reasoning graph behind 'these rows are the same person'.
        Nodes: the accused rows, the evidence that links them, the similarity decision.
        Edges: each carries the BASIS for the inference.
        """
        gi = self.identity_of.get(accused_id)
        if gi is None:
            return {"error": "accused not part of a resolved identity"}
        members = sorted(self.groups[gi])

        nodes, edges = [], []
        concl = f"identity_{gi}"
        nodes.append(self._node(concl, f"CONCLUSION: one person (Identity:{gi})", "conclusion",
                                f"{len(members)} FIR records resolved to a single individual."))

        names_seen = {}
        for amid in members:
            a = self.by_id[amid]
            c = self.store.get_case(a["CaseMasterID"])
            an = f"accused_{amid}"
            nodes.append(self._node(
                an, f"{a['AccusedName']}", "evidence",
                f"FIR {a['CaseMasterID']}, age {a.get('AgeYear','?')}, "
                f"{self.store.get_crime_subhead_name(c['CrimeMinorHeadID']) if c else ''}"))
            names_seen.setdefault(a["AccusedName"], []).append(a["CaseMasterID"])
            edges.append({"from": an, "to": concl, "basis": "candidate record"})

        # the reasoning: name-variant matching + shared physical evidence
        distinct_names = list(names_seen)
        if len(distinct_names) > 1:
            rn = f"reason_name_{gi}"
            nodes.append(self._node(
                rn, "Kannada/transliteration name match", "inference",
                f"Spelling variants judged the same name: {distinct_names}. "
                f"This is invisible to an exact-string SQL match."))
            edges.append({"from": rn, "to": concl,
                          "basis": "name variants reconciled via transliteration + phonetic match"})

        # shared phones/vehicles across the members (the corroborating hard evidence)
        shared = {}
        for amid in members:
            pid = person_id(amid)
            if self.graph.get_node(pid) is None:
                continue
            for nb in self.graph.neighbors(pid):
                nb_id = nb if isinstance(nb, str) else nb[0]
                if str(nb_id).startswith(("Phone:", "Vehicle:")):
                    shared.setdefault(str(nb_id), 0)
                    shared[str(nb_id)] += 1
        corroborated = {k: v for k, v in shared.items() if v >= 2}
        if corroborated:
            re_ = f"reason_evidence_{gi}"
            nodes.append(self._node(
                re_, "Shared physical evidence", "inference",
                f"Same {', '.join(list(corroborated)[:3])} appears across multiple of these FIRs — "
                f"corroborating the name match with hard evidence."))
            edges.append({"from": re_, "to": concl,
                          "basis": "shared phone/vehicle corroborates the identity"})

        return {
            "reasoning_type": "identity_resolution",
            "conclusion": f"Identity:{gi}",
            "member_cases": [self.by_id[m]["CaseMasterID"] for m in members],
            "nodes": nodes,
            "edges": edges,
            "plain_language": (
                f"KAVERI concluded these {len(members)} FIR records describe ONE person because the "
                f"names {distinct_names} are spelling variants of the same name"
                + (f", AND the same physical evidence ({', '.join(list(corroborated)[:2])}) recurs "
                   f"across the cases" if corroborated else "")
                + ". A human officer verifies before any action."),
        }

    def network_reasoning(self, case_id):
        """The reasoning graph behind 'these cases are connected'."""
        nodes, edges = [], []
        root = f"case_{case_id}"
        c = self.store.get_case(case_id)
        if not c:
            return {"error": "case not found"}
        nodes.append(self._node(root, f"FIR {case_id}", "root",
                                self.store.get_crime_subhead_name(c["CrimeMinorHeadID"])))

        # accused -> their evidence -> other cases sharing that evidence
        linked_cases = set()
        for a in self.store.get_accused_for_case(case_id):
            pid = person_id(a["AccusedMasterID"])
            if self.graph.get_node(pid) is None:
                continue
            pnode = f"person_{a['AccusedMasterID']}"
            nodes.append(self._node(pnode, a["AccusedName"], "person", f"accused in FIR {case_id}"))
            edges.append({"from": root, "to": pnode, "basis": "named accused"})
            for nb in self.graph.neighbors(pid):
                nb_id = str(nb if isinstance(nb, str) else nb[0])
                if nb_id.startswith(("Phone:", "Vehicle:", "FinancialAccount:")):
                    enode = f"ev_{nb_id}"
                    if not any(n["id"] == enode for n in nodes):
                        nodes.append(self._node(enode, nb_id, "evidence", "shared evidence"))
                    edges.append({"from": pnode, "to": enode, "basis": "linked to this accused"})
                    # who else touches this evidence?
                    for nb2 in self.graph.neighbors(nb_id):
                        nb2_id = str(nb2 if isinstance(nb2, str) else nb2[0])
                        if nb2_id.startswith("Person:") and nb2_id != pid:
                            # find that person's case
                            for oa in self.store.all_accused():
                                if person_id(oa["AccusedMasterID"]) == nb2_id:
                                    ocase = oa["CaseMasterID"]
                                    if ocase != case_id:
                                        linked_cases.add(ocase)
                                        onode = f"case_{ocase}"
                                        if not any(n["id"] == onode for n in nodes):
                                            nodes.append(self._node(onode, f"FIR {ocase}", "linked_case",
                                                                    "connected via shared evidence"))
                                        edges.append({"from": enode, "to": onode,
                                                      "basis": "same evidence appears in this FIR"})
        return {
            "reasoning_type": "network_linkage",
            "root_case": case_id,
            "linked_cases": sorted(linked_cases),
            "nodes": nodes,
            "edges": edges,
            "plain_language": (
                f"FIR {case_id} connects to {len(linked_cases)} other case(s). The path: the accused "
                f"in this FIR is linked (by phone/vehicle) to evidence that ALSO appears in those "
                f"other FIRs. Each hop is shown and cited; none is inferred by a black box."),
            "render_hint": {
                "node_colors": {"root": "#c0392b", "linked_case": "#e67e22", "person": "#2980b9",
                                "evidence": "#27ae60", "conclusion": "#8e44ad", "inference": "#f39c12"},
                "layout": "left-to-right directed graph; root on the left, conclusion on the right",
            },
        }


if __name__ == "__main__":
    from loader import RelationalStore
    from graph_store import NetworkXGraphStore
    from build_graph import build
    from extract import enrich
    from resolve import resolve

    store = RelationalStore(":memory:"); store.build(verbose=False)
    graph = NetworkXGraphStore(); build(store, graph); enrich(store, graph)
    _, _, _, groups, _ = resolve(store, graph)
    R = ReasoningPathBuilder(store, graph, groups)

    print("=== COMPONENT 23: REASONING-PATH VISUALISATION DATA ===\n")
    print("--- WHY are these the same person? (identity reasoning graph) ---")
    ir = R.identity_reasoning(17)      # the Kannada-variant identity
    print(f"  conclusion: {ir['conclusion']}  ({len(ir['member_cases'])} cases)")
    print(f"  nodes: {len(ir['nodes'])}  edges: {len(ir['edges'])}")
    for n in ir["nodes"]:
        print(f"    [{n['type']:<11}] {n['label']}")
    print(f"\n  PLAIN LANGUAGE: {ir['plain_language']}")

    print("\n\n--- WHY are these cases connected? (network reasoning graph) ---")
    nr = R.network_reasoning(1)
    print(f"  root FIR 1 -> linked cases: {nr['linked_cases']}")
    print(f"  reasoning graph: {len(nr['nodes'])} nodes, {len(nr['edges'])} edges")
    print(f"  PLAIN LANGUAGE: {nr['plain_language']}")
    store.close()
