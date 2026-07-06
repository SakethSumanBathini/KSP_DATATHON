# Component 10 — Frontend (KAVERI Investigation Copilot UI)

React single-file app (kaveri_frontend.jsx). Renders the REAL backend output:
- Chat: natural-language query -> cited answer (network / identity / similar-MO).
- Network: Crime Intelligence Graph visualization (FIR 1 linked to 7 cases via shared phone).
- Brief: the full Investigation Brief from Component 9, with citations.
- Trust: RBAC table + role selector (PII masks live for State Leadership) + hash-chained audit view.
- Kannada voice button (finale demo placeholder).

## Data source
`sample_brief.json` is the ACTUAL output of Component 9 on the Mysuru cluster. The UI renders real
structures the backend produces (identity variants ರಾಮಯ್ಯ.ಕೆ / Ramaiah K / ರಾಮು shown resolved).

## HONEST STATUS
This is a UI shell wired to real backend OUTPUT (exported JSON), not yet a live API integration.
For the demo/deployment: connect the chat box to the Component 7 orchestrator endpoint on Catalyst,
and stream real query results. The rendering, RBAC masking, and brief layout are production-shaped;
the live API wiring is the remaining integration step. Run in any React environment (uses lucide-react).
