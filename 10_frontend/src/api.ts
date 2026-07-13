/**
 * KAVERI API CLIENT
 *
 * ─────────────────────────────────────────────────────────────────────────────
 *  WHY THIS FILE EXISTS — a bug that would have killed the live demo
 * ─────────────────────────────────────────────────────────────────────────────
 *
 *  The first version hardcoded a JWT:
 *
 *      const TOKEN = "eyJhbGciOiJIUzI1NiIs...";
 *
 *  That token had TWO independent death clocks:
 *
 *    1. It expires 8 hours after it was minted. Fine today. Dead tomorrow.
 *
 *    2. WORSE — the server's signing secret is regenerated on every container
 *       restart:
 *
 *           JWT_SECRET = os.getenv("KAVERI_JWT_SECRET")
 *                        or base64(os.urandom(32))     <-- RANDOM
 *
 *       So ANY `catalyst deploy` silently invalidates every previously issued
 *       token. The hardcoded one is dead the moment the backend is redeployed.
 *
 *  And the failure is SILENT. /reasoning/identity/:id returns 401, the code does
 *  `if (d.plain_language) setReasoning(...)`, the field is missing, nothing is set,
 *  no error is thrown. The Identity screen renders perfectly — minus the single
 *  paragraph that is the entire point of the product. In front of judges you would
 *  not know anything was wrong.
 *
 *  THE FIX (both halves are required):
 *
 *    A. Backend: set KAVERI_JWT_SECRET in the Catalyst console so the signing key
 *       survives restarts. Without this, NOTHING can hold a token across a deploy.
 *
 *    B. Frontend (this file): mint a FRESH token at startup via POST /auth/login.
 *       Never hardcode one. Re-mint automatically on 401.
 *
 *  Note which routes actually need auth — measured, not assumed:
 *      GET  /health                 -> 200 without a token
 *      GET  /investigate/:id        -> 200 without a token
 *      POST /converse               -> 200 without a token
 *      GET  /reasoning/identity/:id -> 401 WITHOUT A TOKEN   <-- the one that matters
 *
 *  It is exactly the most important screen that is gated. That is why this broke
 *  quietly instead of loudly.
 * ─────────────────────────────────────────────────────────────────────────────
 */

export const API =
  "https://kaveri-backend-50043711203.development.catalystappsail.in";

let token: string | null = null;
let inflight: Promise<string | null> | null = null;

/** Mint a fresh token. Cached for the session; re-minted automatically on 401. */
export async function getToken(): Promise<string | null> {
  if (token) return token;
  if (inflight) return inflight;

  inflight = (async () => {
    try {
      // text/plain avoids the CORS pre-flight. The backend uses get_json(force=True),
      // so it parses the body regardless of Content-Type. A POST with
      // application/json triggers an OPTIONS pre-flight that fails on this host.
      const r = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "text/plain" },
        body: JSON.stringify({
          kgid: "DEMO-SCRB",
          role: "scrb_analyst", // sees all 500 cases (station_officer sees 30)
        }),
      });
      if (!r.ok) {
        console.error("[KAVERI] /auth/login failed:", r.status);
        return null;
      }
      const d = await r.json();
      token = d.token ?? d.access_token ?? null;
      if (!token) console.error("[KAVERI] /auth/login returned no token:", d);
      return token;
    } catch (e) {
      console.error("[KAVERI] /auth/login threw:", e);
      return null;
    } finally {
      inflight = null;
    }
  })();

  return inflight;
}

/**
 * Fetch with auth. Throws on failure — DO NOT swallow it.
 * Silent catches are why the Identity screen failed invisibly in the first place.
 */
export async function apiFetch(path: string, init?: RequestInit): Promise<any> {
  const t = await getToken();
  const sep = path.includes("?") ? "&" : "?";
  const url = `${API}${path}${t ? `${sep}token=${t}` : ""}`;

  let r = await fetch(url, init);

  // token expired or server restarted with a new secret -> mint a new one, retry ONCE
  if (r.status === 401) {
    console.warn("[KAVERI] 401 — token stale (server restart?), re-minting…");
    token = null;
    const t2 = await getToken();
    if (t2) r = await fetch(`${API}${path}${sep}token=${t2}`, init);
  }

  if (!r.ok) {
    throw new Error(`${path} -> HTTP ${r.status}`);
  }
  return r.json();
}
