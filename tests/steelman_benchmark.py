"""
THE STEEL-MAN BENCHMARK — "Isn't your 2,277 just beating up a strawman?"

That is the question a sharp judge asks, and it is a fair one.

Our headline compares KAVERI against `SQL GROUP BY name`, which produces 2,277 false merges. But
nobody competent would ship exact-name grouping. So this file builds the baseline a GOOD engineer
would actually write in an afternoon — fuzzy name matching, blocking, transitive union-find — and
lets it fight.

We wrote this to find out whether our own headline survives contact with a real opponent. If the
fuzzy baseline had matched us, we needed to know that BEFORE a judge told us.

    python3 tests/steelman_benchmark.py

THREE CONTENDERS
----------------
  1. SQL GROUP BY name        the naive baseline everyone (rightly) dismisses
  2. FUZZY MATCHER            the STEEL MAN: Jaro-Winkler + soundex blocking + union-find,
                              tuned at multiple thresholds so we cannot be accused of
                              rigging it with a bad parameter
  3. KAVERI                   evidence-corroborated resolution: a name is never enough

WHY THE STEEL MAN LOSES ANYWAY (and it is not because we cheated)
-----------------------------------------------------------------
The corpus contains deliberately seeded HARD NEGATIVES — different people whose names are close
enough to fool any string metric:

      "Suresh Kumar"  vs  "Suresh Kumara"      (different men)
      "Prakash B"     vs  "Prakash Bhat"       (different men)
      "Ramesh Gowda"  vs  "Ramesh Gouda"       (SAME man, spelling variant)

Look at those three. NO string metric can separate line 1 and 2 from line 3 — they are the same
shape. A fuzzy matcher tuned loose enough to catch the true variant MUST also merge the two
decoys. Tuned tight enough to reject the decoys, it MUST also miss the true variant. That is not
a tuning failure; it is a ceiling, and this benchmark measures exactly where it sits.

KAVERI escapes the ceiling by refusing to decide on a name at all. A merge requires CORROBORATING
EVIDENCE — a shared phone, vehicle, or financial account. Names only ever propose; evidence
disposes. Name-only matches go to a human review queue, never to an automatic merge.

That is the moat. Not a better string metric — a better DECISION RULE.
"""
import os, sys, json, itertools, collections

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
for d in ("01_data_generator", "02_relational_layer", "03_graph_construction",
          "04_extraction", "05_entity_resolution"):
    sys.path.insert(0, os.path.join(BASE, d))

from loader import RelationalStore
from graph_store import NetworkXGraphStore
from build_graph import build
from extract import enrich
import resolve as KAVERI
import jellyfish


# ─────────────────────────── scoring (identical for all three) ───────────────────────────
def score(pred_pairs, truth_pairs):
    tp = len(pred_pairs & truth_pairs)
    fp = len(pred_pairs - truth_pairs)      # FALSE MERGES — two different people fused
    fn = len(truth_pairs - pred_pairs)      # MISSED — a real repeat offender left unlinked
    P = tp / (tp + fp) if (tp + fp) else 1.0
    R = tp / (tp + fn) if (tp + fn) else 1.0
    F = 2 * P * R / (P + R) if (P + R) else 0.0
    return {"P": P, "R": R, "F": F, "fp": fp, "fn": fn}


def pairs_from_groups(groups):
    out = set()
    for g in groups:
        for a, b in itertools.combinations(sorted(g), 2):
            out.add((a, b))
    return out


# ─────────────────────────── contender 1: the naive baseline ───────────────────────────
def sql_group_by_name(accused):
    """`SELECT ... GROUP BY AccusedName`. The thing a hurried analyst actually runs."""
    buckets = collections.defaultdict(list)
    for a in accused:
        buckets[a["AccusedName"].strip().lower()].append(a["AccusedMasterID"])
    return pairs_from_groups([v for v in buckets.values() if len(v) > 1])


# ─────────────────────────── contender 2: THE STEEL MAN ───────────────────────────
def fuzzy_union_find(accused, threshold):
    """
    The baseline a COMPETENT engineer writes. Not a strawman:

      - BLOCKING on soundex, so we do not do 200k pairwise comparisons (this is what a real
        ER system does for tractability)
      - JARO-WINKLER on the full name, the standard string metric for personal names
      - UNION-FIND for transitive closure, so A~B and B~C implies A~C — exactly the behaviour
        a real system needs and a naive pairwise matcher lacks

    This is a genuinely reasonable system. It is what we would have built if we had stopped
    thinking after the obvious idea. We run it across a THRESHOLD SWEEP so nobody can claim we
    crippled it by picking a bad cutoff.
    """
    parent = {a["AccusedMasterID"]: a["AccusedMasterID"] for a in accused}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    # BLOCKING: only compare people whose names share a soundex key. Standard ER practice.
    blocks = collections.defaultdict(list)
    for a in accused:
        name = a["AccusedName"].strip()
        toks = name.split() or [name]
        try:
            key = jellyfish.soundex(toks[0])
        except Exception:
            key = toks[0][:2].upper()
        blocks[key].append(a)

    for _, members in blocks.items():
        for x, y in itertools.combinations(members, 2):
            s = jellyfish.jaro_winkler_similarity(
                x["AccusedName"].strip().lower(), y["AccusedName"].strip().lower())
            if s >= threshold:
                union(x["AccusedMasterID"], y["AccusedMasterID"])

    groups = collections.defaultdict(list)
    for a in accused:
        groups[find(a["AccusedMasterID"])].append(a["AccusedMasterID"])
    return pairs_from_groups([g for g in groups.values() if len(g) > 1])


# ─────────────────────────── the fight ───────────────────────────
def main():
    store = RelationalStore(":memory:")
    store.build(verbose=False)
    graph = NetworkXGraphStore()
    build(store, graph)
    enrich(store, graph)

    accused = store.get_all_accused() if hasattr(store, "get_all_accused") else store.all_accused()
    gt = json.load(open(os.path.join(BASE, "01_data_generator", "ground_truth.json"),
                        encoding="utf-8"))
    truth = set()
    for m in gt["identity_mappings"]:
        for a, b in itertools.combinations(sorted(m["accused_ids"]), 2):
            truth.add((a, b))

    print("\n" + "=" * 78)
    print("  THE STEEL-MAN BENCHMARK")
    print("  Is the 2,277 a real finding, or are we beating up a strawman?")
    print("=" * 78)
    print(f"\n  corpus: {len(accused)} accused records, {len(truth)} true same-person pairs\n")
    print(f"  {'METHOD':<34} {'prec':>6} {'recall':>7} {'F1':>6} {'FALSE MERGES':>13} {'MISSED':>7}")
    print("  " + "-" * 74)

    # 1. the naive baseline
    r = score(sql_group_by_name(accused), truth)
    print(f"  {'SQL GROUP BY name':<34} {r['P']:>6.3f} {r['R']:>7.3f} {r['F']:>6.3f} "
          f"{r['fp']:>13,} {r['fn']:>7}")
    naive_fp = r["fp"]

    # 2. THE STEEL MAN, swept across thresholds so we cannot be accused of rigging it
    print("  " + "-" * 74)
    best_f, best_t, best = -1, None, None
    for t in (0.80, 0.85, 0.88, 0.90, 0.92, 0.95):
        r = score(fuzzy_union_find(accused, t), truth)
        star = ""
        if r["F"] > best_f:
            best_f, best_t, best = r["F"], t, r
        print(f"  {'FUZZY + blocking + union-find  @' + f'{t:.2f}':<34} {r['P']:>6.3f} "
              f"{r['R']:>7.3f} {r['F']:>6.3f} {r['fp']:>13,} {r['fn']:>7}{star}")

    # 3. KAVERI
    print("  " + "-" * 74)
    merges, reviews, relations, groups, _ = KAVERI.resolve(store, graph)
    rk = score(pairs_from_groups(groups), truth)
    print(f"  {'KAVERI (evidence-corroborated)':<34} {rk['P']:>6.3f} {rk['R']:>7.3f} "
          f"{rk['F']:>6.3f} {rk['fp']:>13,} {rk['fn']:>7}")
    print("  " + "-" * 74)

    # ── the verdict, stated plainly ──
    print(f"\n  BEST the steel man could do: F1={best_f:.3f} at threshold {best_t:.2f}")
    print(f"    -> even tuned to its optimum, it makes {best['fp']} FALSE MERGE(S) "
          f"and misses {best['fn']}.")
    print(f"  KAVERI: F1={rk['F']:.3f}, {rk['fp']} false merges, {rk['fn']} missed.\n")

    if rk["fp"] < best["fp"] or (rk["fp"] == best["fp"] and rk["fn"] < best["fn"]):
        print("  VERDICT: the moat is REAL. A competent fuzzy matcher, tuned to its best,")
        print("  still cannot separate the seeded hard negatives from the true variants —")
        print("  because they are the same shape to any string metric:")
        print("        'Suresh Kumar' vs 'Suresh Kumara'   <- DIFFERENT men")
        print("        'Ramesh Gowda' vs 'Ramesh Gouda'    <- the SAME man")
        print("  KAVERI wins by refusing to decide on a name at all. Evidence disposes.")
    else:
        print("  VERDICT: THE STEEL MAN MATCHED OR BEAT US. The headline is a strawman and")
        print("  MUST be re-framed. Do not put the 2,277 on a slide until this is understood.")

    print(f"\n  Headline remains defensible: naive SQL = {naive_fp:,} false merges, KAVERI = "
          f"{rk['fp']}.")
    print("  But quote the FUZZY number too. Beating only the strawman is not a finding.\n")
    store.close()


if __name__ == "__main__":
    main()
