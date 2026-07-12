"""
CROSS-VALIDATION — "You graded your own homework."

That is the sharpest criticism anyone can make of this project, and it deserves a real answer
rather than a defensive one. It actually contains TWO separate accusations, and they have very
different answers:

  (1a) "Your precision of 1.000 is OVERFITTING. You tuned the resolver until it scored perfectly
        on your one corpus. Show it a corpus it has never seen and it will fall apart."

        ^ THIS IS A FAIR AND TESTABLE ACCUSATION, AND THIS FILE ANSWERS IT.

  (1b) "Synthetic data is not real FIR data."

        ^ TRUE. UNFIXABLE. We do not have access to real Karnataka police records, and using
          them without authorisation would be a privacy violation. We state this plainly in the
          README rather than hiding behind the 1.000.

WHAT THIS FILE DOES
-------------------
Regenerates the ENTIRE WORLD from scratch under different random seeds. Every seed produces a
completely different corpus: different offenders, different names, different ages, different
phone numbers, different crime narratives, different seeded identity sets, and a different
ground truth.

The resolver's thresholds and rules were written against seed 20260706 and have NEVER been
tuned against any other seed. If precision collapses on unseen corpora, we were overfit and
the headline is worthless. If it holds, the mechanism is real and generalises.

We ran this to find out. We would rather find out here than on stage.

    python3 tests/cross_validation.py

WHAT WOULD FALSIFY OUR CLAIM
----------------------------
Any unseen seed producing a FALSE MERGE. One would be enough to prove the resolver was tuned
to a single lucky corpus. The report below prints every seed's result individually, including
any failures, rather than only the average.
"""
import os, sys, json, re, shutil, subprocess, tempfile, itertools, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)

# Seed 20260706 is the one the resolver was DEVELOPED against. Every other seed below is a
# corpus the resolver has never been tuned on, exposed to, or evaluated against.
DEV_SEED = 20260706
UNSEEN_SEEDS = [11111, 42424, 777777, 20261225, 98765, 31337, 5150]


def _sandbox():
    """Copy the pipeline into a temp dir so the real 500-case corpus is never touched."""
    tmp = tempfile.mkdtemp(prefix="kaveri_xval_")
    shutil.copytree(os.path.join(BASE, "01_data_generator"), os.path.join(tmp, "gen"))
    for d in ("02_relational_layer", "03_graph_construction", "04_extraction",
              "05_entity_resolution"):
        shutil.copytree(os.path.join(BASE, d), os.path.join(tmp, d))
    for f in os.listdir(os.path.join(tmp, "gen")):
        if f.endswith(".csv") or f == "ground_truth.json":
            os.remove(os.path.join(tmp, "gen", f))
    return tmp


def main():
    tmp = _sandbox()
    sys.path.insert(0, os.path.join(tmp, "02_relational_layer"))
    sys.path.insert(0, os.path.join(tmp, "03_graph_construction"))
    sys.path.insert(0, os.path.join(tmp, "04_extraction"))
    sys.path.insert(0, os.path.join(tmp, "05_entity_resolution"))
    from loader import RelationalStore
    from graph_store import NetworkXGraphStore
    from build_graph import build
    from extract import enrich
    import resolve as R

    gen_py = os.path.join(tmp, "gen", "generate.py")
    src = open(gen_py, encoding="utf-8").read()

    print("\n" + "=" * 78)
    print("  CROSS-VALIDATION — is precision 1.000 a real result, or overfitting?")
    print("=" * 78)
    print("\n  Each seed below regenerates the ENTIRE WORLD: different offenders, names, ages,")
    print("  phones, narratives, identity sets and ground truth. The resolver was developed")
    print(f"  against seed {DEV_SEED} ONLY, and has never been tuned on any other.\n")
    print(f"  {'SEED':>10} {'':>4} {'accused':>8} {'prec':>6} {'recall':>7} "
          f"{'FALSE MERGES':>13} {'MISSED':>7}")
    print("  " + "-" * 62)

    results = []
    for seed in [DEV_SEED] + UNSEEN_SEEDS:
        open(gen_py, "w", encoding="utf-8").write(
            re.sub(r"^SEED = \d+", f"SEED = {seed}", src, flags=re.M))
        r = subprocess.run([sys.executable, "generate.py"], cwd=os.path.join(tmp, "gen"),
                           capture_output=True, timeout=600)
        if r.returncode:
            print(f"  {seed:>10}  generation FAILED: {r.stderr.decode()[:80]}")
            continue

        store = RelationalStore(":memory:", csv_dir=os.path.join(tmp, "gen"))
        store.build(verbose=False)
        graph = NetworkXGraphStore()
        build(store, graph)
        enrich(store, graph)

        _, _, _, groups, _ = R.resolve(store, graph)
        gt = json.load(open(os.path.join(tmp, "gen", "ground_truth.json"), encoding="utf-8"))
        ev = R.score(groups, gt)
        n_acc = len(store.all_accused())

        tag = "(dev)" if seed == DEV_SEED else ""
        flag = "" if ev["fp"] == 0 and ev["fn"] == 0 else "   <-- FAILURE"
        print(f"  {seed:>10} {tag:>5} {n_acc:>8,} {ev['P']:>6.3f} {ev['R']:>7.3f} "
              f"{ev['fp']:>13} {ev['fn']:>7}{flag}")
        if seed != DEV_SEED:
            results.append(ev)
        store.close()

    print("  " + "-" * 62)

    if not results:
        print("\n  NO UNSEEN SEEDS COMPLETED — cannot make a claim.")
        shutil.rmtree(tmp, ignore_errors=True)
        return

    total_fp = sum(r["fp"] for r in results)
    total_fn = sum(r["fn"] for r in results)
    mean_p = statistics.mean(r["P"] for r in results)
    mean_r = statistics.mean(r["R"] for r in results)

    print(f"\n  ACROSS {len(results)} CORPORA THE RESOLVER HAS NEVER SEEN:")
    print(f"    mean precision      : {mean_p:.3f}")
    print(f"    mean recall         : {mean_r:.3f}")
    print(f"    TOTAL false merges  : {total_fp}")
    print(f"    TOTAL missed        : {total_fn}")

    print()
    if total_fp == 0:
        print("  VERDICT: NOT OVERFIT. The resolver makes zero false merges on corpora it was")
        print("  never tuned against. The 1.000 is a property of the DECISION RULE (evidence must")
        print("  corroborate a name before two people are merged), not an artefact of one lucky")
        print("  random seed. This is the strongest available answer to 'you graded your own")
        print("  homework' — and it is the only half of that criticism we can actually answer.")
    else:
        print(f"  VERDICT: OVERFIT. {total_fp} false merge(s) appeared on unseen corpora.")
        print("  The 1.000 does NOT generalise. DO NOT put it on a slide until this is fixed.")

    print("\n  WHAT THIS STILL DOES NOT PROVE: the data is synthetic. No real Karnataka FIR data")
    print("  exists for us to validate against, and using it without authorisation would be a")
    print("  privacy violation. Generalising across unseen SYNTHETIC corpora is strong evidence")
    print("  that the mechanism is sound. It is not evidence of real-world accuracy, and we do")
    print("  not claim that it is.\n")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
