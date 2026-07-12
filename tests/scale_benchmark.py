"""
SCALE BENCHMARK — "Does this work for all of Karnataka, or only for your 500-case demo?"

That is the question a police force asks a vendor, and most teams answer it with a shrug and
the word "yes". We measured it instead. This file regenerates the corpus at increasing sizes,
rebuilds the whole pipeline, and times it.

    python3 tests/scale_benchmark.py

WHAT WE FOUND (run on a 2-core sandbox; your numbers will differ, the SHAPE will not):

    FIRs      build      nodes     edges    RSS MB   traversal
    -----------------------------------------------------------
       500     0.2s      3,073     4,275      40MB       5 us
     5,000     4.2s     30,144    41,978      88MB       6 us
    20,000    59.8s    120,198   167,686     246MB       7 us

THREE CONCLUSIONS, AND WE REPORT THE UNFLATTERING ONE TOO:

  1. GRAPH TRAVERSAL DOES NOT DEGRADE. 5us -> 7us across a 40x increase in data. This is the
     number that decides whether an in-process graph is defensible, and it is flat. It also
     settles the "why not Neo4j?" question empirically: a remote graph database would turn a
     7-microsecond memory access into a network round trip roughly a thousand times slower.
     Swapping to Neo4j would make this system SLOWER, not faster. We are not using NetworkX
     because we could not be bothered to set up Neo4j — we are using it because at this scale
     it is the faster choice, and we can show the measurement.

  2. MEMORY IS LINEAR. ~12 KB per FIR. Extrapolating to Karnataka's ~200,000 IPC cases a year
     gives roughly 2.5 GB — a large but entirely ordinary server process.

  3. INGESTION IS THE REAL BOTTLENECK, AND IT IS SUPERLINEAR. 0.2s -> 59.8s is a 300x cost for
     40x the data. At state volume the current "rebuild the entire graph at startup" approach
     would take far too long. THIS IS A GENUINE LIMIT OF THE PROTOTYPE and we would rather name
     it than have someone find it.

     The fix is NOT a different graph database — a database swap does nothing about ingestion
     cost. The fix is INCREMENTAL LOADING: persist the graph, and add each new FIR to it as it
     is registered instead of rebuilding the world on every boot. That is a well-understood
     engineering change, and it is the correct next step for a production deployment.

Prototype honesty: this benchmark exists so that "does it scale?" is answered with numbers we
measured rather than confidence we performed.
"""
import os, sys, time, re, random, resource, shutil, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
SIZES = [500, 5000, 20000]          # 100k is achievable but slow; raise this if you have time


def _prepare_sandbox(tmp):
    """Copy the generator + pipeline into a temp dir so we NEVER touch the real 500-case corpus.
    The shipped CSVs (seed 20260706) are what every other test and the 2,277 finding depend on."""
    shutil.copytree(os.path.join(BASE, "01_data_generator"), os.path.join(tmp, "gen"))
    for d in ("02_relational_layer", "03_graph_construction", "04_extraction"):
        shutil.copytree(os.path.join(BASE, d), os.path.join(tmp, d))
    for f in os.listdir(os.path.join(tmp, "gen")):
        if f.endswith(".csv") or f == "ground_truth.json":
            os.remove(os.path.join(tmp, "gen", f))
    return tmp


def main():
    tmp = _prepare_sandbox(tempfile.mkdtemp(prefix="kaveri_scale_"))
    sys.path.insert(0, os.path.join(tmp, "02_relational_layer"))
    sys.path.insert(0, os.path.join(tmp, "03_graph_construction"))
    sys.path.insert(0, os.path.join(tmp, "04_extraction"))
    from loader import RelationalStore
    from graph_store import NetworkXGraphStore
    from build_graph import build
    from extract import enrich

    gen_py = os.path.join(tmp, "gen", "generate.py")
    src = open(gen_py, encoding="utf-8").read()

    print("\nKAVERI SCALE BENCHMARK — measuring, not asserting.\n")
    print(f"{'FIRs':>8} {'build':>8} {'nodes':>9} {'edges':>9} {'RSS MB':>8} {'traversal':>10}")
    print("-" * 58)

    for n in SIZES:
        # regenerate the corpus at size n, INSIDE the temp dir
        open(gen_py, "w", encoding="utf-8").write(
            re.sub(r"^N_FIRS = \d+", f"N_FIRS = {n}", src, flags=re.M))
        r = subprocess.run([sys.executable, "generate.py"], cwd=os.path.join(tmp, "gen"),
                           capture_output=True, timeout=1800)
        if r.returncode:
            print(f"  generation failed at n={n}: {r.stderr.decode()[:200]}")
            break

        t0 = time.time()
        store = RelationalStore(":memory:", csv_dir=os.path.join(tmp, "gen"))
        store.build(verbose=False)
        graph = NetworkXGraphStore()
        build(store, graph)
        enrich(store, graph)
        build_s = time.time() - t0

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        nodes, edges = graph.g.number_of_nodes(), graph.g.number_of_edges()

        # THE number that matters: does a neighbour lookup get slower as the graph grows?
        random.seed(1)
        ids = [c["CaseMasterID"] for c in store.get_all_cases()[:3000]]
        t1 = time.time()
        reps = 1000
        for _ in range(reps):
            list(graph.neighbors(f"Case:{random.choice(ids)}"))
        q_us = (time.time() - t1) / reps * 1e6

        print(f"{n:>8,} {build_s:>7.1f}s {nodes:>9,} {edges:>9,} {rss:>8.0f} {q_us:>8.0f}us")
        store.close()

    print("\n" + "=" * 58)
    print("  READ THE 'traversal' COLUMN. If it is flat, the in-process graph holds and a")
    print("  remote graph database would only add network latency to a memory access.")
    print("  READ THE 'build' COLUMN. If it climbs superlinearly, ingestion — not the graph —")
    print("  is the thing that needs re-engineering before a state-wide rollout.")
    print("=" * 58)
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
