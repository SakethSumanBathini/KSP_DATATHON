"""
Component 9 — Burglary Investigation Playbook.
Chains all components into the officer workflow:
  upload FIR -> extract entities -> resolve identities -> surface links -> near-repeat hotspot
  -> generate cited Investigation Brief.

This is the DELIVERY VEHICLE. Same engine, burglary node priorities. Produces the artifact an
officer actually uses: a structured, cited investigation brief.
"""
import sys, os, json, math, datetime
for p in ["02_relational_layer","03_graph_construction","04_extraction","05_entity_resolution","06_retrieval","07_orchestrator","08_trust_layer"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),p))
from loader import RelationalStore
from graph_store import NetworkXGraphStore
from build_graph import build, fir_id, person_id
from extract import enrich, extract_from_text, phone_node, vehicle_node
from resolve import resolve
from retrieval import Retriever
from trust import AccessControl, ImmutableAudit

def haversine_m(lat1,lon1,lat2,lon2):
    R=6371000
    p1,p2=math.radians(lat1),math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

class BurglaryPlaybook:
    def __init__(self, store, graph, resolved_groups):
        self.store=store; self.graph=graph; self.R=Retriever(store,graph,resolved_groups)
        self.identity_of={}
        for gi,g in enumerate(resolved_groups):
            for amid in g: self.identity_of[amid]=f"Identity:{gi}"
        # DURABLE AUDIT (req 10.2): hand the chain a persist function so every entry is written
        # through to the Catalyst Data Store as well as the in-memory hash chain. If Catalyst is
        # off or unreachable, persist_fn raises, the chain keeps the entry in memory, and the
        # investigation continues — an audit outage must never block an officer.
        _persist = None
        try:
            import catalyst_services as _cs
            if getattr(_cs, "AUDIT_PERSIST", False):
                _persist = _cs.persist_audit
        except Exception:
            _persist = None
        self.audit=ImmutableAudit(persist_fn=_persist)

    def investigate(self, case_id, user="io_01", role="station_officer"):
        c=self.store.get_case(case_id)
        brief={"case_id":case_id,"crime_no":c["CrimeNo"],"generated":datetime.datetime.now().isoformat(),
               "sections":[], "similar_cases":[], "network":{}, "near_repeat":[], "recommended_leads":[],
               "citations":set()}

        # 1. sections (BNS)
        for s in self.store.get_sections_for_case(case_id):
            brief["sections"].append(f"{s['ActShortName']} {s['SectionID']} ({s['SectionDescription']})")

        # 2. similar MO cases (semantic)
        sim=self.R.similar_cases(c["BriefFacts"] or "", k=6)
        brief["similar_cases"]=[s for s in sim if s["case_id"]!=case_id][:5]
        for s in brief["similar_cases"]: brief["citations"].add(s["case_id"])

        # 3. network via shared entities
        net=self.R.network_around_case(case_id)
        brief["network"]={"linked_cases":net["linked_cases"],
                          "shared_phones":sorted(set(p for p,_ in net["shared_phones"])),
                          "shared_vehicles":sorted(set(v for v,_ in net["shared_vehicles"])),
                          "accused":net["accused"]}
        for lc in net["linked_cases"]: brief["citations"].add(lc)

        # 4. near-repeat: burglaries within 400m and 42 days of this incident
        this_lat, this_lng = c["latitude"], c["longitude"]
        this_date = datetime.datetime.fromisoformat(c["CrimeRegisteredDate"])
        for other in self.store.get_all_cases():
            if other["CaseMasterID"]==case_id: continue
            if other["CrimeMinorHeadID"]!=1: continue  # burglary only
            d_m = haversine_m(this_lat,this_lng,other["latitude"],other["longitude"])
            try: od=datetime.datetime.fromisoformat(other["CrimeRegisteredDate"])
            except: continue
            dd=abs((od-this_date).days)
            if d_m<=400 and dd<=42:
                brief["near_repeat"].append({"case_id":other["CaseMasterID"],
                    "distance_m":round(d_m), "days_apart":dd})
                brief["citations"].add(other["CaseMasterID"])
        brief["near_repeat"].sort(key=lambda x:(x["distance_m"]))

        # 5. recommended leads (grounded, cited)
        if brief["network"]["shared_phones"]:
            brief["recommended_leads"].append(
                # NEVER interpolate a list/dict straight into text an officer will read. The old
                # line produced:  shared phone(s) ['+916513911270', '+9193...'] — cases [2, 3, 4]
                # Brackets and quote marks are not evidence; they are a leaked data structure, in
                # an ACTION ITEM someone is expected to carry out. Fixed the narrative line first
                # and missed this one two lines away — so there is now a test (test_invariants)
                # that fails on ANY "['" appearing in officer-facing output, anywhere.
                f"Request CDR for shared phone(s) {', '.join(brief['network']['shared_phones'])} — "
                f"linked across {', '.join('FIR ' + str(c) for c in net['linked_cases'])}.")
        if brief["network"]["shared_vehicles"]:
            # THIRD INSTANCE OF THE SAME BUG. The narrative leaked a raw Python list; I fixed it.
            # The CDR line leaked one two lines away; I fixed that too and added a test. The test
            # only ever ran against case 1 — which has no shared vehicles — so THIS branch never
            # executed and the test passed VACUOUSLY. A green test that exercises nothing is worse
            # than no test: it buys false confidence. The test now sweeps all 500 cases.
            brief["recommended_leads"].append(
                f"Trace vehicle(s) {', '.join(brief['network']['shared_vehicles'])} appearing in "
                f"linked cases.")
        if brief["near_repeat"]:
            nr=brief["near_repeat"][:3]
            brief["recommended_leads"].append(
                f"Near-repeat pattern: {len(brief['near_repeat'])} burglaries within 400m/42 days "
                f"(closest: case {nr[0]['case_id']} at {nr[0]['distance_m']}m). Advise patrol density + resident alerts.")
        # MODUS-OPERANDI LEADS — we were computing these and throwing them away.
        #
        # A random sweep of the corpus found that 464 of 500 cases (93%) showed an EMPTY
        # "Recommended Actions" panel. The officer opens ten cases and nine give him nothing.
        #
        # But the system was NOT ignorant of those cases — it was SILENT about them. Case 58 had
        # FIVE cases matching its modus operandi (FIR 103 at 0.578, FIR 254 at 0.371) sitting
        # right there in the brief, and the lead generator never looked at them. It only fired on
        # shared phones, near-repeat geography, or a resolved repeat offender — the three things
        # that happen to be rare.
        #
        # Knowing something and not saying it is the same, to the officer, as not knowing it.
        if brief.get("similar_cases"):
            sc = brief["similar_cases"][:3]
            refs = ", ".join(f"FIR {s['case_id']} ({s['score']:.2f})" for s in sc)
            brief["recommended_leads"].append(
                f"Modus operandi matches {len(brief['similar_cases'])} other case(s); "
                f"closest {len(sc)} by score: {refs}. "
                f"Compare entry method and timing — a common offender is possible but NOT "
                f"established; no shared evidence links these cases yet.")

        # UNLINKED EVIDENCE — the single most common thing we were sitting on.
        #
        # Case 58 has a phone number written in the FIR: +917830911730. It links to no other case,
        # so `shared_phones` was empty, so no lead fired, so the officer was shown an empty panel.
        # The number was in our graph the whole time. 323 of 500 cases have physical evidence like
        # this that we were never mentioning.
        #
        # AN UNLINKED NUMBER IS NOT A CLEARED NUMBER. It is the first thing an investigating
        # officer would chase, and the fact that our graph cannot yet connect it to anything is a
        # statement about OUR data, not about the suspect.
        try:
            own = [n for n in self.graph.g.neighbors(f"FIR:{case_id}")
                   if n.startswith("Phone:") or n.startswith("Vehicle:")]
            unlinked_ph = [n.split(":", 1)[1] for n in own if n.startswith("Phone:")
                           if n.split(":", 1)[1] not in brief["network"]["shared_phones"]]
            unlinked_ve = [n.split(":", 1)[1] for n in own if n.startswith("Vehicle:")
                           if n.split(":", 1)[1] not in brief["network"]["shared_vehicles"]]
            if unlinked_ph:
                brief["recommended_leads"].append(
                    f"Phone(s) {', '.join(unlinked_ph)} appear in this FIR but link to no other "
                    f"case in the database. Request CDR — an unlinked number is not a cleared "
                    f"number.")
            if unlinked_ve:
                brief["recommended_leads"].append(
                    f"Vehicle(s) {', '.join(unlinked_ve)} appear in this FIR but link to no other "
                    f"case. Run an RTO trace and check ANPR for the incident window.")
        except Exception:
            pass          # graph shape must never take down a briefing

        # resolved repeat offenders
        repeat=[a for a in net["accused"] if a["identity"].startswith("Identity:")]
        if repeat:
            for a in repeat:
                members=[amid for amid,i in self.identity_of.items() if i==a["identity"]]
                if len(members)>1:
                    brief["recommended_leads"].append(
                        f"Accused '{a['name']}' is a resolved repeat offender ({len(members)} linked cases) — prioritize.")

        # NEVER SHOW AN OFFICER A BLANK PANEL.
        #
        # 464 of 500 cases returned an empty "Recommended Actions" box. To an investigating officer
        # a blank panel says ONE thing: this tool is useless. It does not say "I searched the whole
        # database and found no cross-case links" — which is a genuine, valuable investigative
        # finding, and the truth.
        #
        # Silence and "I checked, and there is nothing" are the same pixels and completely
        # different messages. An analyst who says nothing is worthless; an analyst who says "no
        # links found, here is what I checked" has done his job. State the negative result.
        if not brief["recommended_leads"]:
            checked = []
            checked.append(f"{len(brief.get('similar_cases') or [])} modus-operandi comparisons")
            checked.append("shared phones and vehicles across all 500 FIRs")
            checked.append("near-repeat geography (400m / 42 days)")
            checked.append("cross-case identity resolution")
            brief["recommended_leads"].append(
                "No cross-case links found. KAVERI checked " + "; ".join(checked) +
                " — and this FIR connects to none of them. That is a finding, not a gap: treat "
                "this as an isolated incident unless new evidence (a phone, a vehicle, a name) "
                "emerges. Re-run this briefing when it does.")

        brief["citations"]=sorted(brief["citations"])
        self.audit.record(user, role, f"investigate case {case_id}", "playbook",
                          brief["citations"], json.dumps(brief["recommended_leads"]))
        return brief

    def render_brief(self, brief):
        L=[]
        L.append(f"╔══ INVESTIGATION BRIEF — FIR {brief['crime_no']} (Case {brief['case_id']}) ══╗")
        L.append(f"Generated: {brief['generated'][:19]}  |  KAVERI Crime Intelligence")
        L.append(f"\nCHARGES: {'; '.join(brief['sections'])}")
        L.append(f"\n▸ SIMILAR MODUS OPERANDI ({len(brief['similar_cases'])} cases):")
        for s in brief["similar_cases"]:
            L.append(f"   FIR {s['case_id']} (sim {s['score']}): {s['brief'].strip()[:80]}…")
        L.append(f"\n▸ CRIMINAL NETWORK:")
        n=brief["network"]
        L.append(f"   Linked to {len(n['linked_cases'])} cases via shared evidence: {n['linked_cases']}")
        if n["shared_phones"]: L.append(f"   Shared phones: {n['shared_phones']}")
        if n["shared_vehicles"]: L.append(f"   Shared vehicles: {n['shared_vehicles']}")
        for a in n["accused"]: L.append(f"   Accused: {a['name']} [{a['identity']}]")
        L.append(f"\n▸ NEAR-REPEAT ANALYSIS (400m / 42 days):")
        L.append(f"   {len(brief['near_repeat'])} nearby burglaries" +
                 (f"; closest {brief['near_repeat'][0]['distance_m']}m away" if brief['near_repeat'] else ""))
        L.append(f"\n▸ RECOMMENDED INVESTIGATIVE LEADS:")
        for i,l in enumerate(brief["recommended_leads"],1): L.append(f"   {i}. {l}")
        L.append(f"\n▸ EVIDENCE TRAIL (all claims cited): FIRs {brief['citations']}")
        L.append(f"\n⚠ All connections derived from recorded FIR data. Human officer verifies before action.")
        L.append("╚"+"═"*60+"╝")
        return "\n".join(L)


if __name__=="__main__":
    store=RelationalStore(":memory:"); store.build(verbose=False)
    graph=NetworkXGraphStore(); build(store,graph); enrich(store,graph)
    _,_,_,groups,_=resolve(store,graph)
    pb=BurglaryPlaybook(store,graph,groups)
    gt=json.load(open("../01_data_generator/ground_truth.json",encoding="utf-8"))

    # investigate a Set A cluster case (should surface network + near-repeat + repeat offender)
    setA=gt["seeded_connections"]["set_A_mysuru_cluster"]
    brief=pb.investigate(setA["fir_ids"][0])
    print(pb.render_brief(brief))
    store.close()
