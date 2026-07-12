# Component 6 — Hybrid Retrieval

Three retrieval modes over the Crime Intelligence Graph, combined by the orchestrator:
1. GRAPH traversal — networks via shared phone/vehicle, cross-case identity history.
2. SEMANTIC search — similar modus operandi over BriefFacts (impossible in SQL).
3. STRUCTURED filter — by district, crime type.

## Run
```
python3 retrieval.py
```

## Verified (on synthetic data)
- Semantic MO search surfaces the Mysuru cluster burglaries from a natural-language query.
- Network mode finds a case's linked cases via shared extracted entities.
- Cross-case history pulls the Kannada variant's 3 cases under one resolved identity.

## HONEST LIMITATION (semantic backend)
The semantic index here is **TF-IDF**, a stand-in. It works well on synthetic data because
cluster cases share near-identical phrasing. Real FIRs describe the same MO in different words —
TF-IDF matches surface words, not meaning. PRODUCTION uses sentence-transformer / IndicBERT
embeddings in Qdrant (identical interface, drop-in swap). Real-world semantic recall will differ;
claim "semantic MO search, embeddings in production," not "perfect similarity."
