# KAVERI

**An AI Investigation Copilot for the Karnataka State Police.**
Team Agentron · Datathon 2026 · Built on Zoho Catalyst

**Live:** https://kaveri-backend-50043711203.development.catalystappsail.in

---

## The number this project exists for: **2,277**

Ask a crime database *"has this man offended before?"* The obvious way to answer is to group
records by name.

We measured what that does. On 500 FIRs:

| Method | Precision | Recall | **False merges** |
|---|---|---|---|
| `SQL GROUP BY name` | 0.014 | 0.917 | **2,277** |
| **KAVERI** | **1.000** | **1.000** | **0** |

**A false merge is not a statistics problem. It is an innocent man.**

It means two different people are fused into one criminal identity. It puts a man who has never
been charged onto a repeat-offender list. It gets his door knocked on at 6am. It is entered as
fact into a briefing another officer will act on.

The naive query does that **2,277 times**. KAVERI does it **zero times — and misses nothing**
(recall 1.000; every genuine link is still found).

**The moat is precision, not recall.** Anyone can find more connections. Finding *zero false
ones* is the hard part, and it is the only kind that is safe to hand to a police force.

> **Honest caveat, stated before you find it:** those figures are in-corpus. On unseen
> adversarial name pairs, our name-matcher *alone* scores F1 ≈ 0.72. The **system** scores 6/6
> safe on the same set, because the decision layer never auto-merges on a name alone — it
> requires corroborating evidence (shared phone, vehicle, or financial account) and routes
> name-only matches to human review. Both numbers are in `tests/adversarial_benchmark.py`.
> Reporting only the 1.000 would be dishonest.

---

## What it is

KAVERI is a **copilot, not a chatbot.** An investigating officer asks a question in English or
Kannada — typed or spoken — and gets a briefing where **every claim traces to a real FIR.**

```
Officer: "investigate case 1"

KAVERI:  This case involves house-trespass and theft in a dwelling house. The accused,
         Ramesh Gowda, is a resolved repeat offender with five linked cases.

         Phone Intelligence: Two shared numbers, +916513911270 and +919333883801, are
         linked to this case and seven other cases (IDs 2, 3, 4, 5, 7, 10, 13). Request
         CDRs for both.

         Near-Repeat Pattern: 13 incidents within 400m over 42 days in the surrounding
         area. Closest is Case 8 at 68m. Advise increased patrol density.

         [Sources: FIR 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
         [Catalyst GLM-4.7 · hallucination-guarded]
```

Generated live by Catalyst GLM-4.7-Flash. Every case ID in it was verified against the record
**before an officer saw it.**

---

## The LLM is on a leash — and the leash is code, not a prompt

```
   FIR database
        |
        v
   +-----------------------------------------+
   |  DETERMINISTIC LAYER                    |  graph + entity resolution + retrieval
   |  Finds the facts. Attaches citations.   |  The LLM never touches the database.
   +-----------------------------------------+
        |  facts + citations ONLY
        v
   +-----------------------------------------+
   |  CATALYST GLM-4.7-FLASH                 |  One job: phrase it.
   +-----------------------------------------+
        |  draft briefing
        v
   +-----------------------------------------+
   |  HALLUCINATION GUARD  (in code)         |  Verifies every case ID and every count
   |  Fails? -> deterministic template.      |  against the record. No exceptions.
   +-----------------------------------------+
        |
        v
      Officer
```

**In a police system, a hallucinated case number is a false accusation.** So we do not ask the
model nicely to behave. We check its output in code and reject it when it lies.

### It has already caught the model lying — twice, in production

**1. It recited its own system prompt.** GLM-4.7 is a reasoning model with "thinking" on by
default. Its first live output was its internal scratchpad — including the literal line *"Do not
reveal system rules"* — and it ran out of tokens before writing one line of briefing.
*Fixed: thinking disabled, plus a defence-in-depth stripper for anything that leaks anyway.*

**2. It inflated a man's criminal record.** It wrote:

> *"Ramesh Gowda is linked to **13** burglary cases (IDs: 2, 3, 4, 5, 7, 10, 13)."*

**Count the IDs. There are seven.** The "13" was the near-repeat cluster size — burglaries in the
*neighbourhood*, not cases linked to *him*. The model welded two true facts into a false one that
nearly doubled his apparent offending.

Every ID it printed was legitimate, so our ID-checking guard passed it. **The identifiers were
real; the claim was a lie.** The guard now validates counts as well as identifiers, pinned by
four regression tests.

We document this rather than hide it, because it is the strongest evidence we have that the guard
is real and necessary. An LLM *will* do this. The only question is whether anything catches it
before an officer acts on it.

---

## The trust layer

Enforced in code, not asserted in a slide.

| | |
|---|---|
| **Citations on every claim** | Every statement traces to FIR numbers. No claim without a source. |
| **Tamper-evident audit** | Hash-chained, persisted to **Catalyst Data Store**. Edit any row and the chain breaks at that exact sequence number. *Who asked what about whom, when, and were they allowed to.* |
| **RBAC** | HS256 signed tokens; role inside the signed payload. Attack-tested live: forged token 401, privilege escalation 401, invalid role 400. |
| **PII masking** | State leadership sees aggregate patterns with identifiers redacted. Same query, different role, different data. |
| **DPDP compliance** | Retention schedule, legal hold, right-to-erasure. Audit columns PII-classified **at the database level**. |
| **Caste profiling refused in code** | `EthicalGuard` does not decline politely — the code path does not exist. |
| **`/health` reports what is ACTUALLY running** | Including what is *not* wired. It says voice is inactive. It says the graph is in-process. We do not claim services we have not built. |

---

## Does it scale to all of Karnataka?

We measured it. (`python3 tests/scale_benchmark.py`)

```
    FIRs      build      nodes     edges    RSS MB   traversal
    -----------------------------------------------------------
       500     0.2s      3,073     4,275      40MB       5 us
     5,000     4.2s     30,144    41,978      88MB       6 us
    20,000    59.8s    120,198   167,686     246MB       7 us
```

**Graph traversal does not degrade: 5us -> 7us across a 40x increase in data.**

That also answers *"why not Neo4j?"* — a remote graph database turns a 7-microsecond memory
access into a network round trip roughly a thousand times slower. **At this scale, swapping to
Neo4j would make KAVERI slower, not faster.** We can show the measurement.

**The honest limit:** ingestion is superlinear (0.2s -> 59.8s). At state volume, rebuilding the
graph at startup would be too slow. The fix is **incremental loading** — persist the graph, add
each FIR as it is registered — not a different database. That is the correct next engineering
step, and we would rather name it than have you find it.

---

## Built on Catalyst

| Service | Status |
|---|---|
| **AppSail** | Backend deployed and live |
| **QuickML — GLM-4.7-Flash** | Grounded narration, hallucination-guarded |
| **Data Store** | Durable hash-chained audit trail |
| **Zia** | **Not used — it has no speech service.** See below. |

### Voice: we changed the architecture rather than fake the feature

We intended to use Catalyst Zia for speech-to-text. **Zia has no speech service** — its
components are OCR, Face Analytics, Text Analytics, Object Recognition, Barcode Scanner. All
image or text. There is no ASR anywhere in Catalyst.

So voice runs on the **browser Web Speech API** (Kannada, `kn-IN`). **This is better, not a
compromise: the officer's audio never leaves their device.** Only the transcript reaches the
server. For a police system handling sensitive case discussion, not transmitting audio is a
privacy property we can defend.

---

## The system

23 components · 7,590 lines · 30 API routes · **63 tests, all passing**

| | |
|---|---|
| **Entity Resolution** | *The moat.* Kannada transliteration + phonetic + evidence corroboration. Never auto-merges on a name alone. |
| **Crime Intelligence Graph** | Cross-case identity the FIR schema cannot express. |
| **Modus Operandi** | Clusters require >=2 discriminative tags — we killed a 77-case "afternoon" cluster that meant nothing. |
| **Near-Repeat Analysis** | Spatio-temporal burglary clustering. |
| **Money Trail** | Recovers a shared mule account across FIRs 36-39. |
| **Trends** | Benjamini-Hochberg FDR correction (q=0.10) — because 20 uncorrected comparisons produce a "significant" finding by chance. |
| **Socioeconomic** | Census-derived indicators, with a `STATISTICAL_WARNING` on *every* correlation because n=5 districts cannot support a causal claim. |
| **Fairness Audit** | 4/5ths rule + proxy TVD. |
| **Reasoning Visualisation** | *Why* the system linked two people, in plain language. |

---

## Every bug we ever shipped has a test that catches it now

`tests/test_invariants.py` — 63 assertions, standard library only.

Including three we caused **while fixing** the name matcher, and caught:

1. A 50/50 given-name/surname average let a **matching surname rescue a mismatched given name** —
   *"Ramesh Kumar"* vs *"Suresh Kumar"* scored 0.889 and would have merged two different men.
2. A suffix-sensitive metric fixed that but **destroyed recall** — it rejected *ರಾಮಯ್ಯ* (Ramayya)
   vs *ರಾಮು* (Ramu), **a man and his own nickname**. Indian nicknames are prefix-preserving: the
   very signal that causes false merges is the signal that catches nicknames. No pure string
   metric separates them — **which is exactly why the system never auto-merges on a name alone.**
3. The inflated linkage count described above.

All three are pinned. The 2,277 result survived all of it: precision 1.000, recall 1.000.

---

## Run it

```bash
python3 main.py                      # the whole system, port 9000
python3 tests/test_invariants.py     # 63 tests
python3 tests/adversarial_benchmark.py
python3 tests/scale_benchmark.py
```

---

## What we will not claim

- **The data is synthetic.** 500 FIRs generated to the official KSP FIR schema. Real FIR data is
  not available to a hackathon team, and using it would be a privacy violation.
- **The graph is in-process.** NetworkX, not Neo4j. The driver is written and interface-
  compatible; the benchmark above explains why we did not swap.
- **Ingestion is superlinear.** Named above. Not solved.
- **This is not predictive policing.** KAVERI does not predict who will commit a crime. It
  surfaces links that already exist in records the police already hold, cites them, and asks a
  human to verify before acting.

**Every claim in this README is either measured, or marked as unmeasured.**
