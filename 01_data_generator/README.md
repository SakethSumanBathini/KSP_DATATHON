# Component 1 — Synthetic FIR Data Generator

Schema-accurate synthetic Karnataka Police FIR dataset for the KSP Datathon crime-intelligence system.

## Run
```
pip install faker
python3 generate.py
```
Fixed seed (20260706) → reproducible output.

## Outputs
- `*.csv` — one per table (CaseMaster, Accused, Victim, ComplainantDetails, ArrestSurrender, Act, Section, ActSectionAssociation, + reference tables)
- `ground_truth.json` — TRUE identity mappings, seeded connections, entity→FIR links (for scoring components 4 & 5)
- `sample_output.txt` — human-readable view of the three seeded connection sets

## Schema fidelity
Grounded in the real Karnataka Police ER diagram. CrimeNo = 1-digit category + 4-digit district + 4-digit unit + 4-digit year + 5-digit serial (18 digits). Offenses normalized via Act/Section: BNS active, IPC marked Active=0 (legacy).

## Seeded connection sets (the ER + extraction test targets)
- **Set A** — 14 Mysuru burglary FIRs; one phone shared across 5, one UPI across 2; near-repeat spatial cluster (~400m, ~42 days); consistent night house-breaking MO. 3 recurring accused → 3 identity groups in ground truth.
- **Set B** — one accused + one vehicle across a Bengaluru Urban and a Belagavi FIR, different IOs. Cross-district link invisible to SQL.
- **Set C** — one real person written 3 ways (ರಾಮಯ್ಯ.ಕೆ / Ramaiah K / ರಾಮು) across 3 FIRs. The core Kannada entity-resolution test.
- **Decoys** — 6 DIFFERENT people all named "Ramesh", age 34. Must NOT be merged (ER precision stress).

## Known limitations (honest)
- Decoys are exact-string dupes; they test the precision floor, not plausible near-match precision. Add harder near-match decoys when scoring component 5 for a more meaningful precision number.
- Ground truth contains 5 identity groups total (3 from Set A, 1 from Set B, 1 from Set C) — component 5 is scored against all of them, not just the Kannada variant.
