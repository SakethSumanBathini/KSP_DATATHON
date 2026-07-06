"""
Component 7a — LLM narration interface.

PRODUCTION: Catalyst QuickML served model (GLM-4.7 / Qwen — the lineup changes, so this is a
thin swappable wrapper). The orchestrator passes RETRIEVED, STRUCTURED facts + citations; the
LLM's job is to NARRATE them in plain language. It never invents connections — it phrases the
graph/retrieval output. This is the guardrail: the LLM narrates verified structure, nothing more.

HERE (verifiable stand-in): a deterministic template narrator that turns structured retrieval
results into readable prose. This lets us prove the ORCHESTRATION and CITATION logic end-to-end
WITHOUT a live model, and shows exactly what the LLM would be asked to phrase. In production the
same structured payload goes to the served model with a strict "narrate only these facts, cite
every claim" prompt. Interface identical -> one-line swap.
"""

class LLMNarrator:
    """Deterministic stand-in. Swap for Catalyst served-model call in production."""

    PRODUCTION_PROMPT_TEMPLATE = (
        "You are a police investigation assistant. Narrate ONLY the facts provided below in "
        "clear plain language for an investigating officer. Do NOT add, infer, or invent any "
        "connection not present in the facts. Every claim must reference its source FIR id. "
        "If evidence is weak, say so.\n\nFACTS:\n{facts}\n\nNARRATION:"
    )

    def narrate(self, intent, payload):
        """Turn structured retrieval payload into prose. (Template stand-in for the served LLM.)"""
        if intent == "similar_cases":
            lines = [f"Found {len(payload['results'])} cases with a similar modus operandi:"]
            for r in payload["results"]:
                lines.append(f"  • FIR {r['case_id']} (similarity {r['score']}): {r['brief'].strip()}…")
            lines.append("\nThese share operational characteristics and may involve related offenders. "
                         "Each is cited above for verification.")
            return "\n".join(lines)

        if intent == "network":
            n = payload["network"]
            lines = [f"Analysis of FIR {n['case_id']}:"]
            if n["linked_cases"]:
                lines.append(f"This case is connected to {len(n['linked_cases'])} other FIRs through "
                             f"shared physical evidence: {', '.join('FIR '+str(c) for c in n['linked_cases'])}.")
            if n["shared_phones"]:
                phones = sorted(set(p for p,_ in n["shared_phones"]))
                lines.append(f"Shared phone number(s): {', '.join(phones)} — appearing across multiple cases.")
            if n["shared_vehicles"]:
                vs = sorted(set(v for v,_ in n["shared_vehicles"]))
                lines.append(f"Shared vehicle(s): {', '.join(vs)}.")
            for a in n["accused"]:
                lines.append(f"Accused '{a['name']}' (resolved identity {a['identity']}).")
            lines.append("\nAll connections above are drawn from recorded FIR data and are cited. "
                         "A human officer should verify before action.")
            return "\n".join(lines)

        if intent == "identity_history":
            h = payload["history"]
            lines = [f"This individual (resolved identity {h['identity']}) appears in "
                     f"{h['member_count']} cases under different name spellings:"]
            for c in h["cases"]:
                lines.append(f"  • FIR {c['case_id']}: recorded as '{c['name']}'")
            lines.append("\nThese were linked by a shared distinguishing signal (e.g. a common phone/vehicle), "
                         "not by name alone. Name-only matches are flagged for human review, not asserted.")
            return "\n".join(lines)

        return "No narration template for this intent."


# ============================================================================
# GAP 3 — Production LLM narrator (Catalyst QuickML served model).
# Same narrate(intent, payload) interface as the template narrator, so the orchestrator
# is unchanged. Falls back to the template if the endpoint/credentials are unavailable, so
# the pipeline never breaks in dev/sandbox.
# ============================================================================
import os, json as _json

class CatalystLLMNarrator:
    """
    Production narrator. Sends the STRUCTURED, CITED facts to the Catalyst QuickML served model
    with a strict prompt that forbids inventing anything beyond the provided facts.

    Requires env vars (NEVER hardcode):
      CATALYST_LLM_ENDPOINT  — the served-model inference URL
      CATALYST_LLM_TOKEN     — auth token / API key
    """
    def __init__(self):
        self.endpoint = os.environ.get("CATALYST_LLM_ENDPOINT")
        self.token = os.environ.get("CATALYST_LLM_TOKEN")
        self.template_fallback = LLMNarrator()   # reuse the deterministic template as fallback
        self.available = bool(self.endpoint and self.token)

    def _facts_from_payload(self, intent, payload):
        """Serialize the retrieved payload into the FACTS block the model is allowed to narrate."""
        return _json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    def narrate(self, intent, payload):
        if not self.available:
            # No endpoint configured (dev/sandbox) -> deterministic template. Pipeline still works.
            return self.template_fallback.narrate(intent, payload)
        facts = self._facts_from_payload(intent, payload)
        prompt = LLMNarrator.PRODUCTION_PROMPT_TEMPLATE.format(facts=facts)
        try:
            import urllib.request
            body = _json.dumps({
                "prompt": prompt,
                "max_tokens": 400,
                "temperature": 0.2,   # low temp -> faithful narration, minimal embellishment
            }).encode()
            req = urllib.request.Request(
                self.endpoint,
                data=body,
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=25) as resp:  # under Catalyst 30s timeout
                out = _json.loads(resp.read().decode())
            # adapt to the served model's response shape (adjust key if your endpoint differs)
            text = out.get("output") or out.get("text") or out.get("choices",[{}])[0].get("text","")
            return text.strip() if text else self.template_fallback.narrate(intent, payload)
        except Exception as e:
            # any failure (timeout, auth, network) -> safe deterministic fallback, never crash
            print(f"[CatalystLLMNarrator] falling back to template ({type(e).__name__})")
            return self.template_fallback.narrate(intent, payload)


def get_narrator():
    """
    Factory: use the Catalyst served model if configured, else the deterministic template.
    The orchestrator calls this — one line, and it's production-ready when env vars are set.
    """
    n = CatalystLLMNarrator()
    return n if n.available else LLMNarrator()
