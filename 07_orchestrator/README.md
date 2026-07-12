# Component 7 — Orchestrator (the brain)

Flow: query -> intent classification -> retrieval dispatch (Component 6) -> narration (7a)
-> CITATION attachment -> AUDIT log -> response. Enforces two trust invariants on EVERY query:
citations (source FIR ids) and audit (who/when/intent/cases).

## Run
```
python3 orchestrator.py
```

## Verified (on synthetic data)
- similar_cases, network, identity_history (by context OR by name, incl. Kannada script), filter.
- identity_history correctly ASKS for a person handle instead of guessing when none is given
  (honest design: no fabricated answer to an unanswerable query).
- Every query is audit-logged; every answer carries citations to source FIRs.

## HONEST STANDINS (production swaps, identical interfaces)
- LLM narration: deterministic TEMPLATE here (proves orchestration + citation logic without a live
  model). PRODUCTION: Catalyst QuickML served model (GLM/Qwen) with a strict "narrate ONLY these
  cited facts, invent nothing" prompt (included as PRODUCTION_PROMPT_TEMPLATE in llm_interface.py).
- Intent classification: RULE-BASED keyword routing (transparent, debuggable). Production may add
  an LLM classifier behind the same interface.

## Trust invariant that transfers to production
The LLM NEVER sources connections — it only phrases retrieved, cited graph/DB facts. The data layer,
not the LLM, is the source of truth and (with Component 8) the authorization boundary.
