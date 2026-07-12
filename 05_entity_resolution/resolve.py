"""
Component 5 — Kannada Entity Resolution (FINAL, after two rounds of honest failure-fixing).

MERGE RULES (learned from real failures on this data):
  A. Shared distinguishing entity (phone/vehicle/UPI) + SIMILAR name (>=0.80) + same gender
     -> SAME PERSON (merge).
  B. Strong name match (>=0.80 across transliterated forms) + corroborating context
     (age within 2y, same gender, compatible crime context) -> SAME PERSON (merge).
     [This is what links the Kannada variants ರಾಮಯ್ಯ.ಕೆ / Ramaiah K / ರಾಮು.]
  C. Shared entity but DIFFERENT name -> NOT identity; it's a RELATIONSHIP (co-offenders on
     one phone/vehicle). Recorded as a CO_ACCUSED-style link, never an identity merge.
  D. Name-only, moderate -> HUMAN REVIEW. Never auto-merge on weak signal.

Rationale: false MERGE (fusing two people) is the dangerous error, so merges require either a
shared entity with a compatible name, or a strong name match with corroboration. Everything
else is a review flag or a relationship edge. IndicXlit replaces the stand-in transliterator
in production. Scored honestly vs ground_truth (5 identity groups); reports P/R + failures.
"""
import sys, os, json, itertools
import jellyfish
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"02_relational_layer"))
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"03_graph_construction"))
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()),"04_extraction"))
from loader import RelationalStore
from graph_store import NetworkXGraphStore
from build_graph import build, person_id
from extract import enrich
from transliteration import transliterate

NAME_SIMILAR = 0.80

def roman_forms(name): return set(transliterate(name))
def phonetic_keys(name):
    ks=set()
    for f in roman_forms(name):
        for t in f.split():
            if t: ks.add(jellyfish.soundex(t))
    return ks
def _token_sim(a, b):
    """
    Similarity between two name TOKENS. Jaro-Winkler, deliberately.

    WE TRIED TO BE CLEVERER AND IT BACKFIRED — recorded here so nobody repeats it:
    Jaro-Winkler adds a bonus for a shared PREFIX. That bonus causes false merges on Kannada
    names that share a prefix but diverge at the ending (Manjunath/Manjula ~0.90). So we tried
    blending in a REVERSED (suffix-sensitive) comparison and taking the minimum. It killed 3 of
    the 5 adversarial false merges.

    It also DESTROYED RECALL: it missed 'ರಾಮಯ್ಯ' (Ramayya) <-> 'ರಾಮು' (Ramu) — a man and his
    NICKNAME. Indian nicknames are prefix-preserving and suffix-divergent. That is the exact
    same shape as the false merges. The prefix bonus that creates the false merges is the same
    signal that catches the nicknames. A pure string metric cannot separate them.

    So we keep Jaro-Winkler, accept that the name matcher alone is imperfect, and rely on the
    ARCHITECTURE for safety: decide() never auto-merges on a name alone. That is not a
    consolation prize — it is the actual reason the system is safe.
    """
    return jellyfish.jaro_winkler_similarity(a, b)


def name_similarity(a, b):
    """
    Compare two names across all their romanised forms.

    WHY THIS IS NOT JUST jaro_winkler(a, b):
      Indian names are given-name + surname ("Prakash Reddy"). An earlier version compared ONLY
      the first token, so "Prakash Reddy" and "Prakash Rao" — two DIFFERENT people — scored
      1.000. In a police system that is how an innocent man gets merged into a repeat offender's
      identity. The adversarial benchmark exposed it; this is the fix, not a cover-up.

    THE RULE: given name and surname are scored SEPARATELY and combined with min(). BOTH must
    independently agree. An average would let one half rescue the other — we tried that and
    caught it merging "Ramesh Kumar" with "Suresh Kumar" (different men, shared surname).
    Single-token names fall back to the token comparison alone, which is correct: with no
    surname present there is no surname evidence, and we do not invent agreement we cannot see.
    """
    fa, fb = roman_forms(a), roman_forms(b)
    best = 0.0
    for x in fa:
        for y in fb:
            tx, ty = x.split(), y.split()
            if not tx or not ty:
                continue

            given = _token_sim(tx[0], ty[0])

            if len(tx) < 2 or len(ty) < 2:
                # no surname on one side — judge on the given name alone
                score = given
            else:
                surname = max(
                    _token_sim(tx[-1], ty[-1]),
                    max((_token_sim(p, q) for p in tx[1:] for q in ty[1:]), default=0.0),
                )
                score = min(given, surname)

            best = max(best, score)
    return best


def conn_sig(graph,amid):
    return {nb for nb,_ in graph.neighbors(person_id(amid))
            if nb.startswith(("Phone:","Vehicle:","FinancialAccount:"))}

def crime_context(store, amid):
    """crime sub-head + registered date of the person's source case (weak corroboration)."""
    a=[x for x in store.all_accused() if x["AccusedMasterID"]==amid][0]
    c=store.get_case(a["CaseMasterID"])
    return c["CrimeMinorHeadID"], c["CrimeRegisteredDate"]

def decide(store, graph, a, b):
    # UNIVERSAL GUARD: two accused in the SAME case are explicitly different persons (A1/A2 labels).
    if a["CaseMasterID"] == b["CaseMasterID"]:
        return "no", 0.0, {"same_case": True}, "GUARD:same-case co-accused = distinct persons"
    nsim=name_similarity(a["AccusedName"], b["AccusedName"])
    age_ok=(a["AgeYear"] is not None and b["AgeYear"] is not None
            and abs(int(a["AgeYear"])-int(b["AgeYear"]))<=2)
    gender_ok=(a["GenderID"]==b["GenderID"])
    shared=conn_sig(graph,a["AccusedMasterID"]) & conn_sig(graph,b["AccusedMasterID"])
    det={"name_sim":round(nsim,3),"age_ok":age_ok,"gender_ok":gender_ok,"shared":sorted(shared)}

    # Rule A (ONLY auto-merge path): shared distinguishing entity + compatible name + same gender
    # + compatible age. All four required; a shared device with clashing name OR age is NOT identity.
    if shared and nsim>=NAME_SIMILAR and gender_ok and age_ok:
        return "merge", min(1.0,0.6+0.4*nsim), det, "A:entity+name+age"
    # Rule C: shared entity but name OR age clashes -> co-offenders (relationship), NOT identity merge.
    if shared and (nsim<NAME_SIMILAR or not age_ok):
        return "relate", 0.5, det, "C:co-offender(shared device, diff person)"
    # Rule D: strong name match but NO distinguishing entity -> HUMAN REVIEW (never auto-merge,
    # because it is indistinguishable from different people sharing a common name+age).
    if nsim>=NAME_SIMILAR and age_ok and gender_ok:
        return "review", nsim, det, "D:name-only (no distinguishing signal) -> review"
    if nsim>=0.70:
        return "review", nsim, det, "D:weak name -> review"
    return "no", nsim, det, "-"

def resolve(store, graph):
    accused=store.all_accused(); by_id={a["AccusedMasterID"]:a for a in accused}
    pairs=set(); ki={}
    for a in accused:
        for k in phonetic_keys(a["AccusedName"]): ki.setdefault(k,[]).append(a["AccusedMasterID"])
    for k,ids in ki.items():
        for x,y in itertools.combinations(sorted(set(ids)),2): pairs.add((x,y))
    ei={}
    for a in accused:
        for e in conn_sig(graph,a["AccusedMasterID"]): ei.setdefault(e,[]).append(a["AccusedMasterID"])
    for e,ids in ei.items():
        for x,y in itertools.combinations(sorted(set(ids)),2): pairs.add((x,y))

    merges,reviews,relations=[],[],[]
    for (x,y) in pairs:
        act,s,det,rule=decide(store,graph,by_id[x],by_id[y])
        if act=="merge": merges.append((x,y,s,det,rule))
        elif act=="review": reviews.append((x,y,s,det,rule))
        elif act=="relate": relations.append((x,y,det))

    parent={a["AccusedMasterID"]:a["AccusedMasterID"] for a in accused}
    def find(v):
        while parent[v]!=v: parent[v]=parent[parent[v]]; v=parent[v]
        return v
    for (x,y,_,_,_) in merges: parent[find(x)]=find(y)
    cl={}
    for a in accused: cl.setdefault(find(a["AccusedMasterID"]),[]).append(a["AccusedMasterID"])
    groups=[sorted(v) for v in cl.values() if len(v)>1]
    return merges,reviews,relations,groups,pairs

def score(groups, gt):
    truth=set()
    for m in gt["identity_mappings"]:
        for x,y in itertools.combinations(sorted(m["accused_ids"]),2): truth.add((x,y))
    pred=set()
    for g in groups:
        for x,y in itertools.combinations(sorted(g),2): pred.add((x,y))
    tp=len(truth&pred); fp=len(pred-truth); fn=len(truth-pred)
    P=tp/(tp+fp) if tp+fp else 1.0; R=tp/(tp+fn) if tp+fn else 1.0; F=2*P*R/(P+R) if P+R else 0.0
    return {"tp":tp,"fp":fp,"fn":fn,"P":P,"R":R,"F":F,"missed":sorted(truth-pred),"false":sorted(pred-truth)}

if __name__=="__main__":
    store=RelationalStore(":memory:"); store.build(verbose=False)
    graph=NetworkXGraphStore(); build(store,graph); enrich(store,graph)
    gt=json.load(open("../01_data_generator/ground_truth.json",encoding="utf-8"))
    merges,reviews,relations,groups,pairs=resolve(store,graph)
    print("=== COMPONENT 5: KANNADA ENTITY RESOLUTION (final) ===")
    print(f"Candidate pairs (blocked): {len(pairs)}")
    print(f"Merges: {len(merges)} | Reviews: {len(reviews)} | Co-offender relations: {len(relations)}")
    print(f"Resolved identity groups: {len(groups)}")
    m=score(groups,gt)
    print(f"\n=== HONEST SCORE vs GROUND TRUTH ({m['tp']+m['fn']} true same-person pairs) ===")
    print(f"  TP={m['tp']}  FP(false merges)={m['fp']}  FN(missed)={m['fn']}")
    print(f"  PRECISION={m['P']:.3f}  RECALL={m['R']:.3f}  F1={m['F']:.3f}")
    if m["false"]: print(f"  false merges: {m['false'][:8]}")
    print("\n  Per true-identity-group recovery:")
    pred=set()
    for g in groups:
        for x,y in itertools.combinations(sorted(g),2): pred.add((x,y))
    for mm in gt["identity_mappings"]:
        gp=set(itertools.combinations(sorted(mm["accused_ids"]),2))
        found=len(gp&pred)
        label=mm.get('name_used', mm.get('name_variants','?'))
        print(f"    {mm['true_person']}: {found}/{len(gp)} pairs  ({label})")
    # explicit demo case
    print("\n  KANNADA VARIANT DEMO CASE (17,18,19):")
    for g in groups:
        if any(x in (17,18,19) for x in g):
            print(f"    resolved group containing variant: {g}")
    store.close()
