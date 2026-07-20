export const API_BASE = "https://kaveri-backend-50043711203.development.catalystappsail.in";

/**
 * CATALYST'S ZGS GATEWAY REJECTS CORS PREFLIGHT (OPTIONS) BEFORE IT REACHES FLASK.
 *
 * A browser sends a preflight OPTIONS whenever a cross-origin request is "non-simple" — which is
 * triggered by (a) an Authorization header, or (b) a Content-Type the browser doesn't consider
 * simple, such as application/json. Catalyst AppSail's front-door proxy (Server: ZGS) answers that
 * OPTIONS itself with INVALID_REQUEST_METHOD, so our Flask CORS headers never run and every call
 * dies as "Failed to fetch" — even though curl/PowerShell (which don't preflight) get 200.
 *
 * The fix is to make EVERY request "simple", so no preflight is ever emitted:
 *   1. Login POST uses Content-Type: text/plain  (a CORS-simple type) instead of application/json.
 *      The body is still JSON text; Flask reads it with get_json(force=True), which ignores the
 *      declared type. No preflight.
 *   2. Data calls carry the token as ?token=<t> in the URL, NOT as an Authorization header. The
 *      backend's _caller() already accepts ?token= as a fallback (browser-clickable demo links),
 *      so this is fully supported. No auth header => no preflight.
 *
 * This is exactly how the original working frontend authenticated. The rewrite had switched to
 * Bearer + JSON, which is cleaner in theory but preflights, which ZGS blocks.
 */

let currentToken: string | null = null;

export async function getToken(forceRefresh = false): Promise<string> {
  if (currentToken && !forceRefresh) {
    return currentToken;
  }

  // text/plain keeps this a CORS-simple request => no preflight => ZGS lets it through.
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: JSON.stringify({ kgid: 'demo_user', role: 'scrb_analyst' }),  // state-wide role the UI needs (sidebar says SCRB Analyst)
  });

  if (!res.ok) {
    throw new Error('Failed to authenticate');
  }

  const data = await res.json();
  currentToken = data.token || data.access_token; // backend returns { token: ... }
  return currentToken as string;
}

/**
 * A token-signed absolute URL, for things the browser must fetch itself rather than through
 * apiFetch — a PDF download is one: we want the browser's own save dialog, not a blob in memory.
 */
export async function signedUrl(endpoint: string): Promise<string> {
  const t = await getToken();
  const base = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  const sep = base.includes('?') ? '&' : '?';
  return `${base}${sep}token=${encodeURIComponent(t)}`;
}

export async function apiFetch(endpoint: string, options: RequestInit = {}): Promise<any> {
  let token = await getToken();

  const withToken = (t: string) => {
    const base = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
    const sep = base.includes('?') ? '&' : '?';
    return `${base}${sep}token=${encodeURIComponent(t)}`;
  };

  // No Authorization header, no application/json — the token rides in the URL, so the request
  // stays CORS-simple and never preflights.
  let res = await fetch(withToken(token), options);

  // token stale (server restarted with a new secret) -> mint a fresh one and retry ONCE
  if (res.status === 401) {
    token = await getToken(true);
    res = await fetch(withToken(token), options);
  }

  // AN ETHICAL REFUSAL IS AN ANSWER, NOT A TRANSPORT FAILURE.
  //
  // The guard returns 403 with the reason in the body. Treating every non-2xx as an exception
  // turned the single most deliberate thing this system does — refusing to profile by caste —
  // into "API Error: 403" on screen. To an officer that reads as a broken tool, not a principled
  // one. We surface the refusal so the UI can say what happened and why.
  //
  // Narrow on purpose: an ethical refusal carries `allowed:false` with a reason. A jurisdiction
  // denial carries `access_denied:true` and must stay an error — it IS a failure to authorise.
  if (res.status === 403) {
    const body = await res.json().catch(() => null);
    if (body && body.allowed === false && (body.refused || body.answer)) {
      return { ...body, __refusal: true };
    }
    throw new Error(`API Error: ${res.status} ${res.statusText}`);
  }

  if (!res.ok) {
    throw new Error(`API Error: ${res.status} ${res.statusText}`);
  }

  return res.json();
}
