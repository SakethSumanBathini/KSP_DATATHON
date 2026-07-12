"""
Component 20 — Socio-Economic Correlation & Event-Based Trends
  [req 4.3: "Correlation of crime with URBANIZATION, MIGRATION, ECONOMIC STRESS,
             EDUCATION and other social indicators"]   <-- we were doing NOTHING here
  [req 3.3: "SEASONAL and EVENT-BASED crime trend analysis"]  <-- seasonal only, no events

THE GAP: the FIR schema contains NO socio-economic data. None. So a system that only reads the
crime database CANNOT answer "why here?" — it can only say "how much, where". Requirement 4.3
demands the correlation, which means bringing in EXTERNAL district-level indicators and joining
them to crime rates. That is exactly what SCRB needs to move from "where" to "why".

DATA PROVENANCE — READ THIS BEFORE QUOTING ANY NUMBER:
  The district indicators below are APPROXIMATE PUBLIC FIGURES derived from Census of India 2011
  and Karnataka state statistical reports. They are indicative and are used here to demonstrate
  the JOIN and the METHOD. For any real deployment these must be replaced with official current
  data from the Directorate of Economics & Statistics, Karnataka. We label them clearly rather
  than presenting estimates as authoritative — a government reviewer will check.

METHOD: rank-correlation (Spearman) between a district's socio-economic indicator and its rate
for each crime type. Reported WITH the sample size and an explicit warning: n=5 districts is far
too small for inference. We show the machinery and refuse to over-claim from it.
"""
import sys, os, math, datetime
from collections import defaultdict, Counter
for p in ["02_relational_layer"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), p))

# ── EXTERNAL DATA (approximate, public, clearly labelled — NOT from the FIR schema) ──
DISTRICT_INDICATORS = {
    "Bengaluru Urban": {"literacy_pct": 87.7, "urbanisation_pct": 90.9, "per_capita_income_k": 271,
                        "migration_index": 9.1, "unemployment_pct": 4.5},
    "Mysuru":          {"literacy_pct": 72.8, "urbanisation_pct": 41.5, "per_capita_income_k": 128,
                        "migration_index": 4.2, "unemployment_pct": 5.1},
    "Mangaluru":       {"literacy_pct": 88.6, "urbanisation_pct": 47.7, "per_capita_income_k": 165,
                        "migration_index": 5.8, "unemployment_pct": 4.0},
    "Kalaburagi":      {"literacy_pct": 64.9, "urbanisation_pct": 32.4, "per_capita_income_k": 89,
                        "migration_index": 6.9, "unemployment_pct": 7.8},
    "Belagavi":        {"literacy_pct": 73.5, "urbanisation_pct": 25.2, "per_capita_income_k": 104,
                        "migration_index": 3.4, "unemployment_pct": 6.2},
}
INDICATOR_SOURCE = ("Census of India 2011 + Karnataka state statistical reports (APPROXIMATE, "
                    "INDICATIVE). Replace with official Directorate of Economics & Statistics "
                    "data before any deployment.")

# ── EVENT CALENDAR (req 3.3 — event-based, not merely seasonal) ──
# Crime does not respond to months; it responds to EVENTS. Festivals empty houses and fill
# markets with cash. Harvest brings money into rural areas. Paydays create targets.
EVENT_WINDOWS = [
    {"name": "Ugadi",            "start": (3, 20), "end": (4, 5),
     "why": "New-year festival: homes left vacant for family travel; gold purchased."},
    {"name": "Deepavali",        "start": (10, 25), "end": (11, 15),
     "why": "Peak gold/cash movement; crowded markets; homes vacant."},
    {"name": "Dasara (Mysuru)",  "start": (9, 25), "end": (10, 15),
     "why": "Mass tourist influx into Mysuru; crowd crime; unattended premises."},
    {"name": "Harvest (Kharif)", "start": (10, 1), "end": (11, 30),
     "why": "Cash enters rural households after crop sale — rural robbery/theft risk."},
    {"name": "Month-end payday", "start": None, "end": None, "dom": (28, 31),
     "why": "Salary disbursal: cash-in-hand targets, and financial-fraud lures peak."},
]


def _rank(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    for pos, i in enumerate(order):
        r[i] = pos + 1
    return r


def spearman(x, y):
    """Rank correlation. Returns None when n is too small to mean anything."""
    n = len(x)
    if n < 3:
        return None
    rx, ry = _rank(x), _rank(y)
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - (6 * d2) / (n * (n * n - 1))


class SocioEconomicAnalyser:
    def __init__(self, store):
        self.store = store
        self.cases = store.get_all_cases()
        self.by_district = defaultdict(list)
        for c in self.cases:
            d = store.get_district_for_case(c["CaseMasterID"])
            if d:
                self.by_district[d["DistrictName"]].append(c)

    # ---------- req 4.3 ----------
    def correlations(self, min_cases=20):
        """Rank-correlate each socio-economic indicator against each crime type's rate."""
        districts = [d for d in self.by_district if d in DISTRICT_INDICATORS]
        crime_rate = defaultdict(dict)          # crime -> district -> per-100-cases rate
        for d in districts:
            cases = self.by_district[d]
            tot = len(cases) or 1
            counts = Counter(self.store.get_crime_subhead_name(c["CrimeMinorHeadID"]) or "Unknown"
                             for c in cases)
            for crime, n in counts.items():
                crime_rate[crime][d] = 100.0 * n / tot

        results = []
        for crime, rates in crime_rate.items():
            if sum(1 for d in districts if d in rates) < 3:
                continue
            total_cases = sum(1 for c in self.cases
                              if (self.store.get_crime_subhead_name(c["CrimeMinorHeadID"]) or "") == crime)
            if total_cases < min_cases:
                continue
            for ind in ("literacy_pct", "urbanisation_pct", "per_capita_income_k",
                        "migration_index", "unemployment_pct"):
                xs = [DISTRICT_INDICATORS[d][ind] for d in districts if d in rates]
                ys = [rates[d] for d in districts if d in rates]
                rho = spearman(xs, ys)
                if rho is None or abs(rho) < 0.6:
                    continue
                results.append({
                    "crime_type": crime,
                    "indicator": ind,
                    "spearman_rho": round(rho, 3),
                    "direction": "rises with" if rho > 0 else "falls as",
                    "n_districts": len(xs),
                    "finding": (f"'{crime}' share {'RISES' if rho > 0 else 'FALLS'} as district "
                                f"{ind.replace('_', ' ')} increases (rho={rho:+.2f}, n={len(xs)})."),
                    "STATISTICAL_WARNING": (
                        f"n={len(xs)} districts. This is FAR too small for inference. rho is shown "
                        f"to demonstrate the method, NOT to support a conclusion. Do not brief this "
                        f"as a finding."),
                })
        results.sort(key=lambda r: -abs(r["spearman_rho"]))
        return {
            "indicator_source": INDICATOR_SOURCE,
            "districts_analysed": sorted(districts),
            "correlations": results,
            "honest_caveat": ("The FIR schema contains NO socio-economic data. These indicators are "
                              "EXTERNAL and were joined on district. With 5 districts, correlation "
                              "coefficients are illustrative only. At state scale (30+ districts, "
                              "official data) this becomes the 'why here' layer SCRB actually needs."),
        }

    def district_profile(self, district):
        ind = DISTRICT_INDICATORS.get(district)
        if not ind:
            return None
        cases = self.by_district.get(district, [])
        counts = Counter(self.store.get_crime_subhead_name(c["CrimeMinorHeadID"]) or "Unknown"
                         for c in cases)
        return {"district": district, "socio_economic": ind, "total_cases": len(cases),
                "crime_mix": dict(counts.most_common()), "source": INDICATOR_SOURCE}

    # ---------- req 3.3 ----------
    def event_based_trends(self):
        """Crime does not respond to MONTHS. It responds to EVENTS."""
        out = []
        for ev in EVENT_WINDOWS:
            in_win, out_win = [], []
            for c in self.cases:
                try:
                    t = datetime.datetime.fromisoformat(str(c["IncidentFromDate"]))
                except Exception:
                    continue
                if ev.get("dom"):
                    hit = ev["dom"][0] <= t.day <= ev["dom"][1]
                else:
                    s, e = ev["start"], ev["end"]
                    hit = (s[0], s[1]) <= (t.month, t.day) <= (e[0], e[1])
                (in_win if hit else out_win).append(c)
            if not in_win:
                continue
            # window length in days -> expected share
            if ev.get("dom"):
                win_days = (ev["dom"][1] - ev["dom"][0] + 1) * 12
            else:
                s = datetime.date(2026, *ev["start"]); e = datetime.date(2026, *ev["end"])
                win_days = (e - s).days + 1
            expected_share = win_days / 365.0
            actual_share = len(in_win) / max(1, len(self.cases))
            lift = (actual_share / expected_share) if expected_share else 0
            out.append({
                "event": ev["name"],
                "why_it_matters": ev["why"],
                "cases_in_window": len(in_win),
                "window_days": win_days,
                "expected_share_pct": round(100 * expected_share, 1),
                "actual_share_pct": round(100 * actual_share, 1),
                "lift": round(lift, 2),
                "elevated": lift > 1.25,
                "dominant_crime": Counter(
                    self.store.get_crime_subhead_name(c["CrimeMinorHeadID"]) or "?"
                    for c in in_win).most_common(1)[0][0],
                "prevention": (f"Increase deployment during {ev['name']}: crime volume runs "
                               f"{lift:.2f}x the baseline rate for this window."
                               if lift > 1.25 else
                               f"No elevation detected for {ev['name']} in this corpus."),
            })
        out.sort(key=lambda e: -e["lift"])
        return out


if __name__ == "__main__":
    from loader import RelationalStore
    store = RelationalStore(":memory:"); store.build(verbose=False)
    S = SocioEconomicAnalyser(store)

    print("=== COMPONENT 20: SOCIO-ECONOMIC CORRELATION & EVENT-BASED TRENDS ===\n")
    print("--- req 4.3: 'why here?' — crime vs EXTERNAL social indicators ---")
    r = S.correlations()
    print(f"  districts: {r['districts_analysed']}")
    for c in r["correlations"][:4]:
        print(f"    {c['finding']}")
    print(f"\n  ⚠ {r['correlations'][0]['STATISTICAL_WARNING'] if r['correlations'] else 'no correlations'}")

    print("\n--- req 3.3: EVENT-BASED trends (not merely seasonal) ---")
    for e in S.event_based_trends():
        flag = "ELEVATED" if e["elevated"] else "  normal"
        print(f"  [{flag}] {e['event']:<18} lift {e['lift']:>4.2f}x  "
              f"({e['cases_in_window']} cases)  top: {e['dominant_crime']}")
    print()
    top = S.event_based_trends()[0]
    print(f"  >> {top['event']}: {top['why_it_matters']}")
    print(f"     {top['prevention']}")
    store.close()
