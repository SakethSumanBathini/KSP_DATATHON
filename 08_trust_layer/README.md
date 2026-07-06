# Component 8 — Trust Layer (RBAC + Immutable Audit + Citations)

The component that wins a government jury: verifiable governance, not just capability.

## Run
```
python3 trust.py
```

## Verified
- RBAC scope enforced at the DATA layer: station_officer (28 cases) < district_sp (125) < scrb_analyst (500).
- Cross-jurisdiction access DENIED (Mysuru officer cannot open a Bengaluru case).
- Immutable audit: hash-chained; tampering with any entry is DETECTED (proven by actually tampering).
- PII masking: state_leadership sees [NAME-MASKED]/[PHONE-MASKED]; analysts see real data.
- Citation enforcement: case-specific claims without citations are BLOCKED.

## HONEST LIMITATION
The hash-chaining proves the audit MECHANISM (tamper-evidence). Production requires the audit store
itself to be append-only at the INFRASTRUCTURE level (Catalyst NoSQL write-once) — otherwise an admin
with store write-access could recompute the whole chain. RBAC here maps to Catalyst Auth + per-table
scopes in production. Mechanisms are correct; production hardening is infrastructure work.
