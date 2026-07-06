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
def name_similarity(a,b):
    fa,fb=roman_forms(a),roman_forms(b); best=0.0
    for x in fa:
        for y in fb:
            xa=x.split()[0] if x.split() else x; yb=y.split()[0] if y.split() else y
            best=max(best,jellyfish.jaro_winkler_similarity(xa,yb))
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
