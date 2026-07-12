# Component 9 — Burglary Investigation Playbook (the delivery vehicle)

Chains all components into the officer workflow and produces a cited Investigation Brief:
BNS charges + similar-MO cases + criminal network + near-repeat hotspot + resolved repeat
offenders + concrete cited leads + evidence trail.

## Run
```
python3 playbook.py
```

## Verified (on the Mysuru cluster)
- Similar MO: 5 cluster burglaries surfaced semantically.
- Network: linked to 7 cases via shared phones.
- Near-repeat: 13 burglaries within 400m/42 days (closest 85m) — grounded in Johnson & Bowers
  near-repeat criminology (~400m / ~42 days), NOT invented.
- Repeat offender: Ramesh Gowda resolved across 5 cases.
- Every claim cited to source FIRs; human-verification notice on every brief.

## Same engine, three playbooks
Burglary is built deep. Fraud / missing-person are the SAME pipeline with different node priorities
(architected, not built) — demo one, show the architecture for three.
