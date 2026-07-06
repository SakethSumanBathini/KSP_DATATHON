"""
Component 3 — Graph construction. Reads ONLY through Component 2's data-access API.
Creates the Crime Intelligence Graph structure (pre-resolution, pre-extraction).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "02_relational_layer"))
from loader import RelationalStore
from graph_store import NetworkXGraphStore

# Node ID conventions (stable, prefixed by type)
def fir_id(cid):      return f"FIR:{cid}"
def person_id(amid):  return f"Person:{amid}"       # ONE per Accused row — NO cross-case merge
def victim_id(vmid):  return f"Victim:{vmid}"
def comp_id(cpid):    return f"Complainant:{cpid}"
def station_id(uid):  return f"Station:{uid}"
def district_id(did): return f"District:{did}"
def location_id(cid): return f"Location:{cid}"
def section_id(act,sec): return f"Section:{act}-{sec}"

def build(store, graph):
    cases = store.get_all_cases()
    for c in cases:
        cid = c["CaseMasterID"]
        graph.add_node(fir_id(cid), "FIR", case_id=cid, crime_no=c["CrimeNo"],
                       registered=c["CrimeRegisteredDate"], status=c["CaseStatusID"],
                       brief_facts=c["BriefFacts"])
        # location node from lat/lng
        graph.add_node(location_id(cid), "Location", case_id=cid,
                       lat=c["latitude"], lng=c["longitude"])
        graph.add_edge(fir_id(cid), location_id(cid), "OCCURRED_AT")
        # station + district
        st = store.get_station(c["PoliceStationID"])
        if st:
            sid = station_id(st["UnitID"])
            if not graph.get_node(sid):
                graph.add_node(sid, "PoliceStation", unit_id=st["UnitID"], name=st["UnitName"],
                               district=st["DistrictName"])
            graph.add_edge(fir_id(cid), sid, "REGISTERED_AT")
            did = store.get_district_for_case(cid)
            if did:
                dnode = district_id(did["DistrictID"])
                if not graph.get_node(dnode):
                    graph.add_node(dnode, "District", district_id=did["DistrictID"], name=did["DistrictName"])
                graph.add_edge(sid, dnode, "IN_DISTRICT")
        # accused -> Person (one per row, NO merge)
        for a in store.get_accused_for_case(cid):
            pid = person_id(a["AccusedMasterID"])
            graph.add_node(pid, "Person", accused_master_id=a["AccusedMasterID"],
                           name=a["AccusedName"], age=a["AgeYear"], gender=a["GenderID"],
                           source_case_id=cid)   # retains provenance
            graph.add_edge(pid, fir_id(cid), "ACCUSED_IN")
        # victims
        for v in store.get_victims_for_case(cid):
            vid = victim_id(v["VictimMasterID"])
            graph.add_node(vid, "Victim", victim_master_id=v["VictimMasterID"], name=v["VictimName"])
            graph.add_edge(vid, fir_id(cid), "VICTIM_IN")
        # complainants
        for cp in store.get_complainants_for_case(cid):
            cpid = comp_id(cp["ComplainantID"])
            graph.add_node(cpid, "Complainant", complainant_id=cp["ComplainantID"], name=cp["ComplainantName"])
            graph.add_edge(cpid, fir_id(cid), "COMPLAINANT_IN")
        # sections
        for s in store.get_sections_for_case(cid):
            snode = section_id(s["ActID"], s["SectionID"])
            if not graph.get_node(snode):
                graph.add_node(snode, "Section", act=s["ActID"], section=s["SectionID"],
                               desc=s.get("SectionDescription"))
            graph.add_edge(fir_id(cid), snode, "CHARGED_UNDER")
    return graph


if __name__ == "__main__":
    store = RelationalStore(db_path=":memory:")
    store.build(verbose=False)
    graph = NetworkXGraphStore()
    build(store, graph)
    print("=== COMPONENT 3: GRAPH CONSTRUCTION ===")
    print("Node counts by label:")
    for lbl, n in sorted(graph.node_count_by_label().items()): print(f"  {lbl}: {n}")
    print("Edge counts by relationship:")
    for rel, n in sorted(graph.edge_count_by_rel().items()): print(f"  {rel}: {n}")
    store.close()
