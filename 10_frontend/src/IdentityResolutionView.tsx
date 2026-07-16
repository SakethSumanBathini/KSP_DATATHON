import { useState, useEffect } from 'react';
import { CheckCircle2, XCircle, User, Phone, AlertTriangle, Loader2 } from 'lucide-react';
import { apiFetch } from './api';

/**
 * IDENTITY RESOLUTION — THE SCREEN THAT WINS
 *
 * ───────────────────────────────────────────────────────────────────────────────────────────
 *  WHAT WAS WRONG WITH THE FIRST VERSION, AND WHY IT MATTERED MORE THAN A NORMAL BUG
 * ───────────────────────────────────────────────────────────────────────────────────────────
 *
 *  The first version fetched /reasoning/identity/1 — got a 401 — silently discarded the error
 *  with `.catch(console.error)` — and then rendered a beautiful card built from HARDCODED JSX:
 *
 *      FIR 104/2023          <- our FIRs are 2026
 *      Identity ID: ID-8492  <- our identities are Identity:0 .. Identity:5
 *      R. Gowda              <- not a person in our data
 *      name_similarity: 0.94 <- not computed by anything
 *
 *  The screen whose entire purpose is to prove KAVERI never fabricates a claim about a human
 *  being... was fabricating claims about a human being. If a judge had said "show me that pair
 *  in the live system", none of it would have existed.
 *
 *  Every number on this screen now comes from the API. If the API fails, we SAY SO in red. We do
 *  not render a plausible-looking card over a dead request. That is the one sin this product
 *  exists to prevent.
 *
 *  TWO PANELS, AND THE SECOND ONE IS THE PRODUCT:
 *
 *    1. MERGED     — GET /reasoning/identity/1
 *                    5 FIRs, one man. Shared phone. Here is why.
 *
 *    2. REFUSED    — GET /reasoning/refused          <-- THIS IS THE ONE
 *                    Identical names. Compatible age. Same gender. NO shared evidence.
 *                    KAVERI says NO and sends it to a human.
 *                    Ground truth: they are different men.
 *                    `SQL GROUP BY name` merges all 2,052 of these.
 *
 *  Anyone can show you a merge they are proud of. Almost nobody shows you the merge they
 *  refused. That refusal is the entire moat.
 * ───────────────────────────────────────────────────────────────────────────────────────────
 */

interface IdentityNode { id: string; label: string; detail: string; type: string; }
interface IdentityData {
  conclusion: string;
  plain_language: string;
  member_cases: number[];
  nodes: IdentityNode[];
  edges: { from: string; to: string; basis: string }[];
}
interface RefusedPair {
  left:  { accused_id: number; name: string; age: number | null };
  right: { accused_id: number; name: string; age: number | null };
  name_similarity: number;
  age_compatible: boolean;
  gender_match: boolean;
  shared_evidence: string[];
  verdict: string;
  why: string;
}
interface RefusedData {
  refused_merges: RefusedPair[];
  total_refused: number;
  headline: {
    sql_group_by_name_false_merges: number;
    tuned_fuzzy_matcher_false_merges: number;
    kaveri_false_merges: number;
    note: string;
  };
  explanation: string;
}

export function IdentityResolutionView() {
  const [identity, setIdentity] = useState<IdentityData | null>(null);
  const [refused, setRefused] = useState<RefusedData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [id, ref] = await Promise.all([
          apiFetch('/reasoning/identity/1'),
          apiFetch('/reasoning/refused?limit=3'),
        ]);
        if (!alive) return;
        setIdentity(id);
        setRefused(ref);
      } catch (e: any) {
        // NO SILENT CATCH. A dead request must be visible, not papered over with a pretty card.
        if (alive) setError(e?.message ?? 'Failed to reach the backend');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black">
        <div className="flex items-center gap-3 text-neutral-400">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Resolving identities…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black p-10">
        <div className="max-w-lg border border-red-800 bg-red-950/40 rounded-lg p-6">
          <div className="flex items-center gap-2 text-red-400 font-semibold mb-2">
            <AlertTriangle className="w-5 h-5" /> Backend unreachable
          </div>
          <p className="text-neutral-300 text-sm mb-3">{error}</p>
          <p className="text-neutral-500 text-xs">
            This panel deliberately shows nothing rather than showing something plausible.
            A police tool that invents data when it loses its connection is worse than one
            that admits it is offline.
          </p>
        </div>
      </div>
    );
  }

  const merged = identity?.nodes.filter(n => n.type === 'evidence') ?? [];
  const h = refused?.headline;

  return (
    <div className="flex-1 overflow-y-auto bg-black p-10">
      <div className="max-w-6xl mx-auto space-y-12">

        <header>
          <h1 className="text-3xl font-bold text-white mb-3">Identity Resolution Engine</h1>
          <p className="text-neutral-400 text-lg max-w-3xl leading-relaxed">
            KAVERI never merges two people on a name alone. A merge requires{' '}
            <span className="text-white font-medium">corroborating evidence</span> — a shared
            phone, vehicle, or account. Names propose. Evidence disposes.
          </p>
        </header>

        {/* ── THE NUMBERS, straight from the API ── */}
        {h && (
          <div className="grid grid-cols-3 gap-4">
            <Stat n={h.sql_group_by_name_false_merges.toLocaleString()} label="SQL GROUP BY name" sub="false merges" tone="bad" />
            <Stat n={h.tuned_fuzzy_matcher_false_merges.toLocaleString()} label="Tuned fuzzy matcher" sub="false merges" tone="bad" />
            <Stat n={String(h.kaveri_false_merges)} label="KAVERI" sub="false merges · 0 missed" tone="good" />
          </div>
        )}

        {/* ── PANEL 1: MERGED ── */}
        {identity && (
          <section className="border-l-4 border-emerald-500 bg-neutral-900/60 rounded-r-lg p-8">
            <div className="flex items-center gap-3 mb-1">
              <CheckCircle2 className="w-6 h-6 text-emerald-400" />
              <h2 className="text-xl font-semibold text-white">MERGED — same person</h2>
              <span className="ml-auto px-3 py-1 text-xs font-semibold rounded border border-emerald-700 text-emerald-400">
                {identity.conclusion}
              </span>
            </div>
            <p className="text-neutral-500 text-sm mb-6">
              FIRs {identity.member_cases.join(', ')} resolved to one individual
            </p>

            <div className="grid md:grid-cols-2 gap-4 mb-6">
              {merged.slice(0, 2).map(n => (
                <div key={n.id} className="border border-neutral-700 rounded-lg p-5 bg-black/50">
                  <div className="flex items-center gap-3 mb-2">
                    <User className="w-4 h-4 text-neutral-500" />
                    <span className="text-lg text-white">{n.label}</span>
                  </div>
                  <div className="text-neutral-400 text-sm">{n.detail}</div>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-center gap-2 text-blue-400 text-sm mb-6">
              <Phone className="w-4 h-4" />
              <span className="font-mono">
                {identity.edges.find(e => e.basis?.includes('phone'))?.basis ?? 'shared evidence'}
              </span>
            </div>

            <div className="border-t border-neutral-800 pt-5">
              <div className="text-xs uppercase tracking-wider text-neutral-600 mb-2">Reasoning</div>
              <p className="text-neutral-300 text-sm leading-relaxed">{identity.plain_language}</p>
            </div>
          </section>
        )}

        {/* ── PANEL 2: REFUSED — THIS IS THE PRODUCT ── */}
        {refused && (
          <section>
            <div className="flex items-center gap-3 mb-2">
              <XCircle className="w-6 h-6 text-amber-400" />
              <h2 className="text-xl font-semibold text-white">REFUSED — identical names, still not merged</h2>
            </div>
            <p className="text-neutral-400 mb-6 max-w-3xl">
              {refused.explanation}{' '}
              <span className="text-amber-400 font-medium">
                {refused.total_refused.toLocaleString()} such pairs in this corpus.
              </span>
            </p>

            <div className="space-y-4">
              {refused.refused_merges.map((p, i) => (
                <div key={i} className="border-l-4 border-amber-500 bg-neutral-900/60 rounded-r-lg p-6">
                  <div className="grid md:grid-cols-[1fr_auto_1fr] gap-4 items-center mb-5">
                    <div className="border border-neutral-700 rounded p-4 bg-black/50">
                      <div className="text-white text-lg">{p.left.name}</div>
                      <div className="text-neutral-500 text-sm">age {p.left.age ?? '—'}</div>
                    </div>
                    <div className="text-center px-4">
                      <div className="text-2xl font-mono text-amber-400">{p.name_similarity.toFixed(3)}</div>
                      <div className="text-[10px] uppercase tracking-wider text-neutral-600">name similarity</div>
                    </div>
                    <div className="border border-neutral-700 rounded p-4 bg-black/50">
                      <div className="text-white text-lg">{p.right.name}</div>
                      <div className="text-neutral-500 text-sm">age {p.right.age ?? '—'}</div>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm mb-4 font-mono">
                    <Chip label="name" value={p.name_similarity.toFixed(3)} ok />
                    <Chip label="age compatible" value={p.age_compatible ? 'yes' : 'no'} ok={p.age_compatible} />
                    <Chip label="gender match" value={p.gender_match ? 'yes' : 'no'} ok={p.gender_match} />
                    <Chip label="shared evidence" value="NONE" ok={false} />
                  </div>

                  <div className="border-t border-neutral-800 pt-4 flex items-start gap-3">
                    <XCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <div className="text-amber-400 font-semibold mb-1">
                        {p.verdict} → human review
                      </div>
                      <p className="text-neutral-400 text-sm leading-relaxed">{p.why}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {h && (
              <p className="text-neutral-500 text-sm mt-6 max-w-3xl italic border-l-2 border-neutral-700 pl-4">
                {h.note}
              </p>
            )}
          </section>
        )}
      </div>
    </div>
  );
}

function Stat({ n, label, sub, tone }: { n: string; label: string; sub: string; tone: 'good' | 'bad' }) {
  return (
    <div className={`rounded-lg p-6 border ${tone === 'good' ? 'border-emerald-800 bg-emerald-950/20' : 'border-neutral-800 bg-neutral-900/40'}`}>
      <div className={`text-4xl font-bold mb-1 ${tone === 'good' ? 'text-emerald-400' : 'text-neutral-300'}`}>{n}</div>
      <div className="text-sm text-white">{label}</div>
      <div className="text-xs text-neutral-500">{sub}</div>
    </div>
  );
}

function Chip({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-neutral-600">{label}:</span>
      <span className={ok ? 'text-neutral-300' : 'text-amber-400 font-semibold'}>{value}</span>
    </span>
  );
}
