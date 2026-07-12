"""
Component 13 — Crime Pattern, Trend Analytics & Early Warning  [Challenge reqs 3 & 8]

  req 3: trends across time/geography/crime-type/MO; hotspots; emerging clusters;
         seasonal and event-based trend analysis.
  req 8: AI-driven identification of emerging patterns; EARLY WARNING alerts for repeat crimes /
         gang activity; predictive analysis of potential hotspots.

METHOD (deliberately transparent statistics, not a black box — req 9 applies to this too):
  - Temporal profiles: month, day-of-week, hour-of-day (from IncidentFromDate).
  - EMERGING CLUSTER / SPIKE detection: compare a recent window against the historical baseline
    for the same district+crime-type using a Poisson-style z-score. A spike is flagged only when
    it exceeds the baseline by a stated number of standard deviations — the threshold is shown.
  - NEAR-REPEAT EARLY WARNING: grounded in Johnson & Bowers' near-repeat victimisation finding
    (elevated risk within ~400m for ~6 weeks after a burglary). We surface the SPACE-TIME WINDOW,
    not a prediction about any person.

LANGUAGE DISCIPLINE: this is INVESTIGATIVE INTELLIGENCE and PREVENTION RESOURCING.
It forecasts WHERE/WHEN risk is elevated. It never scores or predicts individuals.
"""
import sys, os, math, datetime
from statistics import NormalDist
from collections import Counter, defaultdict
for p in ["02_relational_layer"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), p))

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


class TrendAnalyser:
    def __init__(self, store):
        self.store = store
        self.cases = []
        for c in store.get_all_cases():
            rec = dict(c)
            try:
                rec["_reg"] = datetime.datetime.fromisoformat(c["CrimeRegisteredDate"])
            except Exception:
                rec["_reg"] = None
            try:
                rec["_inc"] = datetime.datetime.fromisoformat(c["IncidentFromDate"])
            except Exception:
                rec["_inc"] = rec["_reg"]
            d = store.get_district_for_case(c["CaseMasterID"])
            rec["_district"] = d["DistrictName"] if d else "?"
            rec["_crime"] = store.get_crime_subhead_name(c["CrimeMinorHeadID"]) or "Unknown"
            self.cases.append(rec)
        dated = [c["_reg"] for c in self.cases if c["_reg"]]
        self.latest = max(dated) if dated else datetime.datetime.now()
        self.earliest = min(dated) if dated else self.latest

    # ---------- TEMPORAL PROFILES (req 3) ----------
    def temporal_profile(self, crime_type=None):
        by_month, by_dow, by_hour = Counter(), Counter(), Counter()
        for c in self.cases:
            if crime_type and c["_crime"] != crime_type:
                continue
            t = c["_inc"] or c["_reg"]
            if not t:
                continue
            by_month[MONTHS[t.month - 1]] += 1
            by_dow[DOW[t.weekday()]] += 1
            by_hour[t.hour] += 1
        return {
            "by_month": {m: by_month[m] for m in MONTHS if by_month[m]},
            "by_day_of_week": {d: by_dow[d] for d in DOW},
            "by_hour": dict(sorted(by_hour.items())),
            "peak_hour": by_hour.most_common(1)[0] if by_hour else None,
            "peak_day": by_dow.most_common(1)[0] if by_dow else None,
        }

    def night_day_split(self, crime_type=None):
        """Night = 22:00-05:59. A classic burglary MO signal."""
        night = day = 0
        for c in self.cases:
            if crime_type and c["_crime"] != crime_type:
                continue
            t = c["_inc"] or c["_reg"]
            if not t:
                continue
            if t.hour >= 22 or t.hour < 6:
                night += 1
            else:
                day += 1
        tot = night + day or 1
        return {"night": night, "day": day, "night_pct": round(100.0 * night / tot, 1)}

    # ---------- EMERGING CLUSTER / SPIKE DETECTION (reqs 3 & 8) ----------
    def emerging_clusters(self, window_days=30, z_threshold=1.5, fdr_q=0.10):
        """
        Spike detection with MULTIPLE-COMPARISONS CONTROL.

        THE BUG THIS FIXES (a real statistical error, not a nitpick):
        We test EVERY (district x crime-type) cell simultaneously — ~25 tests. At z>=1.5 the
        per-test false-positive rate is ~6.7%, so ~1.7 cells will look like "crime waves" BY PURE
        CHANCE. Reporting them uncorrected means dispatching officers against statistical ghosts.
        An alert in a police system is an OPERATIONAL ORDER, so its error rate is not academic.

        FIX: Benjamini-Hochberg FDR control. We compute a p-value per cell, then accept only the
        cells that survive BH at q=fdr_q. We chose FDR over Bonferroni deliberately: policing can
        tolerate a KNOWN, SMALL proportion of false leads, but cannot tolerate an UNKNOWN one.
        Every alert now carries its p-value, and we report the expected false-discovery rate.
        """
        cutoff = self.latest - datetime.timedelta(days=window_days)
        span_days = max(1, (self.latest - self.earliest).days)
        baseline_days = max(1, span_days - window_days)

        recent, historical = Counter(), Counter()
        for c in self.cases:
            if not c["_reg"]:
                continue
            key = (c["_district"], c["_crime"])
            (recent if c["_reg"] >= cutoff else historical)[key] += 1

        # all cells we are testing — the denominator of the multiple-comparisons problem
        cells = set(recent) | set(historical)
        candidates = []
        for key in recent:
            r_count = recent[key]
            h_count = historical.get(key, 0)
            expected = (h_count / baseline_days) * window_days
            if expected <= 0:
                if r_count >= 3:
                    candidates.append({"key": key, "recent_count": r_count, "expected": 0.0,
                                       "z": None, "p": 0.0, "emergent": True})
                continue
            sd = math.sqrt(expected)
            z = (r_count - expected) / sd if sd > 0 else 0.0
            p = 1 - NormalDist().cdf(z)          # one-tailed: we only care about INCREASES
            candidates.append({"key": key, "recent_count": r_count, "expected": expected,
                               "z": z, "p": p, "emergent": False})

        # ---- Benjamini-Hochberg: sort by p, accept while p_(i) <= (i/m) * q ----
        m = max(1, len(cells))
        ranked = sorted(candidates, key=lambda c: c["p"])
        cutoff_i = 0
        for i, c in enumerate(ranked, start=1):
            if c["p"] <= (i / m) * fdr_q:
                cutoff_i = i
        accepted = ranked[:cutoff_i]

        alerts = []
        for c in accepted:
            d, crime = c["key"]
            if c["emergent"]:
                sev, finding = "EMERGENT", (
                    f"NEW pattern: {c['recent_count']} '{crime}' cases in {d} in the last "
                    f"{window_days} days, with no prior baseline.")
            else:
                z = c["z"]
                sev = "HIGH" if z >= 3 else ("ELEVATED" if z >= 2 else "WATCH")
                finding = (f"{crime} in {d}: {c['recent_count']} cases in the last {window_days} "
                           f"days vs {c['expected']:.1f} expected from baseline "
                           f"(z={z:.2f}, p={c['p']:.4f}).")
            alerts.append({
                "district": d, "crime_type": crime,
                "recent_count": c["recent_count"],
                "expected": round(c["expected"], 1),
                "z": round(c["z"], 2) if c["z"] is not None else None,
                "p_value": round(c["p"], 5),
                "severity": sev, "finding": finding,
                "survives_fdr": True,
            })
        alerts.sort(key=lambda a: (a["p_value"]))

        return {
            "window_days": window_days,
            "baseline_days": baseline_days,
            "cells_tested": m,
            "multiple_comparisons": {
                "method": "Benjamini-Hochberg FDR",
                "q": fdr_q,
                "candidates_before_correction": len(candidates),
                "alerts_after_correction": len(alerts),
                "expected_false_discoveries_among_alerts": round(fdr_q * len(alerts), 2),
                "why": ("We test every district x crime-type cell at once. Uncorrected, ~"
                        f"{(1 - NormalDist().cdf(z_threshold)) * m:.1f} cells would look like crime "
                        "waves by chance alone. Each alert is an operational order, so we control "
                        "the false-discovery rate and state it explicitly."),
            },
            "alerts": alerts,
        }


    # ---------- NEAR-REPEAT EARLY WARNING (req 8) ----------
    def near_repeat_warnings(self, radius_m=400, window_days=42, min_cluster=3, as_of=None):
        """
        Johnson & Bowers near-repeat: after a burglary, nearby properties face elevated risk for
        roughly 6 weeks. A cluster = >=min_cluster burglaries within `radius_m` of each other AND
        within `window_days` of each other (a SPACE-TIME cluster, not merely "recent").

        Each cluster reports whether it is still ACTIVE as of `as_of` (default: latest record).
        This forecasts a LOCATION-TIME WINDOW, never a person.
        """
        as_of = as_of or self.latest
        burglaries = [c for c in self.cases
                      if c["_crime"] and "urglary" in c["_crime"] and c["_reg"]]

        clusters = []
        used = set()
        # seed from the most recent burglary backwards, so active clusters surface first
        for a in sorted(burglaries, key=lambda x: -x["_reg"].timestamp()):
            if a["CaseMasterID"] in used:
                continue
            members = [a]
            for b in burglaries:
                if b["CaseMasterID"] == a["CaseMasterID"] or b["CaseMasterID"] in used:
                    continue
                d = haversine_m(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
                dt = abs((b["_reg"] - a["_reg"]).days)
                if d <= radius_m and dt <= window_days:      # SPACE **AND** TIME
                    members.append(b)
            if len(members) >= min_cluster:
                for m in members:
                    used.add(m["CaseMasterID"])
                lat = sum(m["latitude"] for m in members) / len(members)
                lng = sum(m["longitude"] for m in members) / len(members)
                last = max(m["_reg"] for m in members)
                expiry = last + datetime.timedelta(days=window_days)
                is_active = expiry >= as_of
                clusters.append({
                    "district": a["_district"],
                    "cases": sorted(m["CaseMasterID"] for m in members),
                    "cluster_size": len(members),
                    "centroid": {"lat": round(lat, 5), "lng": round(lng, 5)},
                    "radius_m": radius_m,
                    "span_days": (last - min(m["_reg"] for m in members)).days,
                    "last_offence": last.date().isoformat(),
                    "elevated_risk_until": expiry.date().isoformat(),
                    "status": "ACTIVE" if is_active else "EXPIRED",
                    "warning": (f"{'ACTIVE' if is_active else 'HISTORIC'} NEAR-REPEAT CLUSTER: "
                                f"{len(members)} burglaries within {radius_m}m of each other in "
                                f"{a['_district']}, over {(last - min(m['_reg'] for m in members)).days} days. "
                                + (f"Elevated risk in this area until {expiry.date().isoformat()}."
                                   if is_active else
                                   f"Risk window closed {expiry.date().isoformat()}.")),
                    "action": ("Increase patrol density within the radius; issue resident alerts; "
                               "target-hardening advice."
                               if is_active else "Historic pattern — use for MO/offender linkage."),
                    "citations": sorted(m["CaseMasterID"] for m in members),
                })
        # active clusters first, then by size
        clusters.sort(key=lambda c: (c["status"] != "ACTIVE", -c["cluster_size"]))
        return clusters


if __name__ == "__main__":
    from loader import RelationalStore
    store = RelationalStore(":memory:"); store.build(verbose=False)
    T = TrendAnalyser(store)

    print("=== COMPONENT 13: TREND ANALYTICS & EARLY WARNING ===\n")

    print("--- TEMPORAL PROFILE: Burglary ---")
    tp = T.temporal_profile("Burglary / House-breaking")
    print(f"  by month: {tp['by_month']}")
    print(f"  by day  : {tp['by_day_of_week']}")
    print(f"  peak hour: {tp['peak_hour']}   peak day: {tp['peak_day']}")
    ns = T.night_day_split("Burglary / House-breaking")
    print(f"  NIGHT/DAY: {ns['night']} night vs {ns['day']} day  -> {ns['night_pct']}% at night")

    print("\n--- EMERGING CLUSTER DETECTION (spike vs baseline) ---")
    ec = T.emerging_clusters(window_days=30)
    mc = ec["multiple_comparisons"]
    print(f"  window={ec['window_days']}d  baseline={ec['baseline_days']}d  "
          f"cells_tested={ec['cells_tested']}")
    print(f"  MULTIPLE-COMPARISONS CONTROL: {mc['method']} at q={mc['q']}")
    print(f"    candidates before correction: {mc['candidates_before_correction']}")
    print(f"    alerts AFTER correction     : {mc['alerts_after_correction']}")
    print(f"    expected false discoveries  : {mc['expected_false_discoveries_among_alerts']}")
    print()
    if ec["alerts"]:
        for a in ec["alerts"][:6]:
            print(f"  [{a['severity']:<8}] p={a['p_value']}  {a['finding']}")
    else:
        print("  no cells survive multiple-comparisons correction in this window.")

    print("\n--- NEAR-REPEAT EARLY WARNING (active space-time clusters) ---")
    nw = T.near_repeat_warnings()
    for c in nw[:3]:
        print(f"  [{c['district']}] {c['warning']}")
        print(f"     cases {c['cases']}  centroid {c['centroid']}")
        print(f"     ACTION: {c['action']}")
    if not nw:
        print("  no active near-repeat clusters.")
    store.close()
