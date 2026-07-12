"""
Component 16 — Catalyst Service Integration Layer

WHY THIS EXISTS
  The Datathon rules state: "Using a third-party alternative when a Catalyst service is available
  may affect the validity of your submission." Zoho Catalyst is the tech partner. Beyond hosting on
  AppSail we were using SQLite, a templated narrator, and no auth — all third-party/local
  alternatives to services Catalyst provides. That is a stated VALIDITY RISK, not a style point.

DESIGN
  Every integration is an ADAPTER behind a stable interface, selected by environment variable:

      CATALYST_ENABLED=true  + credentials  ->  real Catalyst service
      (unset)                               ->  local fallback (offline dev, and what the
                                                 judges' clone will run without our secrets)

  So the same code path demonstrates Catalyst usage in production AND still runs on a laptop.

HONEST STATUS  (read this before trusting it)
  These adapters are written against Catalyst's documented REST APIs. They are NOT yet executed
  against a live Catalyst tenant from this sandbox — the sandbox has no network access to
  zohocatalyst.com and no project credentials. Every adapter therefore:
    (a) fails CLOSED to the local fallback rather than crashing the app,
    (b) logs exactly which backend served the request, so you can SEE which one ran,
    (c) is marked UNVERIFIED below until you run verify_catalyst.py against your tenant.
  Do not claim "Catalyst-native" to a judge until that script prints PASS for each service.
"""
import os, json, time, urllib.request, urllib.error, urllib.parse

# ── Catalyst GenAI wiring (GLM-4.7-Flash via QuickML LLM Serving) ──
# NOTE ON ENV VAR NAMES: Catalyst REJECTS any environment variable whose name starts with a
# reserved prefix (CATALYST_, ZOHO_, X_ZOHO_) — we hit that wall trying to set CATALYST_ENABLED.
# So every variable below uses the KAVERI_ prefix, which Catalyst accepts.
#
# Secrets (client secret + refresh token) are read from the environment ONLY. They live in the
# Catalyst console's Environment Variables, never in this repo. If they are absent, the whole GLM
# path is skipped and we fall back to the deterministic template — safe by default.
LLM_ENABLED       = os.getenv("KAVERI_LLM_ENABLED", "false").lower() == "true"
LLM_ORG_ID        = os.getenv("KAVERI_LLM_ORG_ID", "60076922859")
LLM_ENDPOINT      = os.getenv("KAVERI_LLM_ENDPOINT",
                              "https://api.catalyst.zoho.in/quickml/v1/project/"
                              "54992000000013047/glm/chat")
LLM_MODEL         = os.getenv("KAVERI_LLM_MODEL", "crm-di-glm47b_30b_it")
LLM_CLIENT_ID     = os.getenv("KAVERI_LLM_CLIENT_ID", "")
LLM_CLIENT_SECRET = os.getenv("KAVERI_LLM_CLIENT_SECRET", "")
LLM_REFRESH_TOKEN = os.getenv("KAVERI_LLM_REFRESH_TOKEN", "")
LLM_TOKEN_URL     = os.getenv("KAVERI_LLM_TOKEN_URL",
                              "https://accounts.zoho.in/oauth/v2/token")

# Kept for the status() report and backward compatibility. "Catalyst enabled" now means
# "the GLM path is configured and switched on".
CATALYST_ENABLED = LLM_ENABLED
CATALYST_PROJECT_ID = "54992000000013047"

# which backend actually served each capability — surfaced at /health so it is never a guess
BACKEND_LOG = {}

# short-lived access token cache: Zoho access tokens last ~1h; we refresh a little early.
_TOKEN_CACHE = {"access_token": None, "expires_at": 0}


def _get_access_token(timeout=8):
    """
    Exchange the long-lived REFRESH token for a short-lived ACCESS token, cached ~55 min.
    The refresh token is the only durable secret; it never leaves the environment. Returns the
    access token string, or None if credentials are missing / the exchange fails (fail-safe:
    callers then fall back to the local template).
    """
    now = time.time()
    if _TOKEN_CACHE["access_token"] and now < _TOKEN_CACHE["expires_at"]:
        return _TOKEN_CACHE["access_token"]
    if not (LLM_CLIENT_ID and LLM_CLIENT_SECRET and LLM_REFRESH_TOKEN):
        return None
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": LLM_CLIENT_ID,
        "client_secret": LLM_CLIENT_SECRET,
        "refresh_token": LLM_REFRESH_TOKEN,
    }).encode()
    req = urllib.request.Request(LLM_TOKEN_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        tok = json.loads(r.read().decode())
    access = tok.get("access_token")
    if access:
        # expires_in is seconds (~3600); refresh 5 min early to avoid edge expiry mid-request
        _TOKEN_CACHE["access_token"] = access
        _TOKEN_CACHE["expires_at"] = now + int(tok.get("expires_in", 3600)) - 300
    return access


def _post(path, body, timeout=8):
    """
    Generic Catalyst BAAS POST — used by the NOT-YET-WIRED adapters (Zia voice, NoSQL audit,
    Catalyst Auth). These remain OFF for now: without an access token the call raises and each
    caller falls back locally. When we wire Zia/NoSQL later, this is the shared transport.
    """
    access = _get_access_token()
    headers = {"Content-Type": "application/json", "CATALYST-ORG": LLM_ORG_ID}
    if access:
        headers["Authorization"] = f"Zoho-oauthtoken {access}"
    url = f"https://api.catalyst.zoho.in/baas/v1/project/{CATALYST_PROJECT_ID}{path}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())



def _strip_reasoning(text):
    """
    DEFENCE IN DEPTH. Even with enable_thinking=False, a reasoning model can leak a scratchpad
    ("1. Analyze the Request...", "<think>...", "Drafting the Briefing:"). An officer must never
    see the model's internal monologue — and it can echo the system prompt back, which is a
    prompt-leak. So we strip any known reasoning wrapper and keep only the final answer.
    """
    import re as _re
    t = text.strip()
    # explicit thinking tags
    if "</think>" in t:
        t = t.split("</think>", 1)[1].strip()
    # numbered "meta" scaffolding the model sometimes emits before the real answer
    for marker in ("**Final Briefing", "**Briefing", "FINAL BRIEFING", "BRIEFING:"):
        if marker in t:
            t = t.split(marker, 1)[1].lstrip(":*# \n")
            break
    else:
        # if it opens with an analysis scaffold, drop those blocks
        if _re.match(r"^\s*\d+[\.\)]\s*\*{0,2}(Analyz|Analys|Draft|Understand|Review)", t):
            parts = _re.split(r"\n\s*\d+[\.\)]\s+", t)
            t = parts[-1].strip() if len(parts) > 1 else t
    # drop a leftover meta heading line ("**Drafting the Briefing:**", "**Final Answer:**", ...)
    t = _re.sub(r"^\s*\*{0,2}(Drafting|Analyz\w*|Analys\w*|Review|Final Answer|Plan)[^\n]*?:?\*{0,2}\s*\n+",
                "", t, flags=_re.I)
    # drop residual meta bullets that echo the system prompt back at the officer
    t = "\n".join(ln for ln in t.splitlines()
                  if not _re.match(r"^\s*\*+\s*\*{0,2}(Role|Input|Output|Constraints?|Header|Rules?)\b",
                                   ln, _re.I))
    return t.strip()


def _glm_chat(messages, max_tokens=500, temperature=0.2, timeout=20):
    """
    Call the Catalyst GLM-4.7-Flash chat endpoint (OpenAI-style request/response).
    Returns the assistant's text, or raises — the caller wraps this in try/except and falls back.
    """
    access = _get_access_token()
    if not access:
        raise RuntimeError("no access token (credentials missing or refresh failed)")
    body = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
        # GLM-4.7 is a REASONING model: with thinking enabled (the default) it emits its internal
        # chain-of-thought — "1. Analyze the Request... 2. Drafting the Briefing..." — and burns
        # the whole token budget narrating its plan instead of producing the briefing. It even
        # echoed our system prompt back. For an officer-facing briefing we want the ANSWER ONLY.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    headers = {
        "Content-Type": "application/json",
        "CATALYST-ORG": LLM_ORG_ID,
        "Authorization": f"Zoho-oauthtoken {access}",
    }
    req = urllib.request.Request(LLM_ENDPOINT, data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode())
    # The LIVE Catalyst GLM API returns {"response": "<text>", "tool_calls": [], "usage": {...}}.
    # (The published sample showed OpenAI-style choices[]; the deployed endpoint differs.) Handle
    # BOTH so we are robust to either shape.
    if isinstance(resp.get("response"), str) and resp["response"].strip():
        return _strip_reasoning(resp["response"])
    choices = resp.get("choices", [])
    if choices:
        return (choices[0].get("message", {}) or {}).get("content", "")
    raise ValueError(f"no text in GLM response: {str(resp)[:200]}")


# ═══════════════════════════════════════════════════════════════════════════
# 1. QuickML — LLM Serving.  GROUNDED narration.
# ═══════════════════════════════════════════════════════════════════════════
class GroundedNarrator:
    """
    Catalyst QuickML (LLM Serving) — used for PHRASING ONLY.

    THE ARCHITECTURAL POINT (this is the answer to "where is the AI?", and it is a better answer
    than "we let an LLM query the crime database"):

        The LLM NEVER retrieves facts and NEVER touches the database.
        The deterministic layer (graph + entity resolution + retrieval) produces FACTS WITH
        CITATIONS. The LLM is handed those facts and asked only to phrase them in fluent
        English/Kannada. It is forbidden to add anything.

        Then we VERIFY: every number and case ID in the LLM's output must appear in the facts we
        supplied. If the model invents a case number, a name, or a statistic, we DETECT it and fall
        back to the deterministic template.

    In a police system a hallucinated case number is a false accusation. So the LLM is on a leash,
    and the leash is enforced in code (see _hallucination_guard), not by prompt-wishing.
    """

    SYSTEM_PROMPT = (
        "You are KAVERI, an investigation assistant for the Karnataka State Police. "
        "You will be given VERIFIED FACTS extracted from FIR records. "
        "Rewrite them as a clear, professional briefing for a police officer. "
        "RULES: (1) Use ONLY the facts provided. (2) NEVER invent a case number, name, phone "
        "number, date or statistic. (3) Do not speculate about guilt. (4) Keep every case ID "
        "exactly as given. (5) Be concise. "
        "(6) OUTPUT THE BRIEFING ONLY. Do NOT show your reasoning, do NOT restate these rules, "
        "do NOT write headings like 'Analyze the Request' or 'Drafting the Briefing'. "
        "Begin directly with the briefing text."
    )

    def __init__(self, fallback_narrator=None):
        self.fallback = fallback_narrator

    def narrate(self, facts, citations, language="en"):
        """facts: dict of verified, cited findings. Returns (text, backend_used)."""
        if not LLM_ENABLED:
            BACKEND_LOG["narration"] = "local_template (GLM disabled)"
            return self._template(facts, citations, language), "local_template"

        try:
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content":
                    f"Language: {'Kannada' if language == 'kn' else 'English'}\n"
                    f"VERIFIED FACTS (use only these):\n"
                    f"{json.dumps(facts, ensure_ascii=False, indent=2)}\n"
                    f"CITATIONS: {citations}"},
            ]
            text = _glm_chat(messages, max_tokens=500, temperature=0.2)
            if not text or not text.strip():
                raise ValueError("empty completion")

            # THE LEASH: verify the model invented nothing before it reaches an officer.
            ok, problem = self._hallucination_guard(text, facts, citations)
            if not ok:
                BACKEND_LOG["narration"] = f"local_template (GLM output REJECTED: {problem})"
                return self._template(facts, citations, language), "template_after_llm_rejected"

            BACKEND_LOG["narration"] = "catalyst_glm"
            return text, "catalyst_glm"

        except Exception as e:
            # fail CLOSED to the deterministic path — never surface an LLM error to an officer
            BACKEND_LOG["narration"] = f"local_template (GLM unreachable: {type(e).__name__})"
            return self._template(facts, citations, language), "local_template_fallback"

    @staticmethod
    def _hallucination_guard(text, facts, citations):
        """
        Reject LLM output that misstates the record. Two classes of lie, both caught in CODE:

        (1) INVENTED CASE IDs — a case number we never supplied. The original guard.

        (2) INFLATED COUNTS — caught in PRODUCTION, and it is the more dangerous one.
            GLM wrote: "Ramesh Gowda is linked to 13 burglary cases (IDs: 2,3,4,5,7,10,13)".
            Count them — there are SEVEN. The "13" was the NEAR-REPEAT cluster size (13 burglaries
            within 400m/42 days), a GEOGRAPHIC statistic about the area, not a count of cases
            linked to that man. The model welded two unrelated facts together.

            Every individual ID it printed was legitimate, so the old ID-only guard passed it.
            But the sentence nearly DOUBLED an accused man's apparent criminal footprint —
            7 linked cases reported as 13. In a police briefing that is not a rounding error;
            that is the precise harm this system exists to prevent.

            So we now verify the CLAIM, not just the identifiers: any "linked to N cases" style
            assertion must match the number of cases we actually supplied.
        """
        import re
        allowed = {str(c) for c in (citations or [])}
        blob = json.dumps(facts, ensure_ascii=False)
        for n in re.findall(r'\b\d{1,6}\b', blob):
            allowed.add(n)

        # (1) invented case identifiers
        for n in re.findall(r'\bFIR\s*#?\s*(\d+)\b', text, re.IGNORECASE):
            if n not in allowed:
                return False, f"invented FIR number {n}"

        # (2) inflated linkage counts
        linked = facts.get("linked_cases") or []
        if linked:
            true_n = len(linked)
            # "linked to 13 cases", "linked to 13 burglary cases", "connected to 13 cases",
            # "13 linked cases", "associated with 13 cases"
            patterns = [
                r'(?:linked|connected|associated|tied)\s+(?:to|with)\s+(\d+)\s+\w*\s*cases?',
                r'\b(\d+)\s+(?:other\s+)?(?:linked|connected|associated)\s+cases?',
            ]
            for pat in patterns:
                for m in re.findall(pat, text, re.IGNORECASE):
                    claimed = int(m)
                    if claimed != true_n:
                        return False, (f"inflated linkage count: claimed {claimed} linked cases, "
                                       f"the record shows {true_n}")
        return True, None

    def _template(self, facts, citations, language):
        if self.fallback:
            return self.fallback(facts, citations, language)
        parts = [f"{k}: {v}" for k, v in facts.items() if v not in (None, [], {})]
        return " ".join(parts) + f"  [Sources: FIR {citations}]"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Zia Services — VOICE (the requirement we were missing entirely)
# ═══════════════════════════════════════════════════════════════════════════
class ZiaVoice:
    """
    Catalyst Zia Services — speech-to-text and text-to-speech.
    Challenge req 1: "Support Voice interaction for the Q&A" — an officer at a scene has their
    hands full; typing a query is not realistic. Kannada STT matters more than English here.
    """

    def speech_to_text(self, audio_b64, language="kn-IN"):
        """Returns (transcript, backend)."""
        if not CATALYST_ENABLED:
            BACKEND_LOG["stt"] = "unavailable (Catalyst disabled)"
            return None, "unavailable"
        try:
            resp = _post("/zia/v1/speechtotext",
                         {"audio": audio_b64, "language": language})
            BACKEND_LOG["stt"] = "catalyst_zia"
            return (resp.get("data", {}) or {}).get("text", ""), "catalyst_zia"
        except Exception as e:
            BACKEND_LOG["stt"] = f"unavailable ({type(e).__name__})"
            return None, "unavailable"

    def text_to_speech(self, text, language="kn-IN"):
        """Returns (audio_b64, backend)."""
        if not CATALYST_ENABLED:
            BACKEND_LOG["tts"] = "unavailable (Catalyst disabled)"
            return None, "unavailable"
        try:
            resp = _post("/zia/v1/texttospeech", {"text": text, "language": language})
            BACKEND_LOG["tts"] = "catalyst_zia"
            return (resp.get("data", {}) or {}).get("audio", ""), "catalyst_zia"
        except Exception as e:
            BACKEND_LOG["tts"] = f"unavailable ({type(e).__name__})"
            return None, "unavailable"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Catalyst Authentication — replaces the ?role= query parameter
# ═══════════════════════════════════════════════════════════════════════════
class CatalystAuth:
    """
    The prototype reads the officer's role from ?role= — which means ANYONE can claim ANY role.
    That is fine for a clickable demo and fatal in production, so we say so plainly rather than
    letting a judge discover it.

    In production the role arrives inside a signed JWT issued by Catalyst Authentication and is
    verified server-side. verify() below does that; when Catalyst is disabled it returns None and
    the caller falls back to the labelled prototype path.
    """

    def verify(self, authorization_header):
        """Returns a dict {user, role, station_id, district_id} or None."""
        if not CATALYST_ENABLED or not authorization_header:
            return None
        token = authorization_header.replace("Bearer ", "").strip()
        try:
            resp = _post("/authentication/validate", {"token": token})
            d = resp.get("data", {}) or {}
            BACKEND_LOG["auth"] = "catalyst_authentication"
            return {
                "user": d.get("email_id"),
                "role": (d.get("role_details") or {}).get("role_name"),
                "station_id": (d.get("user_details") or {}).get("station_id"),
                "district_id": (d.get("user_details") or {}).get("district_id"),
            }
        except Exception as e:
            BACKEND_LOG["auth"] = f"prototype_query_param ({type(e).__name__})"
            return None


# ═══════════════════════════════════════════════════════════════════════════
# 4. Catalyst NoSQL — durable, tamper-evident audit trail
# ═══════════════════════════════════════════════════════════════════════════
class CatalystAudit:
    """
    Req 10 demands "audit logs and traceability". Our hash-chained audit is currently IN MEMORY —
    it dies with the process, which is not an audit trail, it is a diary. Catalyst NoSQL persists
    it. The hash chain still makes tampering detectable; NoSQL makes it survive a restart.
    """

    def __init__(self, local_audit=None):
        self.local = local_audit

    def append(self, entry):
        if self.local:
            self.local.append(entry)              # keep the local hash chain regardless
        if not CATALYST_ENABLED:
            BACKEND_LOG["audit"] = "in_memory (Catalyst disabled — NOT durable)"
            return "in_memory"
        try:
            _post("/nosql/table/kaveri_audit/item",
                  {"item": {**entry, "ts": int(time.time())}})
            BACKEND_LOG["audit"] = "catalyst_nosql (durable)"
            return "catalyst_nosql"
        except Exception as e:
            BACKEND_LOG["audit"] = f"in_memory (NoSQL unreachable: {type(e).__name__})"
            return "in_memory_fallback"


def status():
    """Which backend is REALLY serving each capability. Surfaced at /health — no guessing."""
    return {
        "catalyst_enabled": CATALYST_ENABLED,
        "glm_configured": bool(LLM_CLIENT_ID and LLM_CLIENT_SECRET and LLM_REFRESH_TOKEN),
        "glm_model": LLM_MODEL if LLM_ENABLED else None,
        "project_id_set": bool(CATALYST_PROJECT_ID),
        "credentials_set": bool(LLM_CLIENT_ID and LLM_REFRESH_TOKEN),
        "backends_in_use": dict(BACKEND_LOG) or {"note": "no capability exercised yet"},
        "honesty_note": ("If catalyst_enabled is false, every capability below is served by the "
                         "LOCAL fallback. We report this rather than implying Catalyst is in use. "
                         "When true, narration is served by Catalyst GLM-4.7-Flash with a "
                         "hallucination guard; all other capabilities remain local unless noted."),
    }


if __name__ == "__main__":
    print("=== COMPONENT 16: CATALYST SERVICE INTEGRATION ===\n")
    print(f"CATALYST_ENABLED = {CATALYST_ENABLED}  (set env vars to activate)\n")

    print("--- GROUNDED NARRATION: the hallucination guard is the point ---")
    n = GroundedNarrator()
    facts = {"linked_cases": [2, 3, 4], "accused": "Ramesh Gowda", "shared_phone": "+919876543210"}
    text, backend = n.narrate(facts, citations=[1, 2, 3, 4])
    print(f"  backend: {backend}")
    print(f"  output : {text[:96]}...")
    print()
    print("  Now simulate an LLM that INVENTS a case number that was never in the facts:")
    ok, problem = GroundedNarrator._hallucination_guard(
        "The accused is linked to FIR 999 and FIR 2.", facts, [1, 2, 3, 4])
    print(f"    guard verdict: {'ACCEPTED' if ok else 'REJECTED — ' + problem}")
    print("    -> a fabricated FIR number in a police briefing is a false accusation.")
    print("       The guard catches it in CODE, not by asking the model nicely.")

    print("\n--- VOICE (Zia) — the requirement we were missing ---")
    v = ZiaVoice()
    t, b = v.speech_to_text("<audio>", language="kn-IN")
    print(f"  speech_to_text -> {b}  (activates when CATALYST_ENABLED=true)")

    print("\n--- AUTH ---")
    a = CatalystAuth()
    print(f"  verify(no token) -> {a.verify(None)}  (falls back to the LABELLED prototype path)")

    print("\n--- BACKEND TRANSPARENCY (exposed at /health) ---")
    print(json.dumps(status(), indent=2)[:420])


# ── Catalyst Data Store: DURABLE AUDIT PERSISTENCE (requirement 10.2) ──────────────────────
# The audit chain is hash-chained in memory (tamper-EVIDENT). That survives tampering but NOT a
# restart. For a police system the audit trail is the accountability record — "who asked what
# about whom" — and losing it on a redeploy is not acceptable. This writes every entry through
# to a Catalyst Data Store table so it is DURABLE as well as tamper-evident.
#
# FAIL-SAFE BY DESIGN: if the write fails, the entry is still kept in memory and the request
# still succeeds. An audit outage must never take down an investigation.
AUDIT_TABLE = os.getenv("KAVERI_AUDIT_TABLE", "kaveri_audit")
AUDIT_PERSIST = os.getenv("KAVERI_AUDIT_PERSIST", "false").lower() == "true"


def persist_audit(entry, timeout=8):
    """
    Write ONE audit entry to the Catalyst Data Store.

    API (confirmed against Catalyst docs):
        POST {api}/baas/v1/project/{project_id}/table/{table}/row
        Body: a JSON ARRAY of row objects  ->  [ {col: val, ...} ]

    NOTE ON SCOPE: this needs the OAuth scope ZohoCatalyst.tables.rows.CREATE. A token scoped
    only to QuickML.deployment.READ will 401 here — the refresh token must carry BOTH scopes.
    """
    if not AUDIT_PERSIST:
        BACKEND_LOG["audit"] = "in-memory only (KAVERI_AUDIT_PERSIST not enabled)"
        return None

    access = _get_access_token()
    if not access:
        BACKEND_LOG["audit"] = "in-memory (no access token)"
        raise RuntimeError("no access token for audit persistence")

    # Data Store columns are scalars — the case list is stored as a JSON string.
    row = {
        "seq":              entry.get("seq"),
        "ts":               entry.get("timestamp"),
        "actor":            entry.get("user"),
        "role":             entry.get("role"),
        "query_text":       (entry.get("query") or "")[:2000],
        "intent":           entry.get("intent"),
        "cases_touched":    json.dumps(entry.get("cases_touched", []))[:2000],
        "access_decision":  entry.get("access_decision"),
        "response_chars":   entry.get("response_chars"),
        "prev_hash":        entry.get("prev_hash"),
        "entry_hash":       entry.get("entry_hash"),
    }
    url = (f"https://api.catalyst.zoho.in/baas/v1/project/{CATALYST_PROJECT_ID}"
           f"/table/{AUDIT_TABLE}/row")
    headers = {
        "Content-Type": "application/json",
        "CATALYST-ORG": LLM_ORG_ID,
        "Authorization": f"Zoho-oauthtoken {access}",
    }
    req = urllib.request.Request(url, data=json.dumps([row]).encode(),   # ARRAY, per the API
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode())
    BACKEND_LOG["audit"] = "catalyst_datastore (durable + hash-chained)"
    return resp


def audit_status():
    """Reported at /health so the audit backend is never a guess."""
    return {
        "persist_enabled": AUDIT_PERSIST,
        "table": AUDIT_TABLE if AUDIT_PERSIST else None,
        "backend": BACKEND_LOG.get("audit", "in-memory hash chain (not yet exercised)"),
    }
