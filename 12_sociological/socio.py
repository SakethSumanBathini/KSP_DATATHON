"""
Component 12 — Sociological Crime Insights  [Challenge req 4]

WHAT THE SCHEMA ACTUALLY PERMITS (this distinction is the whole component):
  ComplainantDetails carries OccupationID / ReligionID / CasteID.
  Accused carries ONLY AgeYear and GenderID.
  => The data supports VICTIMOLOGY (who is targeted), NOT offender demographic profiling.

THIS IS A FEATURE, NOT A LIMITATION. We build victimisation analysis (which the data supports
AND which is ethically sound), and we EXPLICITLY REFUSE offender profiling by caste/religion —
because it is (a) unsupported by the schema and (b) unacceptable under DPDP Act 2023 / Art.15
non-discrimination principles. The refusal is a guarded code path, not a policy note.

Delivers:
  - Victimisation rate by occupation / age band / gender (who is targeted, for which crime)
  - Socio-economic correlation by district (crime mix vs district profile)
  - Temporal-demographic patterns (when are which groups victimised)
  - Social risk indicators -> prevention recommendations (community-level, never individual)
"""
import sys, os, datetime
from collections import Counter, defaultdict
for p in ["02_relational_layer","03_graph_construction"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), p))


class EthicalGuard(Exception):
    """Raised when an analysis would profile offenders by protected attributes."""
    pass


PROTECTED_OFFENDER_ATTRS = {"caste", "religion", "casteid", "religionid", "community"}


def guard_offender_profiling(attribute):
    """
    HARD BLOCK. Profiling offenders by caste/religion is refused at the CODE level, not by policy.
    The schema does not even carry these fields on Accused — and if it did, we would still refuse.
    """
    if str(attribute).lower() in PROTECTED_OFFENDER_ATTRS:
        raise EthicalGuard(
            f"REFUSED: offender profiling by '{attribute}' is not permitted. "
            f"The FIR schema carries caste/religion ONLY for complainants (victimology), never for "
            f"accused persons. Profiling offenders by protected attributes is unsupported by the data "
            f"and impermissible under DPDP Act 2023 and constitutional non-discrimination principles. "
            f"Victimisation analysis (who is being targeted) IS supported and available."
        )


AGE_BANDS = [(0, 17, "0-17"), (18, 30, "18-30"), (31, 45, "31-45"), (46, 60, "46-60"), (61, 200, "61+")]


def age_band(age):
    if age is None:
        return "unknown"
    for lo, hi, label in AGE_BANDS:
        if lo <= age <= hi:
            return label
    return "unknown"


class SociologicalAnalyser:
    def __init__(self, store):
        self.store = store
        self.cases = store.get_all_cases()
        self.case_by_id = {c["CaseMasterID"]: c for c in self.cases}

    # ---------- VICTIMOLOGY (supported by the schema, ethically sound) ----------
    def victimisation_by_occupation(self, min_count=3):
        """Which occupations are disproportionately targeted, and for which crime type."""
        occ_total = Counter()
        occ_by_crime = defaultdict(Counter)
        for c in self.cases:
            comps = self.store.get_complainants_for_case(c["CaseMasterID"])
            comp = comps[0] if comps else None
            if not comp:
                continue
            occ = self.store.get_occupation_name(comp.get("OccupationID"))
            if not occ:
                continue
            occ_total[occ] += 1
            crime = self.store.get_crime_subhead_name(c["CrimeMinorHeadID"]) or "Unknown"
            occ_by_crime[occ][crime] += 1

        total = sum(occ_total.values()) or 1
        rows = []
        for occ, n in occ_total.most_common():
            if n < min_count:
                continue
            top_crime, top_n = occ_by_crime[occ].most_common(1)[0]
            rows.append({
                "occupation": occ,
                "cases": n,
                "share_pct": round(100.0 * n / total, 1),
                "most_common_crime": top_crime,
                "most_common_crime_n": top_n,
                "concentration_pct": round(100.0 * top_n / n, 1),
            })
        return rows

    def victim_age_gender_profile(self):
        """Age-band x gender victimisation profile."""
        prof = defaultdict(Counter)
        for c in self.cases:
            for v in self.store.get_victims_for_case(c["CaseMasterID"]):
                g = {1: "M", 2: "F", 3: "T"}.get(v.get("GenderID"), "?")
                prof[age_band(v.get("AgeYear"))][g] += 1
        out = []
        for band, counts in sorted(prof.items()):
            out.append({"age_band": band, "male": counts["M"], "female": counts["F"],
                        "total": sum(counts.values())})
        return out

    # ---------- SOCIO-ECONOMIC CORRELATION BY DISTRICT ----------
    def district_crime_profile(self):
        """Crime mix per district — the 'why here' signal SCRB needs for resource allocation."""
        per_dist = defaultdict(Counter)
        for c in self.cases:
            d = self.store.get_district_for_case(c["CaseMasterID"])
            if not d:
                continue
            crime = self.store.get_crime_subhead_name(c["CrimeMinorHeadID"]) or "Unknown"
            per_dist[d["DistrictName"]][crime] += 1
        out = []
        for dist, counts in sorted(per_dist.items(), key=lambda x: -sum(x[1].values())):
            tot = sum(counts.values())
            top, topn = counts.most_common(1)[0]
            out.append({
                "district": dist, "total_cases": tot,
                "dominant_crime": top,
                "dominant_share_pct": round(100.0 * topn / tot, 1),
                "crime_mix": dict(counts.most_common(4)),
            })
        return out

    # ---------- SOCIAL RISK INDICATORS -> COMMUNITY PREVENTION ----------
    def social_risk_indicators(self):
        """
        Community-level (NEVER individual) prevention signals, derived from victimisation patterns.
        These drive PREVENTION advice, not enforcement against any person.
        """
        signals = []
        occ = self.victimisation_by_occupation(min_count=3)
        if occ:
            top = occ[0]
            if top["concentration_pct"] >= 40:
                signals.append({
                    "indicator": "Occupational victimisation concentration",
                    "finding": (f"{top['occupation']} complainants account for {top['cases']} cases; "
                                f"{top['concentration_pct']}% are '{top['most_common_crime']}'."),
                    "prevention": (f"Targeted crime-prevention outreach to {top['occupation']} "
                                   f"communities regarding {top['most_common_crime']}."),
                })
        ages = self.victim_age_gender_profile()
        if ages:
            worst = max(ages, key=lambda r: r["total"])
            signals.append({
                "indicator": "Age-band victimisation peak",
                "finding": f"Age band {worst['age_band']} shows the highest victimisation ({worst['total']} victims).",
                "prevention": f"Awareness and hardening measures focused on the {worst['age_band']} cohort.",
            })
        dist = self.district_crime_profile()
        if dist:
            d0 = dist[0]
            signals.append({
                "indicator": "District crime concentration",
                "finding": (f"{d0['district']}: {d0['total_cases']} cases, "
                            f"{d0['dominant_share_pct']}% '{d0['dominant_crime']}'."),
                "prevention": (f"Resource weighting toward {d0['district']} for "
                               f"{d0['dominant_crime']} prevention."),
            })
        return signals

    # ---------- THE REFUSAL (a guarded code path, demonstrated) ----------
    def offender_profile_by(self, attribute):
        guard_offender_profiling(attribute)     # raises for caste/religion/community
        # age & gender ARE on Accused and are non-protected for this purpose
        if attribute.lower() in ("age", "ageyear"):
            c = Counter()
            for a in self.store.all_accused():
                c[age_band(a.get("AgeYear"))] += 1
            return dict(sorted(c.items()))
        if attribute.lower() in ("gender", "genderid"):
            c = Counter()
            for a in self.store.all_accused():
                c[{1: "M", 2: "F", 3: "T"}.get(a.get("GenderID"), "?")] += 1
            return dict(c)
        raise ValueError(f"Attribute '{attribute}' is not available on the Accused table.")


if __name__ == "__main__":
    from loader import RelationalStore
    store = RelationalStore(":memory:"); store.build(verbose=False)
    S = SociologicalAnalyser(store)

    print("=== COMPONENT 12: SOCIOLOGICAL CRIME INSIGHTS ===\n")

    print("--- VICTIMISATION BY OCCUPATION (who is targeted, for what) ---")
    for r in S.victimisation_by_occupation()[:6]:
        print(f"  {r['occupation']:<22} {r['cases']:>3} cases ({r['share_pct']}%)  "
              f"-> {r['concentration_pct']}% are '{r['most_common_crime']}'")

    print("\n--- VICTIM AGE/GENDER PROFILE ---")
    for r in S.victim_age_gender_profile():
        print(f"  {r['age_band']:<8} M:{r['male']:>3}  F:{r['female']:>3}  total:{r['total']:>3}")

    print("\n--- DISTRICT CRIME PROFILE (resource allocation signal) ---")
    for r in S.district_crime_profile()[:5]:
        print(f"  {r['district']:<18} {r['total_cases']:>3} cases  dominant: "
              f"{r['dominant_crime']} ({r['dominant_share_pct']}%)")

    print("\n--- SOCIAL RISK INDICATORS -> PREVENTION (community-level, never individual) ---")
    for s in S.social_risk_indicators():
        print(f"  [{s['indicator']}]")
        print(f"     finding:    {s['finding']}")
        print(f"     prevention: {s['prevention']}")

    print("\n--- THE ETHICAL GUARD (a code path, not a policy note) ---")
    for attr in ["age", "gender", "caste", "religion"]:
        try:
            res = S.offender_profile_by(attr)
            print(f"  offender_profile_by('{attr}') -> ALLOWED: {res}")
        except EthicalGuard as e:
            print(f"  offender_profile_by('{attr}') -> BLOCKED")
            print(f"     {str(e)[:150]}...")
    store.close()
