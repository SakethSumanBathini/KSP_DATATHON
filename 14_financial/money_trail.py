"""
Component 14 — Financial Crime & Transaction Link Analysis  [Challenge req 7]
"Detection of financial transactions linked to criminal activities. Identification of money trails
 and suspicious transaction networks."

THE STRUCTURAL POINT (same as our core thesis):
  Financial identifiers (UPI IDs, account handles) exist ONLY inside the BriefFacts free text.
  There is NO financial table in the FIR schema. SQL cannot see them at all.
  Component 4 extracts them; here we build the MONEY TRAIL on top.

Delivers:
  - Financial accounts as first-class graph nodes, linked to cases and (via cases) to persons
  - MULTI-CASE ACCOUNT DETECTION: one UPI handle appearing across several FIRs = a money trail
  - SUSPICIOUS TRANSACTION NETWORK: accounts + persons + cases as one connected structure
  - LAYERING / FAN-IN detection: many cases -> one account (a collection/mule pattern)
  - Every finding cited to the source FIR and the exact text span it was extracted from
"""
import sys, os
from collections import defaultdict
for p in ["02_relational_layer","03_graph_construction","04_extraction","05_entity_resolution"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), p))

from build_graph import person_id, fir_id
from extract import extract_from_text


class MoneyTrailAnalyser:
    def __init__(self, store, graph, resolved_groups=None):
        self.store = store
        self.graph = graph
        self.groups = resolved_groups or []
        self.identity_of = {}
        for gi, g in enumerate(self.groups):
            for amid in g:
                self.identity_of[amid] = gi

        # rebuild account -> cases from the extraction layer (cited to source spans)
        self.account_cases = defaultdict(list)     # upi handle -> [(case_id, span_text)]
        for c in store.get_all_cases():
            text = c["BriefFacts"] or ""
            # extract_from_text returns tuples: (type, canonical_value, matched_span, start, end)
            for (etype, value, span, start, end) in extract_from_text(text):
                if etype == "upi":
                    ctx = text[max(0, start - 45): min(len(text), end + 45)]
                    self.account_cases[value].append({
                        "case_id": c["CaseMasterID"],
                        "crime_no": c["CrimeNo"],
                        "matched": span,
                        "evidence_span": ctx.replace("\n", " "),
                    })

    def multi_case_accounts(self, min_cases=2):
        """A financial account appearing in MORE THAN ONE FIR = a money trail SQL cannot see."""
        out = []
        for acct, hits in self.account_cases.items():
            case_ids = sorted({h["case_id"] for h in hits})
            if len(case_ids) >= min_cases:
                out.append({
                    "account": acct,
                    "case_count": len(case_ids),
                    "cases": case_ids,
                    "evidence": hits,
                })
        out.sort(key=lambda x: -x["case_count"])
        return out

    def suspicious_network(self, account):
        """Full network around one account: cases -> accused -> resolved identities -> other cases."""
        hits = self.account_cases.get(account, [])
        case_ids = sorted({h["case_id"] for h in hits})
        persons, identities = [], set()
        for cid in case_ids:
            for a in self.store.get_accused_for_case(cid):
                amid = a["AccusedMasterID"]
                ident = self.identity_of.get(amid)
                persons.append({
                    "accused_id": amid,
                    "name": a["AccusedName"],
                    "case_id": cid,
                    "identity": f"Identity:{ident}" if ident is not None else "unresolved",
                })
                if ident is not None:
                    identities.add(ident)

        # cases reachable through the RESOLVED identities (the extra hop SQL cannot make)
        reachable = set(case_ids)
        for ident in identities:
            for amid in self.groups[ident]:
                a = next((x for x in self.store.all_accused()
                          if x["AccusedMasterID"] == amid), None)
                if a:
                    reachable.add(a["CaseMasterID"])

        districts = set()
        for cid in reachable:
            d = self.store.get_district_for_case(cid)
            if d:
                districts.add(d["DistrictName"])

        return {
            "account": account,
            "direct_cases": case_ids,
            "persons": persons,
            "resolved_identities": [f"Identity:{i}" for i in sorted(identities)],
            "reachable_cases_via_identity": sorted(reachable),
            "districts": sorted(districts),
            "fan_in": len(case_ids),
            "pattern": self._classify(len(case_ids), len(identities), len(districts)),
            "citations": sorted(reachable),
            "evidence": hits,
        }

    @staticmethod
    def _classify(n_cases, n_identities, n_districts):
        """
        Transparent rule-based typing — an analyst can audit the rule.
        BUG FIX: 'fan-in with a single controller' requires EXACTLY ONE resolved identity.
        n_identities == 0 means we resolved NOBODY — that is NOT evidence of a single controller,
        and claiming otherwise would be an unfounded assertion about a person. We say so plainly.
        """
        if n_cases >= 3 and n_identities == 1:
            return ("FAN-IN / COLLECTION PATTERN: multiple offences funnel into a single account "
                    "held across cases attributable to ONE resolved identity. Consistent with a "
                    "mule/collection account. HIGH investigative priority.")
        if n_cases >= 3 and n_identities == 0:
            return ("RECURRING ACCOUNT, NO RESOLVED CONTROLLER: the same handle appears across "
                    "several offences, but no accused person could be resolved across them. "
                    "This may be a shared/parked handle or a data artefact — REQUIRES HUMAN REVIEW "
                    "before any inference is drawn.")
        if n_cases >= 2 and n_districts >= 2:
            return ("CROSS-DISTRICT MONEY TRAIL: one account links offences across district "
                    "boundaries — invisible to any single station's records.")
        if n_cases >= 2:
            return "MULTI-CASE ACCOUNT: the same financial handle recurs across offences."
        return "SINGLE-CASE ACCOUNT: no trail established."

    def render(self, net):
        L = [f"╔══ MONEY TRAIL — {net['account']} ══╗",
             f"  PATTERN: {net['pattern']}",
             f"  Directly cited in {len(net['direct_cases'])} FIR(s): {net['direct_cases']}",
             f"  Districts touched: {net['districts']}",
             f"  Resolved identities on those cases: {net['resolved_identities']}",
             f"  Cases reachable via identity resolution: {net['reachable_cases_via_identity']}",
             "",
             "  EVIDENCE (extracted from BriefFacts free text — SQL cannot see these):"]
        for e in net["evidence"][:4]:
            L.append(f"    FIR {e['case_id']}: \"…{e['evidence_span'].strip()}…\"")
        L.append("")
        L.append("  ⚠ Financial identifiers exist ONLY in narrative text. No financial table exists")
        L.append("    in the FIR schema. Every link above is cited to its source FIR and text span.")
        L.append("╚" + "═" * 68 + "╝")
        return "\n".join(L)


if __name__ == "__main__":
    from loader import RelationalStore
    from graph_store import NetworkXGraphStore
    from build_graph import build
    from extract import enrich
    from resolve import resolve

    store = RelationalStore(":memory:"); store.build(verbose=False)
    graph = NetworkXGraphStore(); build(store, graph); enrich(store, graph)
    _, _, _, groups, _ = resolve(store, graph)
    M = MoneyTrailAnalyser(store, graph, groups)

    print("=== COMPONENT 14: FINANCIAL CRIME & MONEY-TRAIL ANALYSIS ===\n")
    import json
    gt = json.load(open("../01_data_generator/ground_truth.json", encoding="utf-8"))
    setD = gt["seeded_connections"]["set_D_money_trail"]

    multi = M.multi_case_accounts(min_cases=2)
    print(f"--- Financial accounts appearing in MULTIPLE FIRs: {len(multi)} found ---")
    for m in multi[:5]:
        print(f"  {m['account']:<28} {m['case_count']} cases  {m['cases']}")

    print(f"\n--- VERIFYING against the SEEDED money trail (ground truth) ---")
    print(f"  seeded account : {setD['upi']}")
    print(f"  seeded cases   : {setD['fir_ids']}")
    print(f"  seeded controller: {setD['controller']}")
    net = M.suspicious_network(setD["upi"])
    found_cases = net["direct_cases"]
    ok_cases = set(found_cases) == set(setD["fir_ids"])
    ok_ident = len(net["resolved_identities"]) == 1
    print(f"  -> recovered cases      : {found_cases}  {'MATCH' if ok_cases else 'MISMATCH'}")
    print(f"  -> resolved controller  : {net['resolved_identities']}  "
          f"{'SINGLE CONTROLLER FOUND' if ok_ident else 'controller not resolved'}")
    print()
    print(M.render(net))
    store.close()
