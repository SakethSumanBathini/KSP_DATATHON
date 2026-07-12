"""
Component 19 — Modus Operandi Signature Extraction & Clustering
  [req 3.1: "trends across ... MODUS OPERANDI"]
  [req 5.2: "Behavioural analysis of offenders based on crime history AND MODUS OPERANDI"]

Two named requirements, one build. We had crime TYPE. We had no notion of HOW the crime was done.
"Burglary" is a category. "Entered through a rear window between 02:00 and 04:00 while the house
was vacant, took gold, no vehicle used" is a SIGNATURE — and signatures link offenders across
cases that share nothing else.

METHOD (transparent, auditable — an officer must be able to check every tag):
  MO is extracted from BriefFacts free text with an explicit, inspectable lexicon:
      entry_method   : rear window / door lock broken / grille cut / duplicate key ...
      timing         : night / early hours / daytime  (from IncidentFromDate, not guessed)
      target         : house / shop / vehicle / person
      property       : gold / cash / electronics / vehicle
      tools          : crowbar / cutter / knife / firearm
      approach       : vehicle used / accomplice / impersonation / online lure

  Each case becomes an MO FINGERPRINT (a set of tags). Two offenders with a high Jaccard overlap
  are behaviourally similar EVEN IF they share no phone, no vehicle and no name.
  That is a THIRD linkage channel, independent of identity and of physical evidence.

HONEST LIMIT: this is a lexicon, not a language model. It will miss MO described in words we did
not anticipate. It is a floor, not a ceiling — and it is auditable, which an LLM tagger is not.
"""
import sys, os, re
from collections import Counter, defaultdict
from itertools import combinations
for p in ["02_relational_layer"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), p))

# ── the MO lexicon. Every tag is a regex an officer can read and challenge. ──
MO_LEXICON = {
    "entry:rear_window":   r"rear window|back window|window.{0,15}(broke|forced|prised|pried)",
    "entry:door_forced":   r"door.{0,20}(broke|forced|prised|pried)|lock.{0,12}(broke|cut|forced)",
    "entry:grille_cut":    r"grill?e?.{0,10}cut|iron bars? cut",
    "entry:duplicate_key": r"duplicate key|spare key",
    "entry:unlocked":      r"door was (open|unlocked)|left unlocked",
    "target:house":        r"\bhouse|residence|dwelling|home\b",
    "target:shop":         r"\bshop|store|showroom|commercial premises\b",
    "target:vehicle":      r"\bvehicle|motorcycle|two-wheeler|car\b",
    "target:person":       r"\bpedestrian|passer-?by|the victim was walking\b",
    "property:gold":       r"\bgold|jewell?ery|ornaments?|chain\b",
    "property:cash":       r"\bcash|currency|money|rupees\b",
    "property:electronics":r"\bmobile phone|laptop|television|electronics\b",
    "tool:crowbar":        r"crowbar|iron rod|lever",
    "tool:cutter":         r"cutter|hacksaw|bolt cutter",
    "tool:weapon":         r"\bknife|weapon|firearm|pistol|machete\b",
    "approach:vehicle":    r"\b(on|using|in) a (motorcycle|two-wheeler|car|vehicle)|fled on",
    "approach:accomplice": r"accomplice|two persons|three persons|gang|along with another",
    "approach:impersonate":r"posing as|impersonat|pretending to be|false pretext",
    "approach:online":     r"\bonline|UPI|transfer|induced.{0,20}transfer|call(ed)? .{0,15}mobile\b",
}
COMPILED = {k: re.compile(v, re.IGNORECASE) for k, v in MO_LEXICON.items()}


def timing_tag(dt):
    if dt is None:
        return None
    h = dt.hour
    if 0 <= h < 5:   return "time:early_hours"
    if 5 <= h < 12:  return "time:morning"
    if 12 <= h < 18: return "time:afternoon"
    if 18 <= h < 22: return "time:evening"
    return "time:night"


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class MOAnalyser:
    def __init__(self, store):
        import datetime
        self.store = store
        self.fingerprint = {}          # case_id -> set of MO tags
        self.cases = store.get_all_cases()
        for c in self.cases:
            text = c["BriefFacts"] or ""
            tags = {k for k, rx in COMPILED.items() if rx.search(text)}
            try:
                t = datetime.datetime.fromisoformat(str(c["IncidentFromDate"]))
            except Exception:
                t = None
            tt = timing_tag(t)
            if tt:
                tags.add(tt)
            self.fingerprint[c["CaseMasterID"]] = tags

    def signature(self, case_id):
        return sorted(self.fingerprint.get(case_id, set()))

    def similar_by_mo(self, case_id, min_similarity=0.5, limit=10):
        """
        Cases with a matching BEHAVIOURAL signature — a linkage channel INDEPENDENT of
        identity and of physical evidence. Two cases can link here while sharing no phone,
        no vehicle and no name.
        """
        me = self.fingerprint.get(case_id, set())
        if not me:
            return []
        out = []
        for cid, fp in self.fingerprint.items():
            if cid == case_id:
                continue
            s = jaccard(me, fp)
            if s >= min_similarity:
                out.append({"case_id": cid, "similarity": round(s, 3),
                            "shared_signature": sorted(me & fp),
                            "differs_by": sorted(me ^ fp)})
        out.sort(key=lambda x: -x["similarity"])
        return out[:limit]

    def offender_mo_profile(self, case_ids):
        """The behavioural profile of ONE offender across all their linked cases (req 5.2)."""
        tally = Counter()
        for cid in case_ids:
            for t in self.fingerprint.get(cid, ()):
                tally[t] += 1
        n = len(case_ids) or 1
        consistent = {t: round(100.0 * c / n, 1) for t, c in tally.items() if c / n >= 0.6}
        return {
            "cases_analysed": sorted(case_ids),
            "signature_tags": dict(tally.most_common()),
            "consistent_behaviour": consistent,
            "interpretation": (
                f"Consistent across {int(min(consistent.values()) if consistent else 0)}%+ of their "
                f"cases: {sorted(consistent)}. A stable signature is itself an investigative asset — "
                f"it predicts HOW the next offence will be committed, not WHO will commit one."
                if consistent else "No stable signature — offending pattern is opportunistic/varied."),
        }

    def mo_trends(self, min_support=8):
        """req 3.1 — crime trends across MODUS OPERANDI, not just crime type."""
        by_crime = defaultdict(Counter)
        for c in self.cases:
            crime = self.store.get_crime_subhead_name(c["CrimeMinorHeadID"]) or "Unknown"
            for t in self.fingerprint.get(c["CaseMasterID"], ()):
                by_crime[crime][t] += 1
        out = []
        for crime, tally in by_crime.items():
            total = sum(1 for c in self.cases
                        if (self.store.get_crime_subhead_name(c["CrimeMinorHeadID"]) or "Unknown") == crime)
            dominant = [(t, n, round(100.0 * n / total, 1))
                        for t, n in tally.most_common(5) if n >= min_support]
            if dominant:
                out.append({"crime_type": crime, "cases": total,
                            "dominant_mo": [{"tag": t, "cases": n, "pct": p} for t, n, p in dominant]})
        out.sort(key=lambda x: -x["cases"])
        return out

    # Tags that ACTUALLY discriminate an offender's behaviour. Time-of-day and target-type are
    # context, not signature — thousands of unrelated cases happen in the afternoon.
    DISCRIMINATIVE_PREFIXES = ("entry:", "tool:", "approach:")

    def mo_clusters(self, min_similarity=0.7, min_size=3, min_discriminative=2):
        """
        Groups of cases sharing a BEHAVIOURAL signature — possible same offender or crew.

        BUG THIS FIXES (found in testing, and it was a bad one): the first version clustered on
        raw Jaccard overlap. Sparse fingerprints overlap trivially, so it produced a "cluster" of
        77 cases whose entire shared signature was ['time:afternoon']. That is not intelligence —
        it is a clock reading, and acting on it would send officers to chase 77 unrelated cases.

        A signature must DISCRIMINATE. We now require the shared signature to contain at least
        `min_discriminative` tags describing HOW the offence was committed (entry method, tools,
        approach) — not merely WHEN it happened or WHAT was targeted.
        """
        ids = [c["CaseMasterID"] for c in self.cases
               if len(self.fingerprint.get(c["CaseMasterID"], ())) >= 3]
        seen, clusters = set(), []
        for a in ids:
            if a in seen:
                continue
            members = [a]
            for b in ids:
                if b == a or b in seen:
                    continue
                if jaccard(self.fingerprint[a], self.fingerprint[b]) >= min_similarity:
                    members.append(b)
            if len(members) < min_size:
                continue
            sig = set(self.fingerprint[members[0]])
            for m in members[1:]:
                sig &= self.fingerprint[m]
            disc = [t for t in sig if t.startswith(self.DISCRIMINATIVE_PREFIXES)]
            if len(disc) < min_discriminative:
                continue                      # time/target-only overlap is NOT a signature
            for m in members:
                seen.add(m)
            clusters.append({
                "cases": sorted(members), "size": len(members),
                "shared_signature": sorted(sig),
                "discriminative_tags": sorted(disc),
                "note": ("These cases share a DISCRIMINATIVE behavioural signature (how the offence "
                         "was committed, not merely when). They may involve the same offender or "
                         "crew EVEN IF no name, phone or vehicle links them. This is a third "
                         "linkage channel, independent of identity and physical evidence."),
                "caveat": ("MO similarity is SUGGESTIVE, never probative. It generates a lead for "
                           "a human investigator; it does not establish that the same person acted."),
                "citations": sorted(members),
            })
        clusters.sort(key=lambda c: -c["size"])
        return clusters


if __name__ == "__main__":
    from loader import RelationalStore
    store = RelationalStore(":memory:"); store.build(verbose=False)
    M = MOAnalyser(store)

    print("=== COMPONENT 19: MODUS OPERANDI SIGNATURES ===\n")
    print("--- MO fingerprint of FIR 1 (extracted from free text, invisible to SQL) ---")
    print(f"  {M.signature(1)}")

    print("\n--- req 3.1: CRIME TRENDS ACROSS MODUS OPERANDI (not just crime type) ---")
    for t in M.mo_trends()[:3]:
        print(f"  {t['crime_type']} ({t['cases']} cases):")
        for d in t["dominant_mo"][:4]:
            print(f"     {d['pct']:>5}%  {d['tag']}")

    print("\n--- req 5.2: BEHAVIOURAL PROFILE of a repeat offender ---")
    prof = M.offender_mo_profile([1, 4, 7, 10, 13])      # Ramesh Gowda's cases
    print(f"  cases: {prof['cases_analysed']}")
    print(f"  consistent behaviour: {prof['consistent_behaviour']}")
    print(f"  -> {prof['interpretation'][:150]}")

    print("\n--- BEHAVIOURAL CLUSTERS (linkage with NO shared name/phone/vehicle) ---")
    for c in M.mo_clusters()[:2]:
        print(f"  {c['size']} cases {c['cases'][:8]}")
        print(f"     shared signature: {c['shared_signature']}")
    store.close()
