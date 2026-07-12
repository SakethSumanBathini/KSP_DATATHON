"""
Component 17 — Algorithmic Fairness / Disparate-Impact Audit

THE QUESTION A GOVERNMENT AI ETHICS REVIEW WILL ASK, AND WE HAD NOT ANSWERED:

  "You say you never use caste or religion. Fine. But does your risk score PROXY them?"

This is the real danger with 'neutral' features. In India, geography correlates with caste and
community. If our risk score leans on district, or on crime type, and those correlate with a
protected attribute, then we have laundered discrimination through a feature that merely LOOKS
neutral. Not using a variable is NOT the same as not being influenced by it.

So we TEST it rather than assert it:

  1. DISPARATE IMPACT — do high-risk flags land disproportionately on cases whose complainants
     come from one caste/religion group? (Complainant demographics are the ONLY demographics the
     schema carries, so they are our only measurable proxy channel.)
     Measure: selection rate per group, and the 4/5ths rule (US EEOC; the standard heuristic).

  2. PROXY LEAKAGE — can a protected attribute be PREDICTED from the risk score alone?
     If it can, the score is carrying that information whether we intended it or not.

  3. FEATURE AUDIT — enumerate exactly what enters the score, so nobody has to trust us.

An honest negative result is still a result. If we find bias, we say so and mitigate.
"""
import sys, os, json
from collections import defaultdict, Counter
for p in ["02_relational_layer","03_graph_construction","04_extraction","05_entity_resolution",
          "11_risk_scoring"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), p))


def four_fifths(rates):
    """EEOC 4/5ths rule: min selection rate / max selection rate >= 0.8, else adverse impact."""
    vals = [r for r in rates.values() if r is not None]
    if not vals or max(vals) == 0:
        return None
    return min(vals) / max(vals)


def audit(store, scorer, groups):
    accused = {a["AccusedMasterID"]: a for a in store.all_accused()}

    # score every RESOLVED identity, and attach the demographics of the cases they appear in
    scored = []
    for gi, g in enumerate(groups):
        rep = sorted(g)[0]
        s = scorer.score(rep)
        if not s:
            continue
        castes, religions, occs, districts = set(), set(), set(), set()
        for cid in s["linked_cases"]:
            for cp in store.get_complainants_for_case(cid):
                c = store.get_caste_name(cp.get("CasteID"))
                r = store.get_religion_name(cp.get("ReligionID"))
                o = store.get_occupation_name(cp.get("OccupationID"))
                if c: castes.add(c)
                if r: religions.add(r)
                if o: occs.add(o)
            d = store.get_district_for_case(cid)
            if d: districts.add(d["DistrictName"])
        scored.append({"score": s["risk_score"], "band": s["risk_band"],
                       "castes": castes, "religions": religions,
                       "occupations": occs, "districts": districts})

    print("=== 1. FEATURE AUDIT — exactly what enters the risk score ===")
    from risk_score import WEIGHTS
    for k, w in WEIGHTS.items():
        print(f"    {k:<20} weight {w}")
    print("    protected attributes used: NONE (caste/religion/occupation are not inputs)")
    print(f"    NOTE: 'geographic_spread' IS an input (weight {WEIGHTS['geographic_spread']}). "
          f"Geography can proxy caste. That is precisely why we test below.")

    print("\n=== 2. DISPARATE IMPACT — where do HIGH-RISK flags land? ===")
    for attr in ("castes", "religions"):
        flagged = defaultdict(int)
        total = defaultdict(int)
        for s in scored:
            for v in s[attr]:
                total[v] += 1
                if s["band"] in ("HIGH", "MEDIUM"):
                    flagged[v] += 1
        rates = {v: (flagged[v] / total[v] if total[v] else None) for v in total}
        print(f"\n  by complainant {attr[:-1]}:")
        for v in sorted(total, key=lambda x: -total[x]):
            r = rates[v]
            print(f"    {v:<20} flagged {flagged[v]:>2}/{total[v]:<2}  selection rate "
                  f"{('%.2f' % r) if r is not None else 'n/a'}")
        ratio = four_fifths(rates)
        if ratio is None:
            print("    -> insufficient data for a 4/5ths determination")
        else:
            verdict = "PASS (no adverse impact)" if ratio >= 0.8 else "FAIL — ADVERSE IMPACT"
            print(f"    -> 4/5ths ratio = {ratio:.2f}  [{verdict}]")

    print("\n=== 3. PROXY LEAKAGE — can the score PREDICT a protected attribute? ===")
    # If knowing the score tells you the caste better than chance, the score carries caste info.
    all_castes = Counter()
    for s in scored:
        for c in s["castes"]:
            all_castes[c] += 1
    if len(all_castes) < 2:
        print("    too few groups in the sample to test leakage meaningfully")
    else:
        hi = [s for s in scored if s["band"] in ("HIGH", "MEDIUM")]
        lo = [s for s in scored if s["band"] == "LOW"]
        def dist(rows):
            c = Counter()
            for s in rows:
                for x in s["castes"]:
                    c[x] += 1
            tot = sum(c.values()) or 1
            return {k: v/tot for k, v in c.items()}
        dh, dl = dist(hi), dist(lo)
        keys = set(dh) | set(dl)
        tvd = 0.5 * sum(abs(dh.get(k,0) - dl.get(k,0)) for k in keys)   # total variation distance
        print(f"    caste distribution | HIGH/MED risk : "
              f"{ {k: round(v,2) for k,v in sorted(dh.items())} }")
        print(f"    caste distribution | LOW risk      : "
              f"{ {k: round(v,2) for k,v in sorted(dl.items())} }")
        print(f"    total-variation distance = {tvd:.3f}   (0 = score carries NO caste signal)")
        if tvd > 0.35:
            print("    -> ⚠ the score's caste distribution differs materially by risk band.")
            print("       This is a PROXY WARNING: investigate before any deployment.")
        else:
            print("    -> no material proxy signal detected at this sample size.")

    print("\n=== 4. HONEST LIMITS OF THIS AUDIT ===")
    print("    - Sample is tiny (resolved repeat offenders only). These statistics are")
    print("      INDICATIVE, not conclusive. On real KSP data this must be re-run at scale.")
    print("    - Complainant demographics are an imperfect proxy channel; offender demographics")
    print("      do not exist in the schema (by design, and rightly).")
    print("    - A PASS here does NOT certify fairness. It certifies that we LOOKED, with a")
    print("      stated method, and published the result — which is the minimum bar for a")
    print("      government-deployed system.")


if __name__ == "__main__":
    from loader import RelationalStore
    from graph_store import NetworkXGraphStore
    from build_graph import build
    from extract import enrich
    from resolve import resolve
    from risk_score import OffenderRiskScorer

    store = RelationalStore(":memory:"); store.build(verbose=False)
    graph = NetworkXGraphStore(); build(store, graph); enrich(store, graph)
    _, _, _, groups, _ = resolve(store, graph)
    scorer = OffenderRiskScorer(store, graph, groups)

    print("=== COMPONENT 17: ALGORITHMIC FAIRNESS / DISPARATE-IMPACT AUDIT ===\n")
    audit(store, scorer, groups)
    store.close()
