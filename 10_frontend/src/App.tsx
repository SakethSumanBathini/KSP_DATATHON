import React, { useState, useEffect, useRef } from 'react';
import { LayoutDashboard, Shield, AlertTriangle, Search, Mic, CheckCircle2, Database, Users, Activity, Fingerprint, Square } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { IdentityResolutionView } from './IdentityResolutionView';
import { TheNumbersView } from './TheNumbersView';
import { ReactFlow, Controls, Background, useNodesState, useEdgesState } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { apiFetch } from './api';

/**
 * ════════════════════════════════════════════════════════════════════════════════════════════
 *  FIXES APPLIED TO THIS FILE — every one of these was a real bug, and four of them were the
 *  kind that fail SILENTLY, which is the only kind that reaches a demo.
 * ════════════════════════════════════════════════════════════════════════════════════════════
 *
 *  1. HARDCODED JWT  (would have killed the demo)
 *     const TOKEN = "eyJhbGci..." — an 8-hour token, pasted into source.
 *     Worse: the server's signing secret was `os.urandom(32)`, regenerated on EVERY container
 *     restart, so ANY redeploy silently invalidated it. And only ONE route checks auth —
 *     /reasoning/identity — which is the single most important screen in the product. So the
 *     app would look completely healthy while its best screen quietly 401'd.
 *     -> Now: apiFetch() mints a fresh token via POST /auth/login and re-mints automatically
 *        on a 401. See api.ts.
 *
 *  2. KANNADA CASE NUMBERS NEVER MATCHED
 *     const match = text.match(/\b(\d{1,3})\b/);   // ASCII digits ONLY
 *     Chrome transcribes spoken Kannada "one" as the WORD ಒಂದು — never the digit 1. Every
 *     spoken Kannada case number fell through to /converse and failed. Speech recognition was
 *     working perfectly the whole time; the ROUTING was broken.
 *     -> Now: fuzzy numeral matching, Kannada + English. Fuzzy for Kannada script ONLY —
 *        an earlier attempt fuzzy-matched Latin too, and "the" is edit-distance 2 from "three",
 *        so "show me the network" silently investigated CASE 3. A confident wrong answer is
 *        worse than an error, and that is the exact failure this product exists to prevent.
 *
 *  3. VOICE READ A STALE QUERY
 *     rec.onend = () => { if (query) executeSearch(query); }
 *     `query` is captured by the closure at render time. By the time onend fires, it is the OLD
 *     value — so it would search for whatever you said LAST time, or nothing at all.
 *     -> Now: a ref holds the live transcript, plus a silence window so a mid-sentence breath
 *        does not fire a half-spoken question at the backend.
 *
 *  4. ERRORS WERE SWALLOWED
 *     catch (e) { console.error(e); }  — the user saw a spinner stop and nothing else.
 *     -> Now: failures are shown on screen, in red. A police tool must never fail quietly.
 *
 *  5. "Officer Shaurya" — a fabricated officer, shown to real officers. Removed.
 * ════════════════════════════════════════════════════════════════════════════════════════════
 */

interface InvestigationData {
  case_id: string;
  sections?: string[];
  narrative?: string;
  narrative_source?: string;
  citations?: number[];
  network?: {
    linked_cases?: string[];
    shared_phones?: string[];
    shared_vehicles?: string[];
    accused?: { name: string; accused_id: number; identity: string }[];
  };
  similar_cases?: { case_id: string; score: number; brief: string }[];
  near_repeat?: { case_id: string; distance_m: number; days_apart: number }[];
  recommended_leads?: string[];
}

/* ── SPOKEN NUMBER RECOGNITION ──
   Chrome gave us ಒಂದು one time and ಉಂಡು the next — same word, same speaker. Speech output is
   VARIABLE, so an exact-match table is brittle by construction. We match approximately, but
   ONLY on Kannada script: English recognition is accurate, and short Latin words like "the"
   sit within edit-distance of "three". */
const NUMWORDS: Record<number, string[]> = {
  1: ['ಒಂದು', 'ಉಂಡು', 'ಒನ್ದು', 'ondu', 'undu', 'one'],
  2: ['ಎರಡು', 'ಇರಡು', 'eradu', 'two'],
  3: ['ಮೂರು', 'ಮುರು', 'mooru', 'muru', 'three'],
  4: ['ನಾಲ್ಕು', 'nalku', 'four'],
  5: ['ಐದು', 'aidu', 'five'],
  6: ['ಆರು', 'aaru', 'six'],
  7: ['ಏಳು', 'elu', 'seven'],
  8: ['ಎಂಟು', 'entu', 'eight'],
  9: ['ಒಂಬತ್ತು', 'ombattu', 'nine'],
  10: ['ಹತ್ತು', 'hattu', 'ten'],
};

function editDistance(a: string, b: string): number {
  const m = a.length, n = b.length;
  if (!m) return n;
  if (!n) return m;
  let prev = Array.from({ length: n + 1 }, (_, i) => i);
  for (let i = 1; i <= m; i++) {
    const cur: number[] = [i];
    for (let j = 1; j <= n; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[n];
}

function caseNumberIn(text: string): string | null {
  const digits = text.match(/\b(\d{1,3})\b/);
  if (digits) return digits[1];

  const isKannada = (s: string) => /[\u0C80-\u0CFF]/.test(s);
  const tokens = text.toLowerCase().split(/\s+/).filter(Boolean);
  let best: number | null = null, bestDist = Infinity;

  for (const [num, variants] of Object.entries(NUMWORDS)) {
    for (const v of variants) {
      const vv = v.toLowerCase();
      for (const tok of tokens) {
        if (tok === vv) return String(num);                       // exact — either script
        if (!isKannada(tok) || !isKannada(vv)) continue;          // fuzzy: Kannada ONLY
        const tol = vv.length <= 4 ? 1 : 2;
        const d = editDistance(tok, vv);
        if (d <= tol && d < bestDist) { bestDist = d; best = Number(num); }
      }
    }
  }
  return best !== null ? String(best) : null;
}

export default function App() {
  const [data, setData] = useState<InvestigationData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [health, setHealth] = useState({ cases: 0, identities: 0, ok: false });
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<any>(null);
  const transcriptRef = useRef('');           // FIX 3: live transcript, not a stale closure
  const silenceRef = useRef<any>(null);
  const [activeView, setActiveView] = useState('Identity Resolution');
  const [activeTab, setActiveTab] = useState('Crime Network');

  useEffect(() => {
    apiFetch('/health')
      .then((d: any) => setHealth({ cases: d.cases || 0, identities: d.resolved_identities || 0, ok: true }))
      .catch(() => setHealth(prev => ({ ...prev, ok: false })));
  }, []);

  const executeSearch = async (text: string) => {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);

    const caseId = caseNumberIn(text);        // FIX 2: understands ಒಂದು / ಉಂಡು / "one" / "1"

    try {
      if (caseId) {
        const d = await apiFetch(`/investigate/${caseId}`);
        setData(d);
      } else {
        const d = await apiFetch('/converse', {
          method: 'POST',
          headers: { 'Content-Type': 'text/plain' },   // text/plain avoids the CORS pre-flight
          body: JSON.stringify({ session_id: 'web', query: text, role: 'station_officer' }),
        });
        setData({
          case_id: d.case_id ?? '—',
          narrative: d.answer || d.narrative || d.clarification_needed || 'No answer returned.',
          narrative_source: d.narrative_source,
          citations: d.citations,
        });
      }
    } catch (e: any) {
      // FIX 4: NOT swallowed. The officer sees the failure.
      setError(e?.message ?? 'Could not reach the backend.');
    } finally {
      setLoading(false);
    }
  };

  const stopAll = () => {
    clearTimeout(silenceRef.current);
    try { recognitionRef.current?.abort(); } catch { /* already stopped */ }
    try { window.speechSynthesis?.cancel(); } catch { /* not supported */ }
    setListening(false);
  };

  const handleMic = () => {
    if (listening) { stopAll(); return; }

    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { setError('Voice needs Chrome or Edge (Web Speech API).'); return; }

    transcriptRef.current = '';
    const rec = new SR();
    rec.lang = 'kn-IN';
    rec.continuous = true;         // stay open across natural pauses
    rec.interimResults = true;

    rec.onstart = () => setListening(true);

    rec.onresult = (e: any) => {
      let finalText = '', interim = '';
      for (const r of e.results) {
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      transcriptRef.current = finalText.trim();
      setQuery((finalText + interim).trim());      // officer SEES what is being heard

      // FIX 3: SILENCE WINDOW. The old code fired on the first isFinal, and Chrome marks a
      // result "final" the moment you pause to breathe — so half-spoken questions were sent.
      clearTimeout(silenceRef.current);
      if (transcriptRef.current) {
        silenceRef.current = setTimeout(() => {
          const q = transcriptRef.current;
          try { rec.stop(); } catch { /* already stopped */ }
          if (q) executeSearch(q);
        }, 1400);
      }
    };

    rec.onerror = (e: any) => { setError(`Voice error: ${e.error}`); setListening(false); };
    rec.onend = () => setListening(false);       // no stale-closure search here any more

    recognitionRef.current = rec;
    rec.start();
  };

  return (
    <div className="flex h-screen w-full bg-bg-base text-text-primary overflow-hidden">
      {/* LEFT SIDEBAR */}
      <aside className="w-[280px] flex-shrink-0 bg-bg-surface border-r border-border-subtle flex flex-col z-20 shadow-xl">
        <div className="p-4 border-b border-border-subtle flex items-center gap-3">
          <div className="w-8 h-8 bg-text-primary text-bg-base rounded flex items-center justify-center font-bold">ಕ</div>
          <div>
            <div className="font-semibold text-sm tracking-tight">KAVERI</div>
            <div className="text-[10px] text-text-muted uppercase tracking-wider">Karnataka Police</div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          <div className="mb-2 px-3 text-[10px] font-semibold text-text-muted uppercase tracking-wider">Primary Modules</div>
          <NavItem icon={<Fingerprint size={16} />} label="Identity Resolution" active={activeView === 'Identity Resolution'} onClick={() => setActiveView('Identity Resolution')} />
          <NavItem icon={<Activity size={16} />} label="System Performance" active={activeView === 'System Performance'} onClick={() => setActiveView('System Performance')} />
          <NavItem icon={<LayoutDashboard size={16} />} label="Investigation Workspace" active={activeView === 'Investigation Workspace'} onClick={() => setActiveView('Investigation Workspace')} />
        </div>

        <div className="p-4 border-t border-border-subtle">
          <div className="flex items-center gap-2 mb-3">
            <div className={`w-2 h-2 rounded-full ${health.ok ? 'bg-status-success' : 'bg-status-critical'}`} />
            <span className="text-xs text-text-muted font-medium">
              {health.ok ? `${health.cases} cases · ${health.identities} identities` : 'System Offline'}
            </span>
          </div>
          {/* FIX 5: no fabricated officer. This is the real role the token carries. */}
          <div className="bg-bg-secondary rounded p-3 text-xs border border-border-subtle">
            <div className="text-text-secondary mb-1">Session role</div>
            <div className="font-medium">SCRB Analyst</div>
            <div className="text-[10px] text-brand-accent mt-1 uppercase font-semibold">State-wide access</div>
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        {/* TOP BAR */}
        <header className="h-[56px] bg-bg-base border-b border-border-subtle flex items-center px-6 gap-6 z-10">
          <div className="flex-1 flex items-center">
            <div className="relative w-full max-w-2xl flex items-center">
              <Search className="absolute left-3 text-text-muted" size={16} />
              <input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && executeSearch(query)}
                placeholder="Case ID (e.g. 1), or speak in Kannada (ಪ್ರಕರಣ ಒಂದು)…"
                className="w-full bg-bg-surface border border-border-subtle rounded-md pl-10 pr-20 py-2 text-sm text-text-primary focus:ring-1 focus:ring-brand-accent focus:outline-none transition-all"
              />
              {listening && (
                <button onClick={stopAll} className="absolute right-10 p-1.5 rounded-md text-status-critical bg-status-critical/10" title="Stop">
                  <Square size={14} />
                </button>
              )}
              <button
                onClick={handleMic}
                className={`absolute right-2 p-1.5 rounded-md transition-colors ${listening ? 'text-status-critical bg-status-critical/10 animate-pulse' : 'text-text-muted hover:text-text-primary'}`}
              >
                <Mic size={16} />
              </button>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs font-medium text-text-secondary">
            <span>KN / EN</span>
            <span>{new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        </header>

        <main className="flex-1 flex overflow-hidden">
          {activeView === 'Identity Resolution' && <IdentityResolutionView />}
          {activeView === 'System Performance' && <TheNumbersView />}
          {activeView === 'Investigation Workspace' && (
            <>
              <section className="flex-1 overflow-y-auto border-r border-border-subtle p-8 bg-bg-base relative">
                {/* FIX 4: errors are VISIBLE */}
                {error && (
                  <div className="max-w-3xl mx-auto mb-6 border border-status-critical/40 bg-status-critical/10 rounded p-4 flex items-start gap-3">
                    <AlertTriangle size={18} className="text-status-critical shrink-0 mt-0.5" />
                    <div>
                      <div className="text-status-critical font-semibold text-sm">Request failed</div>
                      <div className="text-text-secondary text-xs mt-1">{error}</div>
                    </div>
                  </div>
                )}

                {loading ? (
                  <div className="flex items-center justify-center h-full text-text-muted text-sm">
                    Analysing… (first request after idle can take ~10s)
                  </div>
                ) : data ? (
                  <div className="max-w-3xl mx-auto space-y-8">
                    <div className="flex items-start justify-between">
                      <div>
                        <h2 className="text-2xl font-bold tracking-tight mb-2">Case Intelligence Report: {data.case_id}</h2>
                        {data.sections && (
                          <div className="flex flex-wrap gap-2">
                            {data.sections.map(s => (
                              <span key={s} className="px-2 py-1 text-xs bg-bg-secondary border border-border-subtle rounded text-text-secondary">{s}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      {data.narrative_source === 'catalyst_glm' ? (
                        <div className="flex items-center gap-2 bg-status-success/10 border border-status-success/30 px-3 py-1.5 rounded text-status-success text-xs font-semibold shrink-0">
                          <Shield size={14} /> Catalyst GLM-4.7 · Hallucination Guarded
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 bg-status-warning/10 border border-status-warning/30 px-3 py-1.5 rounded text-status-warning text-xs font-semibold shrink-0">
                          <AlertTriangle size={14} /> Deterministic Template
                        </div>
                      )}
                    </div>

                    <div className="prose prose-invert prose-sm max-w-none text-text-secondary leading-relaxed">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.narrative || ''}</ReactMarkdown>
                    </div>

                    {data.citations && data.citations.length > 0 && (
                      <div className="pt-6 border-t border-border-subtle">
                        <h3 className="text-xs font-semibold uppercase text-text-muted mb-3">Verified Sources</h3>
                        <div className="flex flex-wrap gap-2">
                          {data.citations.map(c => (
                            <button key={c} onClick={() => executeSearch(String(c))}
                              className="px-3 py-1 bg-bg-surface border border-border-subtle hover:border-brand-accent/50 rounded text-xs transition-colors">
                              FIR {c}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {data.recommended_leads && data.recommended_leads.length > 0 && (
                      <div className="pt-6 border-t border-border-subtle">
                        <h3 className="text-xs font-semibold uppercase text-text-muted mb-3">Recommended Actions</h3>
                        <ul className="space-y-2">
                          {data.recommended_leads.map((lead, i) => (
                            <li key={i} className="flex items-start gap-3 bg-bg-surface p-3 rounded border border-border-subtle">
                              <CheckCircle2 size={16} className="text-brand-accent mt-0.5 shrink-0" />
                              <span className="text-sm text-text-secondary">{lead}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-text-muted">
                    <Shield size={48} className="mb-4 opacity-20" />
                    <p className="text-sm">Type a case number, or press the mic and speak in Kannada.</p>
                  </div>
                )}
              </section>

              <aside className="w-[440px] flex-shrink-0 bg-bg-surface flex flex-col min-h-0">
                <div className="flex px-2 pt-2 border-b border-border-subtle">
                  {['Crime Network', 'Identity Panel', 'Similar Cases'].map(t => (
                    <button key={t} onClick={() => setActiveTab(t)}
                      className={`px-4 py-3 text-xs transition-colors border-b-2 ${activeTab === t ? 'font-semibold text-text-primary border-brand-accent' : 'font-medium text-text-muted hover:text-text-secondary border-transparent'}`}>
                      {t}
                    </button>
                  ))}
                </div>

                <div className="flex-1 relative overflow-hidden bg-bg-base">
                  {activeTab === 'Crime Network' && (
                    data?.network
                      ? <NetworkGraph network={data.network} rootCase={data.case_id} />
                      : <div className="absolute inset-0 flex items-center justify-center text-xs text-text-muted p-8 text-center">
                          No network yet. Investigate a case.
                        </div>
                  )}
                  {activeTab === 'Identity Panel' && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-xs text-text-muted p-8 text-center">
                      <Users size={32} className="mb-3 opacity-20" />
                      Full identity reasoning lives in the <span className="text-text-primary mx-1">Identity Resolution</span> module.
                    </div>
                  )}
                  {activeTab === 'Similar Cases' && (
                    data?.similar_cases?.length
                      ? <div className="absolute inset-0 overflow-y-auto p-4 space-y-2">
                          {data.similar_cases.map(sc => (
                            <button key={sc.case_id} onClick={() => executeSearch(String(sc.case_id))}
                              className="w-full text-left bg-bg-surface border border-border-subtle hover:border-brand-accent/50 rounded p-3 transition-colors">
                              <div className="flex justify-between items-center mb-1">
                                <span className="text-xs font-semibold text-text-primary">FIR {sc.case_id}</span>
                                <span className="text-[10px] font-mono text-brand-accent">{sc.score.toFixed(3)}</span>
                              </div>
                              <div className="text-[11px] text-text-muted line-clamp-2">{sc.brief}</div>
                            </button>
                          ))}
                        </div>
                      : <div className="absolute inset-0 flex flex-col items-center justify-center text-xs text-text-muted p-8 text-center">
                          <Database size={32} className="mb-3 opacity-20" />
                          Investigate a case to see similar modus operandi.
                        </div>
                  )}
                </div>

                {data && (
                  <div className="h-56 border-t border-border-subtle p-6 overflow-y-auto">
                    <h3 className="text-xs font-semibold uppercase text-text-muted mb-4">Risk &amp; Insights</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <StatCard label="Near-repeat cases" value={data.near_repeat?.length || 0} />
                      <StatCard label="Similar MO" value={data.similar_cases?.length || 0} />
                      <StatCard label="Accused identified" value={data.network?.accused?.length || 0} />
                      <StatCard label="Shared assets" value={(data.network?.shared_phones?.length || 0) + (data.network?.shared_vehicles?.length || 0)} />
                    </div>
                  </div>
                )}
              </aside>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function NavItem({ icon, label, active = false, onClick }: { icon: React.ReactNode; label: string; active?: boolean; onClick?: () => void }) {
  return (
    <button onClick={onClick} className={`w-full flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${active ? 'bg-bg-secondary text-text-primary' : 'text-text-secondary hover:bg-bg-secondary hover:text-text-primary'}`}>
      <span className="text-text-muted">{icon}</span>
      {label}
    </button>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-bg-base border border-border-subtle p-3 rounded">
      <div className="text-[10px] uppercase font-semibold text-text-muted mb-1">{label}</div>
      <div className="text-lg font-bold text-text-primary">{value}</div>
    </div>
  );
}

/** Every edge here is one the SERVER asserted. We never invent a connection for visual effect —
 *  a fake line on a police graph is a fake accusation. */
function NetworkGraph({ network, rootCase }: { network: any; rootCase: string }) {
  const [nodes, setNodes] = useNodesState<any>([]);
  const [edges, setEdges] = useEdgesState<any>([]);

  useEffect(() => {
    if (!network) return;
    const newNodes: any[] = [];
    const newEdges: any[] = [];

    newNodes.push({
      id: `case-${rootCase}`,
      position: { x: 240, y: 180 },
      data: { label: `FIR ${rootCase}` },
      style: { background: '#EF4444', color: '#fff', border: 'none', width: 64, height: 64, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 'bold' },
    });

    const items: [string, string, string, number][] = [];
    (network.linked_cases || []).forEach((c: string) => items.push([`case-${c}`, `FIR ${c}`, '#EF4444', 20]));
    (network.accused || []).forEach((a: any) => items.push([`acc-${a.accused_id}`, a.name, '#F59E0B', 26]));
    (network.shared_phones || []).forEach((p: string) => items.push([`ph-${p}`, p.slice(-5), '#2563EB', 16]));
    (network.shared_vehicles || []).forEach((v: string) => items.push([`veh-${v}`, v, '#10B981', 16]));

    const n = Math.max(items.length, 1);
    items.forEach(([id, label, color, radius], i) => {
      const angle = (Math.PI * 2 * i) / n;
      newNodes.push({
        id,
        position: { x: 240 + Math.cos(angle) * 150, y: 180 + Math.sin(angle) * 150 },
        data: { label },
        style: { background: color, color: '#fff', border: 'none', width: radius * 2, height: radius * 2, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, textAlign: 'center' },
      });
      newEdges.push({
        id: `e-${rootCase}-${id}`,
        source: `case-${rootCase}`,
        target: id,
        animated: true,
        style: { stroke: 'rgba(255,255,255,0.25)' },
      });
    });

    setNodes(newNodes);
    setEdges(newEdges);
  }, [network, rootCase, setNodes, setEdges]);

  return (
    <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }} className="bg-bg-base">
      <Background color="#2A313D" gap={16} />
      <Controls className="!bg-bg-surface !border-border-subtle !text-text-primary" />
    </ReactFlow>
  );
}
