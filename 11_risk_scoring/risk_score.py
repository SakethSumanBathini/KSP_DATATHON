"""
Component 11 — Criminological Offender Risk Scoring  [Challenge req 5]
"Risk scoring of offenders to prioritize investigation."

ETHICAL LINE (stated explicitly, because a government jury will ask):
  This scores KNOWN offenders on their RECORDED history to prioritise INVESTIGATIVE ATTENTION.
  It does NOT predict who will commit a crime. It does NOT score members of the public.
  It does NOT use caste / religion / occupation (the schema carries those only for COMPLAINANTS,
  and using them to profile offenders would be both unsupported by the data and unacceptable).
  Every factor is derived from recorded FIR facts and is fully cited and explainable.

SIX CRIMINOLOGY-GROUNDED FACTORS (all from recorded data, all citable):
  1. Prior offence count       — chronic-offender literature: a small % of offenders commit a
                                 large share of crime (Wolfgang's Philadelphia cohort finding).
                                 ONLY VISIBLE BECAUSE OF OUR ENTITY RESOLUTION (the moat).
  2. Offence gravity escalation— trend in GravityOffenceID over time (de-escalating vs escalating).
  3. Network centrality        — degree in the crime graph (co-offenders + shared evidence).
  4. Recency                   — days since most recent linked offence (recent = active).
  5. Geographic spread         — number of distinct districts (mobility / organised activity).
  6. Co-offender count         — distinct people linked via shared evidence (group activity).

Output: 0-100 score, a BAND, and a per-factor explanation with citations. Never a black box.
"""
import sys, os, datetime, math
for p in ["02_relational_layer","03_graph_construction","04_extraction","05_entity_resolution","06_retrieval"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(os.getcwd())), "ksp_datathon", p))
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), p))

from build_graph import person_id, fir_id

# Weights: sum to 100. Chosen to reflect criminology priors (priors + escalation dominate).
WEIGHTS = {
    "prior_offences":   30,
    "escalation":       20,
    "network_centrality":15,
    "recency":          15,
    "geographic_spread":10,
    "co_offenders":     10,
}

BANDS = [(70, "HIGH"), (40, "MEDIUM"), (0, "LOW")]


def _band(score):
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return "LOW"


class OffenderRiskScorer:
    """Scores a RESOLVED identity (not a raw Accused row) — resolution is what makes this possible."""

    def __init__(self, store, graph, resolved_groups):
        self.store = store
        self.graph = graph
        self.groups = resolved_groups
        self.identity_of = {}
        for gi, g in enumerate(resolved_groups):
            for amid in g:
                self.identity_of[amid] = gi
        self.by_id = {a["AccusedMasterID"]: a for a in store.all_accused()}
        # newest registered date in the corpus = "today" for recency purposes
        dates = []
        for c in store.get_all_cases():
            try:
                dates.append(datetime.datetime.fromisoformat(c["CrimeRegisteredDate"]))
            except Exception:
                pass
        self.corpus_latest = max(dates) if dates else datetime.datetime.now()

    def _identity_members(self, accused_id):
        gi = self.identity_of.get(accused_id)
        if gi is None:
            return [accused_id]
        return sorted(self.groups[gi])

    def score(self, accused_id):
        members = self._identity_members(accused_id)
        cases = []
        for amid in members:
            a = self.by_id.get(amid)
            if a:
                c = self.store.get_case(a["CaseMasterID"])
                if c:
                    cases.append(c)
        if not cases:
            return None

        case_ids = sorted({c["CaseMasterID"] for c in cases})
        factors = {}

        # --- 1. prior offence count (chronic offender) ---
        n_prior = len(case_ids)
        # saturating curve: 1 case -> 0, 5+ cases -> full marks
        f_prior = min(1.0, math.log(n_prior) / math.log(5)) if n_prior > 1 else 0.0
        factors["prior_offences"] = {
            "value": n_prior,
            "normalised": round(f_prior, 3),
            "explanation": f"Linked to {n_prior} recorded case(s) after cross-case identity resolution.",
            "citations": case_ids,
        }

        # --- 2. gravity escalation ---
        timeline = []
        for c in cases:
            try:
                d = datetime.datetime.fromisoformat(c["CrimeRegisteredDate"])
                timeline.append((d, c["GravityOffenceID"], c["CaseMasterID"]))
            except Exception:
                pass
        timeline.sort()
        f_esc, esc_desc = 0.0, "Insufficient history to assess escalation."
        if len(timeline) >= 2:
            first_g, last_g = timeline[0][1], timeline[-1][1]
            # LOWER GravityOffenceID = MORE severe (1=Heinous). Escalation = gravity id DECREASES.
            delta = first_g - last_g
            if delta > 0:
                f_esc = min(1.0, delta / 2.0)
                esc_desc = (f"ESCALATING: offence gravity worsened from level {first_g} "
                            f"(FIR {timeline[0][2]}) to level {last_g} (FIR {timeline[-1][2]}).")
            elif delta < 0:
                f_esc = 0.0
                esc_desc = (f"De-escalating: gravity moved from level {first_g} to {last_g}.")
            else:
                f_esc = 0.35
                esc_desc = f"Stable offence gravity (level {last_g}) across {len(timeline)} cases."
        factors["escalation"] = {
            "value": esc_desc.split(":")[0],
            "normalised": round(f_esc, 3),
            "explanation": esc_desc,
            "citations": [t[2] for t in timeline],
        }

        # --- 3. network centrality (graph degree over shared evidence + co-accused) ---
        degree = 0
        linked_entities = []
        for amid in members:
            pid = person_id(amid)
            if self.graph.get_node(pid) is None:
                continue
            for nb in self.graph.neighbors(pid):
                nb_id = nb if isinstance(nb, str) else nb[0]
                degree += 1
                if str(nb_id).startswith(("Phone:", "Vehicle:", "FinancialAccount:")):
                    linked_entities.append(nb_id)
        f_cent = min(1.0, degree / 12.0)
        factors["network_centrality"] = {
            "value": degree,
            "normalised": round(f_cent, 3),
            "explanation": (f"Graph degree {degree}: connected to {len(set(linked_entities))} "
                            f"distinct physical/financial entities across their cases."),
            "citations": case_ids,
        }

        # --- 4. recency ---
        if timeline:
            days_since = (self.corpus_latest - timeline[-1][0]).days
            f_rec = max(0.0, 1.0 - days_since / 180.0)   # active in last 6 months -> high
            rec_desc = f"Most recent linked offence {days_since} day(s) before the latest record in the corpus."
        else:
            f_rec, days_since, rec_desc = 0.0, None, "No dated offences."
        factors["recency"] = {
            "value": days_since,
            "normalised": round(f_rec, 3),
            "explanation": rec_desc,
            "citations": [timeline[-1][2]] if timeline else [],
        }

        # --- 5. geographic spread ---
        districts = set()
        for c in cases:
            d = self.store.get_district_for_case(c["CaseMasterID"])
            if d:
                districts.add(d["DistrictName"])
        f_geo = min(1.0, (len(districts) - 1) / 2.0) if len(districts) > 1 else 0.0
        factors["geographic_spread"] = {
            "value": len(districts),
            "normalised": round(f_geo, 3),
            "explanation": (f"Active across {len(districts)} district(s): {sorted(districts)}."
                            + (" Cross-district activity indicates mobility/organisation."
                               if len(districts) > 1 else "")),
            "citations": case_ids,
        }

        # --- 6. co-offenders (distinct other people sharing evidence/cases) ---
        co = set()
        for c in cases:
            for a in self.store.get_accused_for_case(c["CaseMasterID"]):
                other = a["AccusedMasterID"]
                if other not in members:
                    co.add(self.identity_of.get(other, f"raw:{other}"))
        f_co = min(1.0, len(co) / 4.0)
        factors["co_offenders"] = {
            "value": len(co),
            "normalised": round(f_co, 3),
            "explanation": f"{len(co)} distinct co-accused identities appear in the same cases.",
            "citations": case_ids,
        }

        # --- weighted score ---
        total = sum(WEIGHTS[k] * factors[k]["normalised"] for k in WEIGHTS)
        score = round(total, 1)
        for k in WEIGHTS:
            factors[k]["weight"] = WEIGHTS[k]
            factors[k]["points"] = round(WEIGHTS[k] * factors[k]["normalised"], 1)

        name = self.by_id[members[0]]["AccusedName"] if members else "?"
        return {
            "accused_id": accused_id,
            "identity": f"Identity:{self.identity_of.get(accused_id, 'unresolved')}",
            "name": name,
            "linked_cases": case_ids,
            "risk_score": score,
            "risk_band": _band(score),
            "factors": factors,
            "citations": case_ids,
            "disclaimer": ("Investigative prioritisation only, computed from recorded FIR facts. "
                           "Not a prediction of future offending. No demographic attributes used. "
                           "A human officer verifies before any action."),
        }

    def rank_offenders(self, top_n=10):
        """Rank all RESOLVED (multi-case) identities by risk — the SCRB 'who to look at first' view."""
        out = []
        seen = set()
        for gi, g in enumerate(self.groups):
            if len(g) < 2:
                continue                       # only resolved repeat offenders
            rep = sorted(g)[0]
            if rep in seen:
                continue
            seen.add(rep)
            s = self.score(rep)
            if s:
                out.append(s)
        out.sort(key=lambda x: -x["risk_score"])
        return out[:top_n]


def render(s):
    L = [f"╔══ OFFENDER RISK ASSESSMENT — {s['name']} [{s['identity']}] ══╗",
         f"  RISK SCORE: {s['risk_score']}/100   BAND: {s['risk_band']}",
         f"  Linked cases: {s['linked_cases']}",
         "",
         "  FACTOR BREAKDOWN (every point is explained and cited):"]
    for k, f in s["factors"].items():
        L.append(f"    {k:<20} {f['points']:>5}/{f['weight']:<3} pts  — {f['explanation']}")
    L.append("")
    L.append(f"  ⚠ {s['disclaimer']}")
    L.append("╚" + "═" * 70 + "╝")
    return "\n".join(L)


if __name__ == "__main__":
    import json
    from loader import RelationalStore
    from graph_store import NetworkXGraphStore
    from build_graph import build
    from extract import enrich
    from resolve import resolve

    store = RelationalStore(":memory:"); store.build(verbose=False)
    graph = NetworkXGraphStore(); build(store, graph); enrich(store, graph)
    _, _, _, groups, _ = resolve(store, graph)
    scorer = OffenderRiskScorer(store, graph, groups)

    print("=== COMPONENT 11: CRIMINOLOGICAL OFFENDER RISK SCORING ===\n")
    print("--- SCRB view: ranked repeat offenders (who to prioritise) ---\n")
    ranked = scorer.rank_offenders(top_n=5)
    for r in ranked:
        print(f"  {r['risk_band']:<7} {r['risk_score']:>5}/100  {r['name']:<20} "
              f"{len(r['linked_cases'])} cases  {r['identity']}")
    print()
    print("--- Full explainable assessment for the top offender ---\n")
    print(render(ranked[0]))
    store.close()
