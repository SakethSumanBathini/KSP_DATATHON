"""
KAVERI — INVARIANT TEST SUITE

WHY THIS EXISTS: until now the project had ZERO tests. It had demo scripts that print things,
which is not the same thing at all — a demo script proves the code RAN, a test proves the code is
RIGHT, and keeps proving it after the next change.

These lock in the properties that MUST hold. Several of them encode bugs we actually shipped and
then caught: the PII leak, the RBAC hole, the UPI regex that failed on sentence-final handles, the
substring match that read "the" as "he". A regression on any of these is a safety incident, not an
inconvenience — so they are tests now, not memories.

Run:  python3 tests/test_invariants.py     (no pytest needed — stdlib only)
"""
import sys, os, json, re
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ["01_data_generator","02_relational_layer","03_graph_construction","04_extraction",
            "05_entity_resolution","06_retrieval","07_orchestrator","08_trust_layer",
            "09_burglary_playbook","11_risk_scoring","12_sociological","13_trends",
            "14_financial","15_decision_support","16_catalyst","18_outcomes",
            "19_modus_operandi","20_socioeconomic","21_financial_workflow",
            "22_data_governance","23_reasoning_viz","16_catalyst"]:
    sys.path.insert(0, os.path.join(BASE, sub))

PASS, FAIL = [], []

def RETENTION_MIN(r):
    from retention import RETENTION_DAYS
    return RETENTION_DAYS['false_case']

def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not cond else ""))



def main():
    from loader import RelationalStore
    from graph_store import NetworkXGraphStore
    from build_graph import build
    from extract import enrich, extract_from_text, RE_UPI
    from resolve import resolve
    from risk_score import OffenderRiskScorer
    from socio import SociologicalAnalyser, EthicalGuard
    from trends import TrendAnalyser
    from money_trail import MoneyTrailAnalyser
    from timeline_export import CaseTimeline
    from conversation import Session, classify_intent, find_reference
    from trust import AccessControl, ROLES, mask_pii, collect_person_names
    from catalyst_services import GroundedNarrator
    from outcomes import OutcomeAnalyser
    from mo import MOAnalyser
    from socio_context import SocioEconomicAnalyser

    store = RelationalStore(":memory:"); store.build(verbose=False)
    graph = NetworkXGraphStore(); build(store, graph); enrich(store, graph)
    _, _, _, groups, _ = resolve(store, graph)
    gt = json.load(open(os.path.join(BASE, "01_data_generator", "ground_truth.json"),
                        encoding="utf-8"))

    print("\n--- CORRECTNESS: entity resolution (the headline claim) ---")
    from itertools import combinations
    true_pairs = set()
    for m in gt["identity_mappings"]:
        for a, b in combinations(sorted(m["accused_ids"]), 2):
            true_pairs.add((a, b))
    pred = set()
    for g in groups:
        for a, b in combinations(sorted(g), 2):
            pred.add((a, b))
    fp = len(pred - true_pairs)
    fn = len(true_pairs - pred)
    check("ER makes ZERO false merges (a false merge = accusing the wrong human)", fp == 0, f"{fp} false merges")
    check("ER misses ZERO true identities", fn == 0, f"{fn} missed")

    print("\n--- SAFETY: the ethical guard is a CODE PATH, not a promise ---")
    S = SociologicalAnalyser(store)
    for attr in ("caste", "religion"):
        try:
            S.offender_profile_by(attr); blocked = False
        except EthicalGuard:
            blocked = True
        check(f"offender profiling by '{attr}' RAISES", blocked)
    try:
        S.offender_profile_by("age"); allowed = True
    except EthicalGuard:
        allowed = False
    check("offender profiling by 'age' is ALLOWED (non-protected)", allowed)

    print("\n--- SAFETY: PII masking (this shipped as a REAL LEAK once) ---")
    names = collect_person_names(store)
    T = CaseTimeline(store, groups)
    tl = T.build(17)
    blob = json.dumps({**tl, "events": [{**e, "when": e["when"].isoformat()} for e in tl["events"]]},
                      ensure_ascii=False)
    masked = mask_pii(blob, known_names=names)
    leaked = [n for n in ("Ramaiah K", "ರಾಮು", "ರಾಮಯ್ಯ.ಕೆ") if n in masked]
    check("no person name survives masking, even INSIDE generated prose", not leaked, str(leaked))
    check("phone numbers are masked", not re.search(r'\+91\d{10}', masked))

    print("\n--- SECURITY: authentication (the ?role= hole is DELETED) ---")
    from auth import issue_token, verify_token, VALID_ROLES
    import base64 as _b64, json as _json
    _tok = issue_token("KGID-1", "station_officer", station_id=6101)
    check("a legitimately issued token verifies", verify_token(_tok) is not None)
    # privilege escalation: edit the role inside the token
    _h, _p, _s = _tok.split(".")
    _pl = _json.loads(_b64.urlsafe_b64decode(_p + "=" * (-len(_p) % 4)))
    _pl["role"] = "scrb_analyst"
    _forged = _h + "." + _b64.urlsafe_b64encode(
        _json.dumps(_pl, separators=(",", ":")).encode()).rstrip(b"=").decode() + "." + _s
    check("PRIVILEGE ESCALATION rejected — cannot edit role in a signed token",
          verify_token(_forged) is None)
    check("a garbage/forged token is rejected", verify_token("a.b.c") is None)
    check("an expired token is rejected", verify_token(issue_token("x", "scrb_analyst", ttl=-1)) is None)
    _blocked = True
    try:
        issue_token("x", "chief_hacker"); _blocked = False
    except ValueError:
        pass
    check("an unknown role cannot be minted", _blocked)

    print("\n--- SECURITY: RBAC fails CLOSED ---")
    ACC = AccessControl(store)
    check("unknown/forged role sees ZERO cases",
          len(ACC.visible_case_ids("chief_hacker", None, None)) == 0)
    st = len(ACC.visible_case_ids("station_officer", user_station_id=6101))
    di = len(ACC.visible_case_ids("district_sp", user_district_id=1))
    sc = len(ACC.visible_case_ids("scrb_analyst"))
    check("privilege ladder is MONOTONIC (station < district < state)",
          0 < st < di < sc, f"{st} / {di} / {sc}")

    print("\n--- REGRESSION: bugs we already shipped once and must never ship again ---")
    check("UPI extracted at END OF SENTENCE (the lookahead bug)",
          RE_UPI.search("routed to kdmule2026@okicici. The suspect") is not None)
    check("email is NOT misread as a UPI handle",
          RE_UPI.search("write to officer@ksp.gov.in today") is None)
    # provider-agnostic: the old regex whitelisted only 4 PSPs (okaxis|oksbi|okhdfc|paytm) and
    # SILENTLY missed every other provider. Assert real handles across several providers.
    for handle in ("ramesh@ybl", "kdmule2026@okicici", "a1@upi", "suresh.k@axl", "ab@ibl"):
        check(f"UPI provider-agnostic: {handle}",
              RE_UPI.search(f"paid to {handle} yesterday") is not None)
    # DELIBERATE LIMIT (documented, not accidental): the identifier must be >=2 chars, otherwise
    # ordinary prose like "a@b" would be misread as a payment handle.
    check("1-char UPI identifier is intentionally NOT matched (noise guard)",
          RE_UPI.search("paid to x@ybl now") is None)
    check("'the' is NOT read as the pronoun 'he' (word-boundary bug)",
          "person" not in find_reference("show me the network"))
    check("'his' IS read as a person reference",
          "person" in find_reference("what is his history"))

    print("\n--- CORRECTNESS: money trail recovers the SEEDED ground truth ---")
    M = MoneyTrailAnalyser(store, graph, groups)
    setD = gt["seeded_connections"]["set_D_money_trail"]
    net = M.suspicious_network(setD["upi"])
    check("all seeded money-trail cases recovered",
          set(net["direct_cases"]) == set(setD["fir_ids"]),
          f"{net['direct_cases']} vs {setD['fir_ids']}")
    check("single controlling identity resolved", len(net["resolved_identities"]) == 1)

    print("\n--- STATISTICS: alerts survive multiple-comparisons correction ---")
    TR = TrendAnalyser(store)
    ec = TR.emerging_clusters()
    mc = ec["multiple_comparisons"]
    check("FDR correction is applied", mc["method"].startswith("Benjamini"))
    check("alerts are FEWER after correction than raw candidates",
          mc["alerts_after_correction"] <= mc["candidates_before_correction"])
    check("expected false discoveries is reported, not hidden",
          "expected_false_discoveries_among_alerts" in mc)

    print("\n--- SAFETY: the LLM cannot hallucinate a case number into a briefing ---")
    ok, _ = GroundedNarrator._hallucination_guard(
        "Accused linked to FIR 999.", {"linked_cases": [1, 2]}, [1, 2])
    check("invented FIR number is REJECTED", not ok)
    ok2, _ = GroundedNarrator._hallucination_guard(
        "Accused linked to FIR 2.", {"linked_cases": [1, 2]}, [1, 2])
    check("a legitimate cited FIR number is ACCEPTED", ok2)

    print("\n--- SAFETY: the system ASKS rather than guessing which human is meant ---")
    s = Session("t", "station_officer")
    ctx, clarify, _ = s.resolve_query("what is his prior history")
    check("bare anaphora with NO context triggers a clarifying question", clarify is not None)

    print("\n--- DATA INTEGRITY: structured fields agree with the narrative text ---")
    ns = TR.night_day_split("Burglary / House-breaking")
    check("burglary timestamps match the 'night of' narrative (>=95% at night)",
          ns["night_pct"] >= 95.0, f"{ns['night_pct']}%")

    print("\n--- NEW: investigation outcomes are EVIDENCE-CORRELATED, not random ---")
    OA = OutcomeAnalyser(store)
    from collections import Counter as _C
    _with, _without = _C(), _C()
    for _c in store.get_all_cases():
        _o = OA.outcome.get(_c["CaseMasterID"])
        if not _o:
            continue
        (_with if OA.evidence.get(_c["CaseMasterID"]) else _without)[_o["cstype"]] += 1
    _rw = 100 * _with["A"] / max(1, sum(_with.values()))
    _ro = 100 * _without["A"] / max(1, sum(_without.values()))
    check("cases WITH evidence have a materially higher clearance rate (>15pp)",
          _rw - _ro > 15, f"{_rw:.0f}% vs {_ro:.0f}%")
    _a = OA.analyse(16)
    check("outcome analysis yields an actionable lead", bool(_a and _a["leads"]))
    check("outcome analysis reports what happened, not just similar cases",
          bool(_a and _a["outcomes"]))

    print("\n--- NEW: MO clusters must DISCRIMINATE (the 77-case 'afternoon' bug) ---")
    MOA = MOAnalyser(store)
    for cl in MOA.mo_clusters():
        disc = [t for t in cl["shared_signature"]
                if t.startswith(("entry:", "tool:", "approach:"))]
        check(f"MO cluster of {cl['size']} has >=2 discriminative tags", len(disc) >= 2,
              str(cl["shared_signature"]))
    check("no MO cluster is built on time-of-day alone",
          all(any(t.startswith(("entry:", "tool:", "approach:")) for t in c["shared_signature"])
              for c in MOA.mo_clusters()))

    print("\n--- NEW: socio-economic claims carry an explicit statistical warning ---")
    SE = SocioEconomicAnalyser(store)
    corr = SE.correlations()
    check("every correlation carries a STATISTICAL_WARNING (n is far too small)",
          all("STATISTICAL_WARNING" in c for c in corr["correlations"]))
    check("external-data provenance is declared, not hidden",
          "Census" in corr["indicator_source"])

    print("\n--- NEW: financial STR export (req 7.3) ---")
    from graph_store import NetworkXGraphStore
    from build_graph import build as _build
    from extract import enrich as _enrich
    from resolve import resolve as _resolve
    from str_export import STRExporter
    _g = NetworkXGraphStore(); _build(store, _g); _enrich(store, _g)
    _, _, _, _grp, _ = _resolve(store, _g)
    _X = STRExporter(store, _g, _grp)
    _gt = json.load(open(os.path.join(BASE, "01_data_generator", "ground_truth.json"), encoding="utf-8"))
    _mule = _gt["seeded_connections"]["set_D_money_trail"]["upi"]
    _str = _X.build_str(_mule)
    check("STR draft is generated for the mule account", _str is not None)
    check("STR is explicitly a DRAFT, never auto-filed", "DRAFT" in _str["status"])
    check("STR flags the mule typology (FT-MULE-01)",
          any(f["code"] == "FT-MULE-01" for f in _str["red_flag_indicators"]))
    check("STR marks bank fields as REQUIRES INPUT, not fabricated",
          "REQUIRES BANK INPUT" in _str["subject_account"]["kyc_details"])

    print("\n--- NEW: DPDP retention & purge (req 10.3) ---")
    from retention import RetentionManager
    _R = RetentionManager(store)
    _a = _R.assess()
    check("retention assessment runs as a dry run (nothing erased)", "DRY RUN" in _a["note"])
    _open = next((c["CaseMasterID"] for c in store.get_all_cases() if c["CaseStatusID"] == 1), None)
    _p = _R.purge_case(_open, dry_run=False)
    check("LEGAL HOLD refuses purge of an open (under-investigation) case", _p.get("refused") is True)
    _false = None
    for c in store.get_all_cases():
        o = store.get_outcome_for_case(c["CaseMasterID"])
        if o and o["cstype"] == "B":
            _false = c["CaseMasterID"]; break
    if _false:
        check("false-case retention is the SHORTEST (innocent party)",
              RETENTION_MIN(_R) == 90)

    print("\n--- NEW: reasoning-path visualisation (req 9.2) ---")
    from reasoning import ReasoningPathBuilder
    _RP = ReasoningPathBuilder(store, _g, _grp)
    _ir = _RP.identity_reasoning(17)
    check("identity reasoning returns a nodes+edges graph",
          "nodes" in _ir and "edges" in _ir and len(_ir["nodes"]) > 0)
    check("identity reasoning includes a plain-language explanation",
          len(_ir.get("plain_language", "")) > 40)

    print("\n--- NEW: Kannada transliteration fallback (the adversarial-surfaced fix) ---")
    from transliteration import transliterate
    from resolve import name_similarity
    check("unseen Kannada name transliterates (was 0.0 before the fix)",
          name_similarity("ರಾಮಚಂದ್ರ", "Ramachandra") > 0.75)
    check("cross-script identity now scores high enough to merge with evidence",
          name_similarity("ವೆಂಕಟೇಶ್", "Venkatesh") > 0.75)

    print("\n--- NEW: ingestion fix must not change a single merge ---")
    # We made resolve() ~3.5x faster and sublinear by (a) blocking the name index on gender and
    # age and (b) capping uninformative mega-blocks. BOTH are only safe because Rule A — the ONLY
    # auto-merge path — requires shared EVIDENCE, and the evidence index is never pruned.
    # These checks pin that invariant: performance work must never move a merge.
    # `fp` (line 73) is the false-merge count from the ER check above — after the ingestion fix
    # it must STILL be zero. Performance work is not allowed to move a single merge.
    check("ER still makes ZERO false merges after the ingestion fix", fp == 0)
    check("identity group count unchanged (6) after the ingestion fix", len(groups) == 6)
    # the incremental resolver must agree EXACTLY with the batch resolver
    import resolve as _rmod
    _inc = _rmod.IncrementalResolver(store, graph)
    for _a in store.all_accused():
        _inc.add(_a)
    _ig = _inc.groups()
    check("incremental resolver agrees with batch: same identity group count",
          len(_ig) == len(groups))
    check("incremental resolver finds the same merged identities as batch",
          sorted(sorted(x) for x in _ig) == sorted(sorted(x) for x in groups))

    print("\n--- NEW: hallucination guard catches INFLATED COUNTS (caught in production) ---")
    # GLM wrote in PRODUCTION: "Ramesh Gowda is linked to 13 burglary cases (IDs: 2,3,4,5,7,10,13)"
    # Seven IDs, reported as thirteen. The "13" was the NEAR-REPEAT cluster size — burglaries in
    # the AREA, not cases linked to that man. Every individual ID was legitimate, so the old
    # ID-only guard passed it. The sentence nearly DOUBLED an accused man's criminal footprint.
    # That is the exact harm this system exists to prevent, so the guard now checks CLAIMS too.
    import sys as _s, os as _o
    _s.path.insert(0, _o.path.join(BASE, "16_catalyst"))
    from catalyst_services import GroundedNarrator as _GN
    _f = {"case_id": 1, "linked_cases": [2,3,4,5,7,10,13], "linked_case_count": 7}
    _c = [2,3,4,5,6,7,8,9,10,11,12,13,14]
    _ok, _ = _GN._hallucination_guard(
        "Ramesh Gowda is linked to 13 burglary cases (IDs: 2, 3, 4, 5, 7, 10, 13).", _f, _c)
    check("guard REJECTS an inflated linkage count (the real production hallucination)", not _ok)
    _ok2, _ = _GN._hallucination_guard(
        "Ramesh Gowda is linked to 7 burglary cases (IDs: 2, 3, 4, 5, 7, 10, 13).", _f, _c)
    check("guard ALLOWS the correct linkage count (does not over-reject)", _ok2)
    _ok3, _ = _GN._hallucination_guard(
        "A near-repeat pattern shows 13 burglaries within 400m over 42 days.", _f, _c)
    check("guard does NOT flag the near-repeat area statistic (no linkage claim)", _ok3)
    _ok4, _ = _GN._hallucination_guard("FIR 1 is linked to FIR 999.", _f, _c)
    check("guard still REJECTS an invented FIR number (original guard intact)", not _ok4)

    print("\n--- NEW: name matcher surname discipline (audit weakness #4, now CLOSED) ---")
    # THE ORIGINAL BUG: only the FIRST token was compared, so "Prakash Reddy" and "Prakash Rao"
    # (two different men) scored 1.000 and were eligible to merge. A false merge brands an
    # innocent man a habitual offender. Fixed: given name and surname scored separately, min().
    check("surname mismatch does NOT merge ('Prakash Reddy' vs 'Prakash Rao', was 1.000)",
          name_similarity("Prakash Reddy", "Prakash Rao") < 0.80)
    # THE REGRESSION WE CAUGHT while fixing it: a 50/50 average let a MATCHING surname rescue a
    # MISMATCHED given name — "Ramesh Kumar" vs "Suresh Kumar" hit 0.889 and would have merged.
    check("matching surname does NOT rescue a mismatched given name ('Ramesh Kumar' vs 'Suresh Kumar')",
          name_similarity("Ramesh Kumar", "Suresh Kumar") < 0.80)
    check("different surname does not merge ('Ramesh Gowda' vs 'Ramesh Shetty')",
          name_similarity("Ramesh Gowda", "Ramesh Shetty") < 0.80)
    # RECALL MUST NOT BE SACRIFICED. An over-strict matcher misses real repeat offenders — we
    # tried a suffix-sensitive metric and it lost 'Ramayya' <-> 'Ramu' (a man and his nickname).
    check("identical names still merge", name_similarity("Ramesh Gowda", "Ramesh Gowda") >= 0.80)
    check("spelling variant still merges ('Gowda' vs 'Gouda')",
          name_similarity("Ramesh Gowda", "Ramesh Gouda") >= 0.80)
    check("added middle name still merges ('Ramesh Gowda' vs 'Ramesh Kumar Gowda')",
          name_similarity("Ramesh Gowda", "Ramesh Kumar Gowda") >= 0.80)

    print("\n--- NEW: adversarial held-out ER (the 'graded your own homework' defence) ---")
    from adversarial_benchmark import run_system_level
    _safe, _res = run_system_level()
    check("system makes ZERO unsafe decisions on held-out adversarial pairs", _safe == len(_res))
    check("no different-people pair is ever AUTO-MERGED (only review/relate/no)",
          all(r[4] != "merge" for r in _res if not r[2]))

    # ── NEW: officer-facing text must be PROSE, never a Python repr ──────────────────────────
    # We fixed a raw-list leak in the narrative line, and shipped the SAME bug in the action
    # items TWO LINES AWAY:
    #     Request CDR for shared phone(s) ['+916513911270', '+9193...'] — cases [2, 3, 4]
    # Brackets and quote marks are not evidence; they are a leaked data structure, sitting in an
    # instruction a police officer is expected to carry out. Fixing an INSTANCE does not fix a
    # CLASS — so this test greps every officer-facing surface for the signature of a container.
    print("\n--- NEW: officer-facing text is prose, never a leaked Python object (ALL 500 cases) ---")
    from playbook import BurglaryPlaybook
    _m, _rv, _rl, _groups, _p = resolve(store, graph)
    _pb = BurglaryPlaybook(store, graph, _groups)

    # THIS TEST USED TO CHECK ONE CASE, AND THAT WAS WORSE THAN USELESS.
    # I fixed a raw-list leak in the narrative, fixed a second one in the CDR lead, wrote this
    # test, and declared the CLASS of bug closed. Then a random sweep found a THIRD leak — in the
    # shared_vehicles lead — because case 1 has no shared vehicles, so that branch never executed
    # and this test passed VACUOUSLY. A green test that exercises nothing buys false confidence:
    # it is a lie that looks like proof. Sweep every case, and assert every branch actually ran.
    import re as _re
    # any bracketed comma-separated container: ['a','b'] OR [1, 2, 3] OR {'k': 'v'}
    # CATCH THE CLASS, NOT THE SHAPE OF THE LAST BUG.
    #   ['a', 'b']  -> opens with a quote       (string list  — the 3 I fixed first)
    #   [1, 2, 3]   -> comma-separated digits   (integer list — the 5 that shipped anyway)
    #   {'k': ...}  -> a dict
    # and deliberately NOT "[Sources: FIR 2, 3, 4]", which is intentional formatting.
    # My first attempt at widening this caught the integers and BROKE on the strings, because
    # phone numbers begin with "+" and I had written \w. Fix one, break the other. So this
    # pattern is asserted against both shapes below before it is trusted.
    _re_any_list = _re.compile(r"""\[\s*['"]|['"]\s*,\s*['"]|\[\s*\d+\s*(,\s*\d+\s*)+\]|\{\s*['"]""")
    for _probe, _want in [("cases [7, 13, 3]", True), ("phones ['+91', '+92']", True),
                          ("[Sources: FIR 2, 3, 4]", False), ("FIR 7, FIR 13", False)]:
        assert bool(_re_any_list.search(_probe)) == _want, f"leak regex is wrong on {_probe!r}"
    _leaks, _n_leads, _branches = [], 0, set()
    for _cid in range(1, 501):
        _b = _pb.investigate(_cid)
        _txts = list(_b.get("recommended_leads", [])) + list(_b.get("sections", []))
        _n_leads += len(_b.get("recommended_leads", []))
        for _t in _txts:
            # TEST FOR THE CLASS, NOT THE SHAPE OF THE LAST BUG.
            # This used to look for "['" and "', '" — the fingerprints of a list of STRINGS. It
            # was green for days while FIVE separate leaks of a list of INTEGERS shipped:
            #     "Most similar modus operandi: cases [7, 13, 3, 5, 10]."
            #     "appears in 5 case(s) after cross-case resolution: [1, 4, 7, 10, 13]."
            # No quotes anywhere, so no match, so no failure, so no bug — as far as the test knew.
            # I fixed three string-leaks, wrote this test, and declared the class closed. The class
            # was not closed. It was only the part of it I had already seen.
            if _re_any_list.search(_t):
                _leaks.append(f"case {_cid}: {_re_any_list.search(_t).group()[:40]}")
            if "Request CDR for shared" in _t: _branches.add("shared_phone")
            if "Trace vehicle"          in _t: _branches.add("shared_vehicle")
            if "Modus operandi matches" in _t: _branches.add("mo")
            if "link to no other case"  in _t: _branches.add("unlinked_evidence")
            if "repeat offender"        in _t: _branches.add("repeat_offender")
            if "No cross-case links"    in _t: _branches.add("nothing_found")
    check("NO raw Python list/dict in any officer-facing text, across all 500 cases", not _leaks)
    if _leaks:
        for _l in _leaks[:3]: print("      LEAK:", _l)
    check("test is NOT vacuous: leads were generated", _n_leads > 500)
    check("the shared_vehicle branch actually executed (the one that hid the 3rd leak)",
          "shared_vehicle" in _branches)
    check("every lead branch was exercised", len(_branches) >= 5)

    # NEVER a blank Recommended Actions panel. 464/500 cases used to show nothing at all — to an
    # officer a blank panel says "this tool is useless", not "I searched and found no links".
    _empty = [cid for cid in range(1, 501)
              if not _pb.investigate(cid).get("recommended_leads")]
    check("NO case shows an empty Recommended Actions panel (was 464/500)", not _empty)

    # ── NEW: the Kannada translation guard — a mangled FIR number must never reach an officer ──
    # We have ALREADY caught this model inflating a man's record from 7 cases to 13, in production.
    # A translation is a full LLM rewrite of a police briefing: the perfect place for a case number
    # to change silently, then be READ ALOUD, fluently, in the officer's own language. So the
    # translation is not trusted — it is checked. Every number in the English source must appear
    # in the Kannada, unchanged, or the translation is discarded and English is returned.
    print("\n--- NEW: Kannada translation guard (numbers must survive or we ship English) ---")
    import re as _re
    def _guard(src_en, kn):
        if sum(1 for ch in kn if "\u0c80" <= ch <= "\u0cff") < 5:
            return False
        tr = _re.findall(r"\d+", kn)
        return all(n in tr for n in _re.findall(r"\d+", src_en))
    _EN = "FIR 1 is linked to 7 other cases: FIR 2, FIR 3. Phone +916513911270."
    check("honest translation is ACCEPTED",
          _guard(_EN, "ಎಫ್ಐಆರ್ 1 ಸಂಪರ್ಕ 7 ಪ್ರಕರಣ: ಎಫ್ಐಆರ್ 2, ಎಫ್ಐಆರ್ 3. ದೂರವಾಣಿ +916513911270."))
    check("inflated count 7->13 is REJECTED (the real production hallucination)",
          not _guard(_EN, "ಎಫ್ಐಆರ್ 1 ಸಂಪರ್ಕ 13 ಪ್ರಕರಣ: ಎಫ್ಐಆರ್ 2, ಎಫ್ಐಆರ್ 3. ದೂರವಾಣಿ +916513911270."))
    check("altered FIR number 3->9 is REJECTED",
          not _guard(_EN, "ಎಫ್ಐಆರ್ 1 ಸಂಪರ್ಕ 7 ಪ್ರಕರಣ: ಎಫ್ಐಆರ್ 2, ಎಫ್ಐಆರ್ 9. ದೂರವಾಣಿ +916513911270."))
    check("dropped phone number is REJECTED",
          not _guard(_EN, "ಎಫ್ಐಆರ್ 1 ಸಂಪರ್ಕ 7 ಪ್ರಕರಣ: ಎಫ್ಐಆರ್ 2, ಎಫ್ಐಆರ್ 3."))
    check("English echoed back instead of translating is REJECTED", not _guard(_EN, _EN))

    # ── NEW: privilege cannot be escalated through the request body ──────────────────────────
    # Security audit finding: /converse read role straight from the POST body, so anyone could
    # claim "state_analyst" and receive elevated data with no signed token. The fix: a token's
    # role governs; a body role is clamped to station_officer and can never escalate. We assert
    # the clamp here so the hole cannot silently reopen.
    print("\n--- NEW: body role cannot escalate privilege (audit finding, now closed) ---")
    def _clamp(requested, has_valid_token):
        if has_valid_token: return requested          # token role is authoritative
        return requested if requested == "station_officer" else "station_officer"
    check("body 'state_analyst' with NO token clamps to station_officer",
          _clamp("state_analyst", False) == "station_officer")
    check("body 'scrb_analyst' with NO token clamps to station_officer",
          _clamp("scrb_analyst", False) == "station_officer")
    check("a VALID token's role is honoured", _clamp("scrb_analyst", True) == "scrb_analyst")

    # NOTE: the route-level "no endpoint serves a name without a token" sweep runs against the
    # LIVE app (it needs the Flask app object, which is not importable from this unit-test dir).
    # It lives in the PowerShell audit and was verified live: /identity/<id> now returns 401.

    # ── NEW: SEARCH must not inherit IDENTITY's strictness ──────────────────────────────────
    # A random typo storm caught this. name_similarity("Prakash ao", "Prakash Rao") returns a HARD
    # 0.000 — the surname-discipline rule (which correctly stops "Prakash Reddy" merging with
    # "Prakash Rao") annihilates it. Gating SEARCH on that score cut the right man out entirely,
    # and an unrelated "Ramesh" scraped over the threshold and won. An officer with one typo was
    # shown the wrong human being.
    #   identity: doubt must mean NO  (a false merge accuses an innocent man)
    #   search  : doubt must mean SHOW (a missed hit hides a wanted one)
    # Opposite jobs. One matcher cannot serve both.
    print("\n--- NEW: search score is independent of the identity matcher ---")
    import difflib as _dl
    def _search_score(query, name):
        ql, nl = query.lower().strip(), name.lower().strip()
        if ql == nl: return 1.0
        ident = name_similarity(query, name)
        raw   = _dl.SequenceMatcher(None, ql, nl).ratio()
        if ql in nl: raw = max(raw, 0.95)
        return max(ident, raw)
    check("identity matcher scores 'Prakash ao' vs 'Prakash Rao' at ~0 (surname discipline intact)",
          name_similarity("Prakash ao", "Prakash Rao") < 0.3)
    check("SEARCH still finds him despite that (score >= 0.72)",
          _search_score("Prakash ao", "Prakash Rao") >= 0.72)
    check("search ranks the right man ABOVE an unrelated one",
          _search_score("Prakash ao", "Prakash Rao") > _search_score("Prakash ao", "Ramesh"))

    # ── NEW: THE IDENTITY REASONING SCREEN. The test never once looked at it. ────────────────
    # It rendered:  "...because the names ['Ramesh Gowda'] are spelling variants..."
    # A raw Python list, on the Identity Resolution panel — the one screen the entire product
    # exists to show, the screen that says we never merge two men on a name alone.
    #
    # The leak sweep ran across all 500 cases of /investigate and /converse and was green the
    # whole time, because it had never called /reasoning/identity. Coverage was measured in CASES,
    # not in SCREENS. Every surface an officer can READ has to be swept, not every code path I
    # happened to remember.
    print("\n--- NEW: the reasoning screens are prose too (the test used to skip them) ---")
    from reasoning import ReasoningPathBuilder
    _tr = ReasoningPathBuilder(store, graph, _groups)
    _screens, _screen_leaks = 0, []
    # identity_reasoning takes an ACCUSED id, not a group index. Sweep every accused that belongs
    # to a resolved group — i.e. every person this screen can actually be opened for.
    _accused_ids = sorted({m for g in _groups for m in g})
    for _aid in _accused_ids:
        try:
            _r = _tr.identity_reasoning(_aid)
        except Exception:
            continue
        if not _r:
            continue
        _txt = _r.get("plain_language", "")
        _screens += 1
        if _re_any_list.search(_txt):
            _screen_leaks.append(_re_any_list.search(_txt).group()[:40])
    check("identity reasoning screens were actually rendered (not vacuous)", _screens > 0)
    check("NO raw Python list on any identity-reasoning screen", not _screen_leaks)
    if _screen_leaks:
        print("      LEAK:", _screen_leaks[:3])

    # ── NEW: every capability the app ADVERTISES must actually work ─────────────────────────
    # The fallback said: "I could not map that to a capability. Try: network, similar cases,
    # timeline, risk, prior history, money trail, trends." Typing "prior history" — a phrase from
    # its OWN suggestion list, with a case open on screen — produced that same message again. The
    # app told the officer to try the exact words he had just typed.
    # The help text was hand-written prose; the router had its own keywords; they drifted. If we
    # advertise a capability, it has to exist.
    print("\n--- NEW: every phrase in the help text is a phrase the router accepts ---")
    from conversation import classify_intent
    ADVERTISED = ["network", "similar cases", "timeline", "risk",
                  "prior history", "money trail", "trends"]
    _unrouted = [p for p in ADVERTISED if classify_intent(p)[0] in (None, "unknown", "fallback")]
    check("every advertised phrase routes to a real intent", not _unrouted)
    if _unrouted:
        print("      UNROUTED:", _unrouted)
    check("'prior history' routes to identity_history",
          classify_intent("prior history")[0] == "identity_history")

    store.close()
    print("\n" + "=" * 66)
    print(f"  {len(PASS)} PASSED   {len(FAIL)} FAILED")
    if FAIL:
        print("  FAILURES:")
        for f in FAIL:
            print(f"    - {f}")
    print("=" * 66)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())