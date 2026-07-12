"""
Component 18 — Investigation Outcomes & Evidence-Driven Leads   [Challenge req 6.2]
"Identification of similar past cases AND INVESTIGATION OUTCOMES."

THE GAP THIS CLOSES:
  We were telling an investigator "here are 5 similar cases." We never told them WHAT HAPPENED
  to those cases. That is the half of the requirement that actually matters — an investigator
  does not want similar cases, they want to know WHAT SOLVED similar cases.

  The data was in the schema the whole time and we never read it:
      ChargesheetDetails.cstype -> 'A' Chargesheet filed | 'B' False case | 'C' Undetected

WHAT THIS PRODUCES:
  Not "5 similar cases" but:
      "5 similar burglaries. 3 chargesheeted, 1 false complaint, 1 undetected.
       ALL 3 solved cases had a vehicle number recovered in the FIR. Yours does not.
       RECOMMENDED LEAD: canvass for vehicle sightings."

  That is a decision-support system. The previous version was a search engine.

METHOD (transparent, no black box):
  1. Find comparable cases (same crime sub-head, same district OR near-repeat radius).
  2. Pull their final reports.
  3. Compute the CLEARANCE RATE, and compare the evidence present in SOLVED vs UNSOLVED ones.
  4. Any evidence type over-represented among solved cases becomes a RECOMMENDED LEAD.
  Every number is cited to the FIRs it came from.
"""
import sys, os, math
from collections import Counter, defaultdict
for p in ["02_relational_layer", "04_extraction"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), p))

from extract import extract_from_text

CSTYPE = {"A": "Chargesheet filed", "B": "False case", "C": "Undetected"}
EVIDENCE_LABEL = {"phone": "a mobile number", "vehicle": "a vehicle registration number",
                  "upi": "a financial account handle"}


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


class OutcomeAnalyser:
    def __init__(self, store):
        self.store = store
        self.cases = store.get_all_cases()
        self.by_id = {c["CaseMasterID"]: c for c in self.cases}
        self.outcome = {o["CaseMasterID"]: o for o in store.all_outcomes()}
        # evidence fingerprint per case, extracted from BriefFacts (invisible to SQL)
        self.evidence = {}
        for c in self.cases:
            types = {t for (t, v, s, a, b) in extract_from_text(c["BriefFacts"] or "")}
            self.evidence[c["CaseMasterID"]] = types
        # arrests
        self.arrested = set()
        for a in store.all_accused():
            if store.get_arrests_for_accused(a["AccusedMasterID"]):
                self.arrested.add(a["CaseMasterID"])

    def comparable_cases(self, case_id, radius_m=5000, limit=40):
        """Same crime type; same district OR within radius. The peer group we learn from."""
        c = self.by_id.get(case_id)
        if not c:
            return []
        d = self.store.get_district_for_case(case_id)
        dname = d["DistrictName"] if d else None
        peers = []
        for o in self.cases:
            if o["CaseMasterID"] == case_id:
                continue
            if o["CrimeMinorHeadID"] != c["CrimeMinorHeadID"]:
                continue
            od = self.store.get_district_for_case(o["CaseMasterID"])
            same_district = od and dname and od["DistrictName"] == dname
            near = False
            try:
                near = haversine_m(c["latitude"], c["longitude"],
                                   o["latitude"], o["longitude"]) <= radius_m
            except Exception:
                pass
            if same_district or near:
                peers.append(o["CaseMasterID"])
        return peers[:limit]

    def analyse(self, case_id):
        c = self.by_id.get(case_id)
        if not c:
            return None
        peers = self.comparable_cases(case_id)
        resolved = [p for p in peers if p in self.outcome]

        counts = Counter(self.outcome[p]["cstype"] for p in resolved)
        solved = [p for p in resolved if self.outcome[p]["cstype"] == "A"]
        unsolved = [p for p in resolved if self.outcome[p]["cstype"] == "C"]
        false_cases = [p for p in resolved if self.outcome[p]["cstype"] == "B"]

        clearance = (100.0 * len(solved) / len(resolved)) if resolved else None

        # WHAT DIFFERENTIATED THE SOLVED CASES? — the actionable part
        ev_solved, ev_unsolved = Counter(), Counter()
        for p in solved:
            for t in self.evidence.get(p, ()):
                ev_solved[t] += 1
        for p in unsolved:
            for t in self.evidence.get(p, ()):
                ev_unsolved[t] += 1

        leads = []
        this_evidence = self.evidence.get(case_id, set())
        for t in set(list(ev_solved) + list(ev_unsolved)):
            s_rate = ev_solved[t] / len(solved) if solved else 0
            u_rate = ev_unsolved[t] / len(unsolved) if unsolved else 0
            lift = s_rate - u_rate
            if lift > 0.15:                      # over-represented among SOLVED cases
                leads.append({
                    "evidence_type": t,
                    "present_in_solved_pct": round(100 * s_rate, 1),
                    "present_in_unsolved_pct": round(100 * u_rate, 1),
                    "lift_pp": round(100 * lift, 1),
                    "you_have_it": t in this_evidence,
                    "recommendation": (
                        f"{'YOU ALREADY HAVE THIS — exploit it.' if t in this_evidence else 'MISSING FROM YOUR FIR.'} "
                        f"{EVIDENCE_LABEL.get(t, t)} appears in {100*s_rate:.0f}% of the comparable "
                        f"cases that were CHARGESHEETED, but only {100*u_rate:.0f}% of those left "
                        f"UNDETECTED."
                        + ("" if t in this_evidence else
                           f" Actively pursue {EVIDENCE_LABEL.get(t, t)}.")),
                })
        leads.sort(key=lambda l: -l["lift_pp"])

        # arrest effect
        arr_solved = sum(1 for p in solved if p in self.arrested)
        arr_unsolved = sum(1 for p in unsolved if p in self.arrested)

        return {
            "case_id": case_id,
            "crime_type": self.store.get_crime_subhead_name(c["CrimeMinorHeadID"]),
            "your_status": self.store.get_case_status_name(c["CaseStatusID"]),
            "your_outcome": (CSTYPE.get(self.outcome[case_id]["cstype"])
                             if case_id in self.outcome else "Still under investigation"),
            "comparable_cases_found": len(peers),
            "with_final_report": len(resolved),
            "outcomes": {CSTYPE[k]: v for k, v in counts.items()},
            "clearance_rate_pct": round(clearance, 1) if clearance is not None else None,
            "solved_case_ids": solved[:12],
            "undetected_case_ids": unsolved[:12],
            "false_case_ids": false_cases[:6],
            "your_evidence": sorted(this_evidence),
            "leads": leads,
            "arrest_effect": {
                "arrest_made_in_solved": f"{arr_solved}/{len(solved)}" if solved else "n/a",
                "arrest_made_in_undetected": f"{arr_unsolved}/{len(unsolved)}" if unsolved else "n/a",
            },
            "citations": sorted(set(solved + unsolved + false_cases)),
        }

    def render(self, a):
        L = [f"INVESTIGATION OUTCOMES — FIR {a['case_id']} ({a['crime_type']})",
             f"Your case: {a['your_outcome']}",
             "",
             f"  {a['with_final_report']} comparable cases have a final report:"]
        for k, v in a["outcomes"].items():
            L.append(f"     {v:>3}  {k}")
        if a["clearance_rate_pct"] is not None:
            L.append(f"  CLEARANCE RATE for this crime type in this area: {a['clearance_rate_pct']}%")
        L.append("")
        if a["leads"]:
            L.append("  WHAT SOLVED THE OTHERS  (this is your lead):")
            for l in a["leads"]:
                mark = "HAVE" if l["you_have_it"] else "MISSING"
                L.append(f"    [{mark:<7}] {l['recommendation']}")
        else:
            L.append("  No evidence type distinguishes solved from unsolved cases here.")
        L.append("")
        L.append(f"  Solved cases (study these): {a['solved_case_ids'][:8]}")
        L.append(f"  Sources: FIR {a['citations'][:10]}...")
        return "\n".join(L)


if __name__ == "__main__":
    from loader import RelationalStore
    store = RelationalStore(":memory:"); store.build(verbose=False)
    A = OutcomeAnalyser(store)

    print("=== COMPONENT 18: INVESTIGATION OUTCOMES & EVIDENCE-DRIVEN LEADS ===\n")

    # pick an OPEN burglary — the realistic scenario: an IO with a live case
    target = None
    for c in store.get_all_cases():
        if c["CrimeMinorHeadID"] == 1 and c["CaseStatusID"] == 1:
            target = c["CaseMasterID"]; break
    a = A.analyse(target or 1)
    print(A.render(a))

    print("\n\n--- The same analysis, as an investigator would consume it ---")
    print(f"  Q: 'What happened to cases like mine?'")
    print(f"  A: {a['with_final_report']} comparable cases closed. "
          f"{a['clearance_rate_pct']}% were chargesheeted.")
    if a["leads"]:
        top = a["leads"][0]
        print(f"     The strongest differentiator: {EVIDENCE_LABEL.get(top['evidence_type'])}.")
        print(f"     Present in {top['present_in_solved_pct']}% of SOLVED vs "
              f"{top['present_in_unsolved_pct']}% of UNDETECTED (+{top['lift_pp']}pp).")
        print(f"     You {'HAVE' if top['you_have_it'] else 'DO NOT HAVE'} it.")
    store.close()
