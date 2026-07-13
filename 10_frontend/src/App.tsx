import React, { useState, useEffect, useRef } from 'react';
import { LayoutDashboard, Shield, AlertTriangle, Search, Mic, CheckCircle2, Database, Users, Activity, Fingerprint, Square, CornerDownLeft, Volume2 } from 'lucide-react';
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
  const currentCase = useRef<number | null>(null);   // the case the officer is LOOKING at
  const [people, setPeople] = useState<any[] | null>(null);   // name-search results
  const [speaking, setSpeaking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);   // informational, NOT an error
  const fallbackEn = useRef<string>('');                        // English text for TTS fallback
  const declaredLang = useRef<string | null>(null);            // language the BACKEND declared
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [health, setHealth] = useState({ cases: 0, identities: 0, ok: false });
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<any>(null);
  const transcriptRef = useRef('');           // FIX 3: live transcript, not a stale closure
  const silenceRef = useRef<any>(null);
  const [lang, setLang] = useState<'kn-IN' | 'en-IN'>('en-IN');   // BUG 2/3: was hardcoded kn-IN
  const [activeView, setActiveView] = useState('Identity Resolution');
  const [activeTab, setActiveTab] = useState('Crime Network');

  useEffect(() => {
    apiFetch('/health')
      .then((d: any) => setHealth({ cases: d.cases || 0, identities: d.resolved_identities || 0, ok: true }))
      .catch(() => setHealth(prev => ({ ...prev, ok: false })));
  }, []);

  const executeSearch = async (text: string) => {
    if (!text.trim()) return;

    // BUG 1 — THE SEARCH WORKED AND YOU COULD NOT SEE IT.
    // The search box lives in the header, so it is visible on EVERY tab. But the result renders
    // only inside the Investigation Workspace. Typing "1" on the Identity Resolution tab fetched
    // the case correctly, set state correctly, and painted it into a view nobody was looking at.
    // It looked exactly like "Enter does nothing". A silent SUCCESS is as dangerous as a silent
    // failure — both leave the officer with no idea what the machine just did.
    setActiveView('Investigation Workspace');

    setLoading(true);
    setError(null);
    setNotice(null);

    const caseId = caseNumberIn(text);        // FIX 2: understands ಒಂದು / ಉಂಡು / "one" / "1"

    // NAME SEARCH — officers think in PEOPLE, not case IDs.
    // The box literally said "or Person Name (e.g. Ramesh Gowda)" and typing exactly that
    // returned "I could not map that to a capability." There was no name route at all. It now
    // hits /search/person, which is typo-tolerant and cross-script: "Rameshh Gowdaa" and
    // "ಮಂಜುನಾಥ್" both find the right man. Note what it does NOT do — it never merges two people
    // who share a name. It ranks candidates and a human picks.
    const looksLikeName = !caseId && /^[\p{L}][\p{L}\s.']{2,40}$/u.test(text.trim())
                          && text.trim().split(/\s+/).length <= 4;

    try {
      if (looksLikeName) {
        const r = await apiFetch(`/search/person?q=${encodeURIComponent(text.trim())}`);
        if (r.matches?.length) { setPeople(r.matches); setLoading(false); return; }
        // no name hits -> fall through and let the conversational layer try
      }
      setPeople(null);

      if (caseId) {
        // THE TOGGLE HAD NO EFFECT HERE — AND THIS IS THE PATH HE USES MOST.
        // /converse honoured prefer_language. /investigate never even looked at it. So an officer
        // who switched to Kannada and typed a case number — the commonest action in the entire
        // product — got an English briefing and no explanation. The switch was not broken; it was
        // decorative on the one screen that matters, which is worse, because he cannot tell
        // whether we ignored him or simply have no Kannada.
        const d = await apiFetch(`/investigate/${caseId}?lang=${lang === 'kn-IN' ? 'kn' : 'en'}`);
        currentCase.current = Number(caseId);      // the screen is now the context
        setData(d);
        fallbackEn.current = d?.narrative_en || d?.narrative || '';
        declaredLang.current = d?.narrative_language || 'en';   // the backend TELLS us. Believe it.
        if (d?.narrative) speak(d.narrative);      // hands full, eyes up
      } else {
        const d = await apiFetch('/converse', {
          method: 'POST',
          headers: { 'Content-Type': 'text/plain' },   // text/plain avoids the CORS pre-flight
          // THE SCREEN IS THE CONTEXT.
          // Without this, an officer looking at case 1 who asks "who was this guy running with"
          // was told "Which case should I analyse? (no case in context)". /investigate is a GET
          // that never touched the conversation session, and /converse reads that session — two
          // paths that never spoke. The machine was staring at the case and claiming not to see
          // it. We now send whatever is on screen. The clarifying question still fires when there
          // is genuinely nothing there; we did not weaken "ask, never guess" — we stopped
          // pretending we were blind.
          body: JSON.stringify({
            session_id: 'web',
            query: text,
            role: 'station_officer',
            case_id: currentCase.current,
            // The toggle is a STANDING instruction: if it says KN, brief me in Kannada even when
            // I type the case number in Latin digits. And if I actually WRITE Kannada, that wins
            // regardless of the toggle — what I typed is stronger evidence than a switch I set an
            // hour ago. The backend applies: (query is Kannada) OR (toggle is KN).
            prefer_language: lang === 'kn-IN' ? 'kn' : 'en',
          }),
        });
        // MERGE, DO NOT REPLACE.
        //
        // Bug found by using it: the officer loads case 1 — full briefing, crime network graph,
        // near-repeat count, similar-MO count. He asks ONE follow-up question, and the entire
        // case board goes blank: "No network yet. Investigate a case." Every counter resets to 0.
        //
        // Cause: /converse returns an ANSWER, not a case. setData({...}) built a brand-new object
        // from that answer, silently destroying the network, similar_cases and near_repeat that
        // /investigate had loaded. The data was never wrong — it was thrown away.
        //
        // An investigation ACCUMULATES context. It does not reset every time you open your mouth.
        fallbackEn.current = d.answer_en || d.answer || '';   // English to SPEAK if no KN voice
        declaredLang.current = d.answer_language || 'en';
        if (d.answer) speak(d.answer);
        setData(prev => ({
          ...(prev ?? {} as InvestigationData),
          case_id: d.case_id ?? prev?.case_id ?? (currentCase.current ? String(currentCase.current) : '—'),
          narrative: d.answer || d.narrative || d.clarification_needed || 'No answer returned.',
          narrative_source: d.narrative_source,
          citations: d.citations ?? prev?.citations,
        }));
      }
    } catch (e: any) {
      // FIX 4: NOT swallowed. The officer sees the failure.
      setError(e?.message ?? 'Could not reach the backend.');
    } finally {
      setLoading(false);
    }
  };

  /* ════════════════════════════════════════════════════════════════════════════════════════
   *  TEXT-TO-SPEECH — and the Kannada bug that made it read ONLY THE NUMBERS
   * ════════════════════════════════════════════════════════════════════════════════════════
   *
   *  SYMPTOM: a Kannada briefing was spoken as "one... two... three..." — the digits, and
   *  nothing else. Every Kannada word silent.
   *
   *  CAUSE — three mistakes stacked:
   *
   *    1. I set utterance.lang = 'kn-IN' and NEVER CHECKED WHETHER A KANNADA VOICE EXISTS.
   *       Chrome on Windows usually has none. It silently falls back to the English engine,
   *       which is then handed Kannada script it has no phonemes for. It skips every glyph it
   *       cannot pronounce — and reads the only thing it recognises: the numbers.
   *
   *    2. speechSynthesis.getVoices() is ASYNCHRONOUS. It returns [] on the first call, before
   *       the voice list loads. Anyone testing it once, early, sees "no voices" and moves on.
   *
   *    3. Setting .lang alone is NOT ENOUGH. Chrome largely ignores it unless you assign an
   *       actual SpeechSynthesisVoice object to .voice.
   *
   *  THE FIX, AND THE PRINCIPLE:
   *    Wait for the voice list. Find a real Kannada voice. Assign the voice OBJECT.
   *    And if there ISN'T one — SAY SO. Do not mumble a row of digits at a police officer and
   *    let him think the system is broken, or worse, that those numbers were the whole message.
   *    A tool that cannot do something must announce it. Silence is the one unacceptable answer.
   * ════════════════════════════════════════════════════════════════════════════════════════ */
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);

  useEffect(() => {
    if (!('speechSynthesis' in window)) return;
    const load = () => setVoices(window.speechSynthesis.getVoices());
    load();                                              // may be [] on first call...
    window.speechSynthesis.onvoiceschanged = load;       // ...so listen for the real list
    return () => { window.speechSynthesis.onvoiceschanged = null; };
  }, []);

  /** Find a real voice for a language. Returns null if the browser genuinely has none. */
  const pickVoice = (want: 'kn' | 'en'): SpeechSynthesisVoice | null => {
    if (!voices.length) return null;
    if (want === 'kn') {
      return voices.find(v => v.lang?.toLowerCase().startsWith('kn'))
          ?? voices.find(v => /kannada/i.test(v.name))
          ?? null;                                       // no Kannada voice on this machine
    }
    return voices.find(v => v.lang === 'en-IN')
        ?? voices.find(v => v.lang?.toLowerCase().startsWith('en'))
        ?? voices[0] ?? null;
  };

  const speak = (text: string) => {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();

    const clean = text.replace(/[*#_`]/g, '').replace(/\s+/g, ' ').trim();
    if (!clean) return;

    // Speak the language of the TEXT, not the language of the toggle. Reading English words
    // through a Kannada engine (or vice versa) produces noise, not an accent.
    // IS THIS A KANNADA BRIEFING, OR AN ENGLISH ONE ABOUT A MAN WITH A KANNADA NAME?
    //
    // This used to ask: does the text contain ANY Kannada character? Case 3's accused is called
    // ಮಂಜುನಾಥ್. His name sits inside an otherwise entirely English briefing. So the test said
    // "Kannada", the browser found no Kannada voice, and the officer was shown:
    //
    //     "No Kannada voice is installed... The Kannada text above is complete and correct."
    //
    // The text above was ENGLISH. The notice was false — a confident, well-formatted statement
    // about the screen that was wrong about the screen. One Kannada proper noun does not make an
    // English sentence Kannada.
    //
    // Two fixes: BELIEVE THE BACKEND when it declares the language (it knows — it did or did not
    // translate), and where it hasn't, measure the PROPORTION of Kannada letters rather than
    // asking whether a single one exists.
    const letters = clean.replace(/[^\p{L}]/gu, '');
    const knChars = (clean.match(/[\u0C80-\u0CFF]/g) || []).length;
    const knRatio = letters.length ? knChars / letters.length : 0;
    const isKannada = declaredLang.current === 'kn'
                      || (declaredLang.current == null && knRatio > 0.35);
    const voice = pickVoice(isKannada ? 'kn' : 'en');

    // NO KANNADA VOICE ON THIS MACHINE -> SPEAK THE ENGLISH. NEVER MUMBLE DIGITS.
    //
    // Windows ships no Kannada TTS voice, and neither will the judge's laptop. Handing Kannada
    // script to an English speech engine does not fail loudly — it SKIPS EVERY WORD IT CANNOT
    // PRONOUNCE and reads the numbers. The officer hears "one... two... three..." in a confident
    // voice, with the entire meaning removed. He concludes the tool is broken, or that those
    // numbers were the message.
    //
    // So: show the Kannada he asked for. Speak the English the machine can actually pronounce.
    // Tell him which is which. Degrading gracefully means saying what you did — not going quiet
    // and not making a fluent noise.
    if (isKannada && !voice) {
      const spoken = fallbackEn.current;
      if (spoken) {
        setNotice('No Kannada voice is installed on this device, so the briefing is being read aloud in English. The Kannada text above is complete and correct.');
        const enVoice = pickVoice('en');
        const enChunks = spoken.replace(/[*#_`]/g, '').match(/[^.!?]+[.!?]*/g) ?? [spoken];
        setSpeaking(true);
        enChunks.forEach((chunk, i) => {
          const u = new SpeechSynthesisUtterance(chunk.trim());
          if (enVoice) u.voice = enVoice;
          u.lang = 'en-IN';
          u.rate = 0.98;
          if (i === enChunks.length - 1) u.onend = () => setSpeaking(false);
          window.speechSynthesis.speak(u);
        });
      } else {
        setNotice('No Kannada voice is installed on this device. The Kannada text above is complete and correct, but cannot be read aloud.');
        setSpeaking(false);
      }
      return;      // NEVER hand Kannada script to an English engine. It reads only the digits.
    }

    const chunks = clean.match(/[^.!?]+[.!?]*/g) ?? [clean];
    setSpeaking(true);
    chunks.forEach((chunk, i) => {
      const u = new SpeechSynthesisUtterance(chunk.trim());
      if (voice) u.voice = voice;                        // assign the OBJECT, not just .lang
      u.lang = isKannada ? 'kn-IN' : 'en-IN';
      u.rate = 0.98;
      if (i === chunks.length - 1) u.onend = () => setSpeaking(false);
      window.speechSynthesis.speak(u);
    });
  };

  const stopAll = () => {
    setSpeaking(false);
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
    rec.lang = lang;                    // BUG 3: follows the KN/EN toggle now
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
                placeholder="Type a case number and press Enter — or ask a question. Mic speaks KN/EN."
                className="w-full bg-bg-surface border border-border-subtle rounded-md pl-10 pr-20 py-2 text-sm text-text-primary focus:ring-1 focus:ring-brand-accent focus:outline-none transition-all"
              />
              {listening && (
                <button onClick={stopAll} className="absolute right-[68px] p-1.5 rounded-md text-status-critical bg-status-critical/10" title="Stop listening">
                  <Square size={14} />
                </button>
              )}
              <button
                onClick={handleMic}
                title={lang === 'kn-IN' ? 'Speak in Kannada' : 'Speak in English'}
                className={`absolute right-9 p-1.5 rounded-md transition-colors ${listening ? 'text-status-critical bg-status-critical/10 animate-pulse' : 'text-text-muted hover:text-text-primary'}`}
              >
                <Mic size={16} />
              </button>
              {/* BUG 4: there was no way to submit with a mouse. */}
              <button
                onClick={() => executeSearch(query)}
                disabled={!query.trim()}
                title="Search (Enter)"
                className="absolute right-2 p-1.5 rounded-md text-text-muted hover:text-brand-accent disabled:opacity-30 transition-colors"
              >
                <CornerDownLeft size={16} />
              </button>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs font-medium text-text-secondary">
            {/* BUG 2: "KN / EN" was decorative TEXT. It is now the switch that actually drives
                speech recognition — which is why the mic only ever heard Kannada. */}
            <button
              onClick={() => setLang(l => (l === 'kn-IN' ? 'en-IN' : 'kn-IN'))}
              title="Switch voice recognition language"
              className="px-2 py-1 rounded border border-border-subtle hover:border-brand-accent transition-colors"
            >
              <span className={lang === 'kn-IN' ? 'text-brand-accent font-bold' : 'text-text-muted'}>KN</span>
              <span className="mx-1 text-text-muted">/</span>
              <span className={lang === 'en-IN' ? 'text-brand-accent font-bold' : 'text-text-muted'}>EN</span>
            </button>
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

                {notice && (
                  <div className="max-w-3xl mx-auto mb-6 border border-brand-accent/40 bg-brand-accent/5 rounded p-3 flex items-start gap-3">
                    <Volume2 size={16} className="text-brand-accent shrink-0 mt-0.5" />
                    <div className="text-xs text-text-secondary">{notice}</div>
                  </div>
                )}

                {/* NAME SEARCH RESULTS — candidates for a human to choose from.
                    Two different men with the same name appear as TWO rows, each with their own
                    cases. We rank; we never merge. */}
                {people && !loading && (
                  <div className="max-w-3xl mx-auto mb-8">
                    <h3 className="text-xs font-semibold uppercase text-text-muted mb-3">
                      {people.length} person(s) match — select one
                    </h3>
                    <div className="space-y-2">
                      {people.map((p: any) => (
                        <button key={p.accused_id}
                          onClick={() => { setPeople(null); executeSearch(String(p.cases[0])); }}
                          className="w-full text-left bg-bg-surface border border-border-subtle hover:border-brand-accent rounded p-4 transition-colors">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-text-primary font-medium">{p.name}</span>
                            <span className="text-[10px] font-mono text-text-muted">match {p.match_score}</span>
                          </div>
                          <div className="text-xs text-text-secondary">
                            age {p.age ?? '—'} · {p.case_count} case(s): {p.cases.slice(0, 6).join(', ')}
                            {p.resolved_identity && (
                              <span className="ml-2 text-status-success font-semibold">
                                ★ resolved across {p.linked_records} records
                              </span>
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                    <p className="text-[11px] text-text-muted mt-3 italic">
                      Two people can share a name. They are listed separately — KAVERI ranks candidates,
                      it never merges them.
                    </p>
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
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => (speaking ? stopAll() : speak(data.narrative || ''))}
                          title={speaking ? 'Stop reading' : 'Read this briefing aloud'}
                          className={`p-2 rounded border transition-colors ${speaking
                            ? 'border-status-critical text-status-critical bg-status-critical/10'
                            : 'border-border-subtle text-text-muted hover:text-text-primary'}`}
                        >
                          {speaking ? <Square size={14} /> : <Volume2 size={14} />}
                        </button>
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
