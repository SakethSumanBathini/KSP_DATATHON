"""
Conversational Context + Bilingual (English/Kannada) query understanding.  [Challenge req 1]

  "Context-aware conversations allowing follow-up queries without repeating context"
  "Support for Multiple Languages, English and Kannada"

CONTEXT MODEL (deliberately simple and auditable — no hidden state):
  A Session holds the last-referenced case, person, and account. A follow-up query containing a
  referring expression ("this case", "he", "that account", "ಅವನ", "ಈ ಪ್ರಕರಣ") is RESOLVED against
  that state. If the reference cannot be resolved, we ASK — we never guess (guessing in a police
  system means asserting a false link about a real person).

BILINGUAL: Kannada intent keywords are matched directly (no translation round-trip needed for
routing). Kannada NAMES are already handled by Component 5's transliteration + entity resolution.
Query text may be Kannada, English, or code-mixed (which is how officers actually type).
"""
import re

# ---- intent keywords, English + Kannada ----
LAST_ROUTE_REASON = None   # why the LLM router did/didn't fire — surfaced, never swallowed

INTENT_KEYWORDS = {
    "network": {
        "en": ["network", "linked", "connected", "connection", "gang", "associates", "who else"],
        "kn": ["ಜಾಲ", "ಸಂಪರ್ಕ", "ಸಂಬಂಧ", "ಗುಂಪು", "ನೆಟ್‌ವರ್ಕ್", "ನೆಟ್ವರ್ಕ್", "ಲಿಂಕ್", "ಕನೆಕ್ಷನ್"],
    },
    "identity_history": {
        "en": ["history", "prior", "previous", "record", "alias", "same person", "background"],
        "kn": ["ಇತಿಹಾಸ", "ಹಿಂದಿನ", "ದಾಖಲೆ", "ಪೂರ್ವ", "ಹಿಸ್ಟರಿ", "ರೆಕಾರ್ಡ್", "ಪ್ರಯರ್"],
    },
    "similar_cases": {
        "en": ["similar", "same modus", "same mo", "like this", "comparable", "pattern"],
        "kn": ["ಹೋಲಿಕೆ", "ಸಮಾನ", "ಮಾದರಿ", "ಸಿಮಿಲರ್", "ಪ್ಯಾಟರ್ನ್"],
    },
    "risk": {
        "en": ["risk", "dangerous", "priority", "prioritise", "prioritize", "how serious"],
        "kn": ["ಅಪಾಯ", "ಆದ್ಯತೆ", "ರಿಸ್ಕ್", "ಪ್ರಯಾರಿಟಿ", "ಡೇಂಜರ್"],
    },
    "money_trail": {
        "en": ["money", "financial", "upi", "transaction", "account", "payment", "transfer"],
        "kn": ["ಹಣ", "ಹಣಕಾಸು", "ವರ್ಗಾವಣೆ", "ಖಾತೆ", "ಮನಿ", "ಟ್ರಾನ್ಸಾಕ್ಷನ್", "ಯುಪಿಐ", "ಅಕೌಂಟ್", "ಪೇಮೆಂಟ್"],
    },
    "trend": {
        "en": ["trend", "hotspot", "spike", "increase", "rising", "pattern over time", "forecast",
               "early warning", "alert", "cluster"],
        "kn": ["ಪ್ರವೃತ್ತಿ", "ಹೆಚ್ಚಳ", "ಎಚ್ಚರಿಕೆ", "ಟ್ರೆಂಡ್", "ಹಾಟ್‌ಸ್ಪಾಟ್", "ಅಲರ್ಟ್"],
    },
    "accused": {
        "en": ["main accused", "who is the accused", "accused", "suspect", "who did", "culprit"],
        "kn": ["ಆರೋಪಿ", "ಶಂಕಿತ", "ಯಾರು", "ಸಸ್ಪೆಕ್ಟ್", "ಅಕ್ಯೂಸ್ಡ್"],
    },
    "victim": {
        "en": ["victim", "complainant", "who was targeted", "who reported"],
        "kn": ["ಸಂತ್ರಸ್ತ", "ದೂರುದಾರ", "ವಿಕ್ಟಿಮ್", "ಕಂಪ್ಲೇನಂಟ್"],
    },
    "summary": {
        # "investigate case 1", "brief me on case 1", "tell me about case 1" all returned
        # "I could not map that to a capability" — the most natural way an officer would open a
        # case was the one phrasing the router had no word for.
        "en": ["investigate", "brief me", "briefing", "summarise", "summarize", "summary",
               "tell me about", "overview", "what happened"],
        "kn": ["\u0cb8\u0cbe\u0cb0\u0cbe\u0c82\u0cb6", "\u0cb5\u0cbf\u0cb5\u0cb0", "\u0cb8\u0cae\u0cb0\u0cbf"],
    },
    "status": {
        "en": ["status", "investigation status", "where does it stand", "chargesheet"],
        "kn": ["ಸ್ಥಿತಿ", "ತನಿಖೆ", "ಸ್ಟೇಟಸ್", "ಚಾರ್ಜ್‌ಶೀಟ್"],
    },
    "timeline": {
        "en": ["timeline", "chronology", "sequence", "what happened", "when did"],
        "kn": ["ಕಾಲಾನುಕ್ರಮ", "ಯಾವಾಗ", "ಟೈಮ್‌ಲೈನ್", "ಘಟನಾವಳಿ"],
    },
}

# referring expressions that REQUIRE prior context
REFERRING = {
    "case":   ["this case", "the case", "it", "this fir", "ಈ ಪ್ರಕರಣ", "ಈ ಎಫ್ಐಆರ್"],
    # AMBIGUITY FIX: bare "accused"/"ಆರೋಪಿ" is normally a FRESH question ("who is the accused?"),
    # not an anaphor ("what is HIS history?"). Treating it as a back-reference made the system
    # demand context for a perfectly self-contained question. Only unambiguously referential
    # expressions live here.
    "person": ["he", "him", "his", "she", "her", "this person", "that person", "same person",
               "ಅವನ", "ಅವನು", "ಅವಳ", "ಈ ವ್ಯಕ್ತಿ"],
    "account": ["that account", "this account", "the account", "ಈ ಖಾತೆ"],
}

KANNADA_RE = re.compile(r'[\u0C80-\u0CFF]')


def detect_language(text):
    """Kannada / English / code-mixed — officers really do type all three."""
    has_kn = bool(KANNADA_RE.search(text))
    has_en = bool(re.search(r'[A-Za-z]{2,}', text))
    if has_kn and has_en:
        return "code-mixed"
    if has_kn:
        return "kn"
    return "en"


def classify_intent(text):
    """
    Return (intent, matched_keyword, language).

    TWO-STAGE ROUTING, added after an honest look at what we had built:

      STAGE 1 — KEYWORD MATCH (below). Fast, free, deterministic, and correct whenever the
                officer happens to use a word we anticipated.

      STAGE 2 — LLM ROUTER (Catalyst GLM). Runs ONLY when the keywords miss. This is what turns
                "our conversational AI" from a lookup table into something an officer can
                actually talk to:

                    "who was this guy running with"   keywords: MISS   ->  LLM: network
                    "has he done this before"         keywords: MISS   ->  LLM: identity_history
                    "should I be worried about him"   keywords: MISS   ->  LLM: risk

    The LLM picks a ROUTE, never a FACT. A wrong route is cheap and visible — the officer sees
    the wrong tool and asks again. A wrong FACT is catastrophic and invisible. So the model is
    allowed to choose which deterministic capability runs, and is never allowed to produce the
    answer. If the LLM is off, times out, or returns anything not on our list, we keep whatever
    the keyword stage decided. It can only ever pick from a menu we wrote.
    """
    low = text.lower()
    lang = detect_language(text)
    for intent, langs in INTENT_KEYWORDS.items():
        for kw in langs["en"]:
            if kw in low:
                return intent, kw, lang
        for kw in langs["kn"]:
            if kw in text:
                return intent, kw, lang
    # Keywords missed -> ask the LLM to route it.
    #
    # NOTE THE ABSENCE OF `except: pass`. The first version of this swallowed every exception,
    # so when the router called the WRONG Catalyst endpoint it failed silently on every request
    # and simply looked like "the model chose not to route this". A silent except is a bug you
    # cannot find. Failures are now surfaced in LAST_ROUTE_REASON and reported in the API
    # response, so a broken router announces itself instead of quietly degrading.
    global LAST_ROUTE_REASON
    try:
        import os as _os, sys as _sys
        _sys.path.insert(0, _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "16_catalyst"))
        from catalyst_services import route_intent_llm
        _lang = "kn" if any("\u0c80" <= ch <= "\u0cff" for ch in text) else "en"
        intent, how = route_intent_llm(text, set(INTENT_KEYWORDS.keys()))
        LAST_ROUTE_REASON = how
        if intent:
            return intent, f"glm_router", _lang
    except Exception as e:
        LAST_ROUTE_REASON = f"router_exception:{type(e).__name__}:{str(e)[:60]}"

    return "unknown", None, lang


def _phrase_present(phrase, text_lower, text_raw):
    """
    WORD-BOUNDARY match. Substring matching is a BUG here: "the" contains "he", so
    "show me THE network" was being read as a reference to a male person. In a police system
    that means silently attaching a query to the wrong human being.
    Kannada has no ASCII word boundaries, so Kannada phrases are matched directly.
    """
    if KANNADA_RE.search(phrase):
        return phrase in text_raw
    return re.search(r'\b' + re.escape(phrase) + r'\b', text_lower) is not None


def find_reference(text):
    """Which kind of prior context does this query lean on, if any?"""
    low = text.lower()
    hits = []
    for kind, phrases in REFERRING.items():
        for p in phrases:
            if _phrase_present(p, low, text):
                hits.append(kind)
                break
    return hits


class Session:
    """
    Per-officer conversation state. AUDITABLE: every resolution records WHAT was inferred and
    from WHICH earlier turn — so an auditor can reconstruct why the system answered about person X.
    """
    def __init__(self, user, role):
        self.user = user
        self.role = role
        self.turns = []
        self.last_case = None
        self.last_person = None       # accused_id
        self.last_account = None

    def remember(self, case_id=None, person_id=None, account=None):
        if case_id is not None:
            self.last_case = case_id
        if person_id is not None:
            self.last_person = person_id
        if account is not None:
            self.last_account = account

    def resolve_query(self, text, explicit_case=None, explicit_person=None):
        """
        Resolve a possibly-elliptical follow-up against session state.
        Returns (context_dict, clarification_needed_or_None, provenance list).
        NEVER guesses: if a reference can't be resolved, it ASKS.
        """
        intent, kw, lang = classify_intent(text)
        refs = find_reference(text)
        # populate intent/language IMMEDIATELY so ctx is complete even on an early clarification
        ctx = {"case_id": explicit_case, "person_id": explicit_person, "account": None,
               "intent": intent, "language": lang, "matched_keyword": kw}
        provenance = []

        # explicit ids in the text, e.g. "FIR 17" / "case 17"
        m = re.search(r'\b(?:fir|case)\s*#?\s*(\d+)\b', text, re.IGNORECASE)
        if m:
            ctx["case_id"] = int(m.group(1))
            provenance.append(f"case {ctx['case_id']} stated explicitly in this query")

        # resolve referring expressions from session state
        if "case" in refs and ctx["case_id"] is None:
            if self.last_case is None:
                return (ctx, "Which case are you referring to? No case has been discussed yet in "
                              "this session.", provenance)
            ctx["case_id"] = self.last_case
            provenance.append(f"'this case' resolved to case {self.last_case} from the previous turn")

        if "person" in refs and ctx["person_id"] is None:
            if self.last_person is None:
                return (ctx, "Which person are you referring to? No accused has been discussed yet "
                              "in this session.", provenance)
            ctx["person_id"] = self.last_person
            provenance.append(f"'{'/'.join(r for r in refs if r=='person')}' resolved to accused "
                              f"{self.last_person} from the previous turn")

        if "account" in refs:
            if self.last_account is None:
                return (ctx, "Which account are you referring to?", provenance)
            ctx["account"] = self.last_account
            provenance.append(f"'this account' resolved to {self.last_account} from a previous turn")

        # intent needs a subject but none available -> ask, do not guess
        if intent in ("network", "similar_cases", "timeline", "accused", "victim", "status") \
                and ctx["case_id"] is None and not refs and self.last_case is None:
            return (ctx, f"Which case should I analyse? (no case in context)", provenance)
        if intent in ("network", "similar_cases", "timeline", "accused", "victim", "status") \
                and ctx["case_id"] is None:
            ctx["case_id"] = self.last_case
            if self.last_case is not None:
                provenance.append(f"case {self.last_case} carried over from context")

        if intent in ("identity_history", "risk") and ctx["person_id"] is None:
            if self.last_person is not None:
                ctx["person_id"] = self.last_person
                provenance.append(f"accused {self.last_person} carried over from context")

        return (ctx, None, provenance)

    def log(self, text, ctx, answer_summary):
        self.turns.append({"query": text, "context": dict(ctx), "answer": answer_summary})


if __name__ == "__main__":
    print("=== CONVERSATIONAL CONTEXT + BILINGUAL ROUTING ===\n")

    print("--- Language detection ---")
    for q in ["show the network for this case",
              "ಈ ಪ್ರಕರಣದ ಜಾಲ ತೋರಿಸಿ",
              "ರಾಮಯ್ಯ ಇತಿಹಾಸ show me"]:
        i, kw, lang = classify_intent(q)
        print(f"  [{lang:<10}] intent={i:<16} matched='{kw}'   | {q}")

    print("\n--- MULTI-TURN CONVERSATION (follow-ups WITHOUT repeating context) ---\n")
    s = Session("io_01", "station_officer")

    turns = [
        "Show me the criminal network for FIR 1",
        "Who is the main accused?",            # follow-up, no case repeated
        "What is his prior history?",          # 'his' -> resolved from context
        "How risky is he?",                    # 'he' -> still resolved
        "ಈ ಪ್ರಕರಣದ ಜಾಲ ತೋರಿಸಿ",                 # Kannada, 'this case' -> from context
    ]
    for t in turns:
        ctx, clarify, prov = s.resolve_query(t)
        print(f"  OFFICER: {t}")
        if clarify:
            print(f"  KAVERI : (asks) {clarify}")
        else:
            print(f"  KAVERI : intent={ctx['intent']}  case={ctx['case_id']}  person={ctx['person_id']}  lang={ctx['language']}")
            for p in prov:
                print(f"           ↳ context: {p}")
        # simulate the system learning from its own answer
        if ctx.get("case_id") == 1 and ctx["intent"] == "network":
            s.remember(case_id=1, person_id=1)
        elif ctx.get("case_id"):
            s.remember(case_id=ctx["case_id"])
        print()

    print("--- IT ASKS INSTEAD OF GUESSING (fresh session, no context) ---")
    s2 = Session("io_02", "station_officer")
    ctx, clarify, prov = s2.resolve_query("What is his prior history?")
    print(f"  OFFICER: What is his prior history?")
    print(f"  KAVERI : (asks) {clarify}")
    print("\n  ^ In a police system, guessing WHICH person means asserting a false link about a")
    print("    real human being. So it asks. This is a safety property, not a UX gap.")
