"""
Component 6 — Hybrid retrieval over the Crime Intelligence Graph.
Three retrieval modes, combined:
  1. GRAPH traversal  — multi-hop relationship queries (shared phone/vehicle, co-accused, networks)
  2. SEMANTIC search  — similarity over BriefFacts (finds similar MO — impossible in SQL)
  3. STRUCTURED filter — by district, crime type, section, date

SEMANTIC BACKEND:
  PRODUCTION: sentence-transformer / IndicBERT embeddings in Qdrant (vector DB, containerized).
  HERE (verifiable stand-in): TF-IDF cosine similarity — same interface (embed + top-k),
  swappable to Qdrant with no change to callers. Clearly marked.

Every result carries provenance (source case IDs) so Component 7 can cite.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"02_relational_layer"))
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"03_graph_construction"))
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"04_extraction"))
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"05_entity_resolution"))
from loader import RelationalStore
from graph_store import NetworkXGraphStore
from build_graph import build, person_id, fir_id
from extract import enrich
from resolve import resolve
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class SemanticIndex:
    """
    Semantic search over BriefFacts. Two backends behind ONE interface: build() / query().
      PRODUCTION (use_embeddings=True): real sentence-transformer embeddings (multilingual model
        recommended for Kannada: "paraphrase-multilingual-MiniLM-L12-v2"). In production these
        vectors live in Qdrant (containerized on Catalyst); here they're held in-process — the
        SAME embeddings, just a different store. Swapping to Qdrant is a store change, not a
        model change.
      FALLBACK (use_embeddings=False or model unavailable): TF-IDF cosine. Keeps the pipeline
        runnable in any environment (e.g. no-internet sandbox). Lower semantic quality; clearly
        the fallback, not the production path.
    """
    def __init__(self, use_embeddings=True, model_name="paraphrase-multilingual-MiniLM-L12-v2"):
        self.ids = []; self.mode = None
        self.model = None; self.embeddings = None
        self.vec = None; self.matrix = None
        if use_embeddings:
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(model_name)
                self.mode = "embeddings"
            except Exception as e:
                # model/network unavailable -> graceful fallback, pipeline never breaks
                print(f"[SemanticIndex] embeddings unavailable ({type(e).__name__}); "
                      f"falling back to TF-IDF. In production (open internet) this uses real embeddings.")
                self.mode = "tfidf"
        else:
            self.mode = "tfidf"
        if self.mode == "tfidf":
            self.vec = TfidfVectorizer(stop_words="english", ngram_range=(1,2), min_df=1)

    def build(self, id_text_pairs):
        self.ids = [i for i,_ in id_text_pairs]
        texts = [t for _,t in id_text_pairs]
        if self.mode == "embeddings":
            self.embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        else:
            self.matrix = self.vec.fit_transform(texts)

    def query(self, text, k=5):
        if self.mode == "embeddings":
            q = self.model.encode([text], convert_to_numpy=True, show_progress_bar=False)
            sims = cosine_similarity(q, self.embeddings)[0]
        else:
            q = self.vec.transform([text])
            sims = cosine_similarity(q, self.matrix)[0]
        order = np.argsort(-sims)[:k]
        return [(self.ids[i], float(sims[i])) for i in order if sims[i] > 0]

class Retriever:
    def __init__(self, store, graph, resolved_groups):
        self.store = store; self.graph = graph
        # map each accused_master_id -> its resolved identity cluster id
        self.identity_of = {}
        for gi, group in enumerate(resolved_groups):
            for amid in group: self.identity_of[amid] = f"Identity:{gi}"
        # semantic index over BriefFacts
        self.sem = SemanticIndex(use_embeddings=True)  # tries real embeddings, falls back to TF-IDF if unavailable
        self.sem.build([(c["CaseMasterID"], c["BriefFacts"] or "") for c in store.get_all_cases()])

    # ---- MODE 2: semantic MO similarity ----
    def similar_cases(self, query_text, k=5):
        hits = self.sem.query(query_text, k=k)
        out = []
        for cid, score in hits:
            c = self.store.get_case(cid)
            out.append({"case_id": cid, "score": round(score,3),
                        "crime_no": c["CrimeNo"], "brief": c["BriefFacts"][:120]})
        return out

    # ---- MODE 1: graph — entities/persons connected to a case ----
    def network_around_case(self, case_id):
        result = {"case_id": case_id, "shared_phones": [], "shared_vehicles": [],
                  "linked_cases": set(), "accused": []}
        fnode = fir_id(case_id)
        # entities on this FIR
        for nb, d in self.graph.neighbors(fnode):
            if nb.startswith("Phone:") or nb.startswith("Vehicle:"):
                # which OTHER cases share this entity?
                for cnb, cd in self.graph.neighbors(nb):
                    if cnb.startswith("FIR:") and cnb != fnode:
                        other = int(cnb.split(":")[1])
                        result["linked_cases"].add(other)
                        if nb.startswith("Phone:"): result["shared_phones"].append((nb.split(":",1)[1], other))
                        else: result["shared_vehicles"].append((nb.split(":",1)[1], other))
        result["linked_cases"] = sorted(result["linked_cases"])
        for a in self.store.get_accused_for_case(case_id):
            amid = a["AccusedMasterID"]
            result["accused"].append({"name": a["AccusedName"], "accused_id": amid,
                                      "identity": self.identity_of.get(amid, f"Person:{amid}")})
        return result

    # ---- MODE 1b: all cases for a resolved identity (cross-case history) ----
    def cases_for_identity(self, accused_master_id):
        ident = self.identity_of.get(accused_master_id)
        if not ident: return [accused_master_id and self.store.get_accused_for_case]  # single
        members = [amid for amid, i in self.identity_of.items() if i == ident]
        cases = []
        for amid in members:
            a = [x for x in self.store.all_accused() if x["AccusedMasterID"]==amid][0]
            cases.append({"accused_id": amid, "name": a["AccusedName"], "case_id": a["CaseMasterID"]})
        return {"identity": ident, "member_count": len(members), "cases": cases}

    # ---- MODE 3: structured filter ----
    def filter_cases(self, district_name=None, crime_subhead=None, limit=20):
        out = []
        for c in self.store.get_all_cases():
            if crime_subhead and c["CrimeMinorHeadID"] != crime_subhead: continue
            if district_name:
                d = self.store.get_district_for_case(c["CaseMasterID"])
                if not d or d["DistrictName"] != district_name: continue
            out.append(c["CaseMasterID"])
            if len(out) >= limit: break
        return out


if __name__ == "__main__":
    store = RelationalStore(":memory:"); store.build(verbose=False)
    graph = NetworkXGraphStore(); build(store, graph); enrich(store, graph)
    _,_,_,groups,_ = resolve(store, graph)
    R = Retriever(store, graph, groups)
    gt = json.load(open("../01_data_generator/ground_truth.json", encoding="utf-8"))

    print("=== COMPONENT 6: HYBRID RETRIEVAL ===\n")

    print("--- MODE 2: Semantic MO similarity (query: night ground-floor glass-break burglary) ---")
    for r in R.similar_cases("night ground floor residence rear window glass broken gold stolen", k=5):
        print(f"  case {r['case_id']} (sim {r['score']}): {r['brief']}")

    print("\n--- MODE 1: Network around a Set A cluster case (shared phone -> linked cases) ---")
    setA = gt["seeded_connections"]["set_A_mysuru_cluster"]
    net = R.network_around_case(setA["fir_ids"][0])
    print(f"  case {net['case_id']}: linked to {len(net['linked_cases'])} other cases via shared entities")
    print(f"  linked cases: {net['linked_cases'][:10]}")
    print(f"  accused (with resolved identity): {net['accused']}")

    print("\n--- MODE 1b: Cross-case history for the Kannada-variant identity ---")
    C = gt["seeded_connections"]["set_C_kannada_variant_identity"]
    hist = R.cases_for_identity(C["accused_ids"][0])
    print(f"  {hist}")

    print("\n--- MODE 3: Structured filter (burglaries in Mysuru) ---")
    f = R.filter_cases(district_name="Mysuru", crime_subhead=1, limit=10)
    print(f"  {len(f)} burglary cases in Mysuru: {f}")
    store.close()
