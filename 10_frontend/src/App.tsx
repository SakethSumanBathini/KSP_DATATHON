import React, { useState, useEffect, useRef } from 'react';
import { LayoutDashboard, Shield, AlertTriangle, Search, Mic, CheckCircle2, Database, Users, Activity, Fingerprint, Square, CornerDownLeft, Volume2, Loader2, RadioTower } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { IdentityResolutionView } from './IdentityResolutionView';
import { TheNumbersView } from './TheNumbersView';
import { PoliceCommandDashboard } from './PoliceCommandDashboard';
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

// Speech recognition mishears "case N" / "FIR N" as homophones: "case one" collapses into
// "Keshwan"/"Kishan", "FIR" is heard as "Fire"/"fear", "case" as "keys"/"kase". The Web Speech
// engine cannot be tuned, so we repair the transcript before parsing. This maps known mishearings
// back to their intent, then normal number-parsing takes over. English only — Kannada is untouched.
function normalizeVoice(text: string): string {
  let t = ' ' + text.toLowerCase().trim() + ' ';
  // "FIR" family -> "fir" (so "Fire 1" / "fear 1" -> "fir 1")
  t = t.replace(/\b(fire|fired|fier|fear|feyar|phair)\b/g, 'fir');
  // "case" family -> "case" (so "keys 1" / "kase 1" -> "case 1")
  t = t.replace(/\b(keys|kase|kaise|keys's|cayce)\b/g, 'case');
  // mangled "case one" said as a single word -> "case 1"
  t = t.replace(/\b(keshwan|kishwan|kishan|keshawan|keshvan|kesh one|kesh wan)\b/g, 'case 1');
  t = t.replace(/\b(kesh two|keshtwo)\b/g, 'case 2');
  t = t.replace(/\b(kesh three)\b/g, 'case 3');
  return t.trim();
}

// Spoken English numbers above ten. NUMWORDS only covered 1-10, so "case fourteen" fell through
// to null and — worse — "case two hundred" matched the bare "two" and CONFIDENTLY OPENED CASE 2.
// A system whose entire thesis is refusing to be confidently wrong must not silently open the
// wrong case. This parser handles compounds ("two hundred" = 200, "twenty five" = 25) and returns
// null when it finds no English number at all, so Kannada parsing below still gets its turn.
const EN_UNITS: Record<string, number> = { one:1, two:2, three:3, four:4, five:5, six:6, seven:7, eight:8, nine:9 };
const EN_TEENS: Record<string, number> = { ten:10, eleven:11, twelve:12, thirteen:13, fourteen:14, fifteen:15, sixteen:16, seventeen:17, eighteen:18, nineteen:19 };
const EN_TENS: Record<string, number> = { twenty:20, thirty:30, forty:40, fourty:40, fifty:50, sixty:60, seventy:70, eighty:80, ninety:90 };

function englishNumberIn(tokens: string[]): number | null {
  let value = 0, started = false;
  for (const tok of tokens) {
    if (EN_UNITS[tok] !== undefined)      { value += EN_UNITS[tok]; started = true; }
    else if (EN_TEENS[tok] !== undefined) { value += EN_TEENS[tok]; started = true; }
    else if (EN_TENS[tok] !== undefined)  { value += EN_TENS[tok]; started = true; }
    else if (tok === 'hundred')           { value = (value || 1) * 100; started = true; }
    else if (tok === 'and' && started)    { continue; }
    else if (started)                     { break; }   // number ended; stop before unrelated words
  }
  return started && value > 0 ? value : null;
}

function caseNumberIn(text: string): string | null {
  text = normalizeVoice(text);   // repair "Fire 1"->"fir 1", "Keshwan"->"case 1" before parsing
  const digits = text.match(/\b(\d{1,3})\b/);
  if (digits) return digits[1];

  const en = englishNumberIn(text.toLowerCase().split(/\s+/).filter(Boolean));
  if (en !== null) return String(en);

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
  const [activeView, setActiveView] = useState('Investigation Workspace');   // land on the REAL product first, not the concept dashboard
  const [activeTab, setActiveTab] = useState('Crime Network');
  // Dark-only. This is a police command / intelligence surface — dark is the correct, expected
  // aesthetic for the domain, and the whole palette is tuned for it. The theme mechanism (tokens
  // that flip on the .dark class) is left intact in the CSS, but the UI ships dark and the toggle
  // is hidden rather than shipping a second, lower-quality light surface.

  useEffect(() => {
    // Always dark (see theme note above).
    document.documentElement.classList.add('dark');
  }, []);

  useEffect(() => {
    apiFetch('/health')
      .then((d: any) => setHealth({ cases: d.cases || 0, identities: d.resolved_identities || 0, ok: true }))
      .catch(() => setHealth(prev => ({ ...prev, ok: false })));
  }, []);

  const executeSearch = async (text: string, overrideLang?: 'kn-IN' | 'en-IN') => {
    if (!text.trim()) return;
    const activeLang = overrideLang || lang;

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
        const d = await apiFetch(`/investigate/${caseId}?lang=${activeLang === 'kn-IN' ? 'kn' : 'en'}`);
        currentCase.current = Number(caseId);      // the screen is now the context
        setData(d);
        fallbackEn.current = d?.narrative_en || d?.narrative || '';
        declaredLang.current = d?.narrative_language || (activeLang === 'kn-IN' ? 'kn' : 'en');   // the backend TELLS us. Believe it.
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
            prefer_language: activeLang === 'kn-IN' ? 'kn' : 'en',
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
        declaredLang.current = d.answer_language || (activeLang === 'kn-IN' ? 'kn' : 'en');
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
    <div className="flex h-screen w-full bg-black text-neutral-300 overflow-hidden relative font-sans selection:bg-cyan-900/50">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:32px_32px] pointer-events-none z-0"></div>

      {/* LEFT SIDEBAR */}
      <aside className="w-[280px] flex-shrink-0 bg-panel border-r border-neutral-900 flex flex-col z-20 relative">
        <div className="p-6 border-b border-neutral-900 flex items-center gap-4">
          <div className="w-12 h-12 bg-white rounded flex items-center justify-center overflow-hidden shrink-0">
            <img
              src="/ksp-logo.webp"
              alt="Karnataka State Police"
              className="w-full h-full object-contain"
              onError={(e) => {
                const el = e.currentTarget;
                el.style.display = 'none';
                const parent = el.parentElement;
                if (parent && !parent.querySelector('.logo-fallback')) {
                  const span = document.createElement('span');
                  span.className = 'logo-fallback text-black font-black text-lg';
                  span.textContent = 'KSP';
                  parent.appendChild(span);
                }
              }}
            />
          </div>
          <div>
            <div className="font-bold text-white tracking-widest uppercase">KAVERI</div>
            <div className="text-[10px] text-neutral-500 uppercase font-mono tracking-widest mt-0.5">Karnataka Police</div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-1.5">
          <div className="mb-4 px-3 text-[10px] font-mono font-bold text-cyan-600 uppercase tracking-widest">Active Modules</div>
          <NavItem icon={<Fingerprint size={16} />} label="Identity Resolution" active={activeView === 'Identity Resolution'} onClick={() => setActiveView('Identity Resolution')} />
          <NavItem icon={<Activity size={16} />} label="Crime Analytics" active={activeView === 'System Performance'} onClick={() => setActiveView('System Performance')} />
          <NavItem icon={<LayoutDashboard size={16} />} label="Investigation Workspace" active={activeView === 'Investigation Workspace'} onClick={() => setActiveView('Investigation Workspace')} />
          <NavItem icon={<RadioTower size={16} />} label="Command Center" active={activeView === 'Police Command'} onClick={() => setActiveView('Police Command')} />
        </div>

        <div className="p-5 border-t border-neutral-900 bg-black/40">
          <div className="flex items-center gap-3 mb-4">
            <div className="relative flex h-2.5 w-2.5">
              {health.ok && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>}
              <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${health.ok ? 'bg-cyan-500 shadow-[0_0_8px_rgba(34,211,238,0.8)]' : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]'}`}></span>
            </div>
            <span className="text-xs font-mono text-neutral-400 uppercase tracking-widest">
              {health.ok ? `${health.cases} cases / ${health.identities} ID` : 'SYSTEM OFFLINE'}
            </span>
          </div>
          <div className="bg-panel rounded border border-neutral-800/50 p-4 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-neutral-700 to-transparent"></div>
            <div className="text-neutral-500 text-[10px] font-mono uppercase tracking-widest mb-1.5">Session Role</div>
            <div className="text-white font-semibold text-sm tracking-wide">SCRB Analyst</div>
            <div className="text-[10px] text-cyan-500/80 mt-1.5 uppercase font-mono tracking-widest font-bold">State-wide Access</div>
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0 z-10 relative">
        {/* TOP BAR */}
        <header className="h-[64px] bg-panel/95 backdrop-blur border-b border-neutral-900 flex items-center px-8 gap-6 z-10">
          <div className="flex-1 flex items-center">
            <div className="relative w-full max-w-3xl flex items-center group">
              <Search className="absolute left-4 text-cyan-500/50 group-focus-within:text-cyan-400 transition-colors" size={16} />
              <input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && executeSearch(query)}
                placeholder="Type case number, or press mic to speak KN/EN."
                className="w-full bg-neutral-950 border border-neutral-700 rounded pl-12 pr-24 py-2.5 text-sm text-cyan-100 font-mono focus:border-cyan-500/60 focus:ring-1 focus:ring-cyan-500/50 outline-none transition-all duration-300 placeholder:text-neutral-500 shadow-[inset_0_2px_10px_rgba(0,0,0,0.6)] focus:shadow-[inset_0_2px_10px_rgba(0,0,0,0.6),0_0_20px_rgba(34,211,238,0.15)]"
              />
              {listening && (
                <button onClick={stopAll} className="absolute right-[84px] p-1.5 rounded text-red-400 bg-red-500/10 hover:bg-red-500/20 transition-colors" title="Stop listening">
                  <Square size={14} />
                </button>
              )}
              <button
                onClick={handleMic}
                title={lang === 'kn-IN' ? 'Speak in Kannada' : 'Speak in English'}
                className={`absolute right-12 p-1.5 rounded transition-colors ${listening ? 'text-red-500 bg-red-500/10 animate-pulse shadow-[0_0_10px_rgba(239,68,68,0.2)]' : 'text-neutral-500 hover:text-cyan-400 hover:bg-cyan-500/10'}`}
              >
                <Mic size={16} />
              </button>
              <button
                onClick={() => executeSearch(query)}
                disabled={!query.trim()}
                title="Search (Enter)"
                className="absolute right-3 p-1.5 rounded text-neutral-600 hover:text-cyan-400 disabled:opacity-30 transition-colors"
              >
                <CornerDownLeft size={16} />
              </button>
            </div>
          </div>
          <div className="flex items-center gap-6 text-xs font-mono font-medium text-neutral-500">

            <button
              onClick={() => {
                const nextLang = lang === 'kn-IN' ? 'en-IN' : 'kn-IN';
                setLang(nextLang);
                if (currentCase.current) {
                  executeSearch(String(currentCase.current), nextLang);
                }
              }}
              title="Switch voice recognition language"
              className="flex items-center px-1 py-0.5 rounded border border-neutral-800 bg-panel hover:border-cyan-500/50 transition-colors"
            >
              <span className={`px-2 py-1 rounded-sm ${lang === 'kn-IN' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_5px_rgba(34,211,238,0.2)]' : 'text-neutral-600'}`}>KN</span>
              <span className={`px-2 py-1 rounded-sm ${lang === 'en-IN' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_5px_rgba(34,211,238,0.2)]' : 'text-neutral-600'}`}>EN</span>
            </button>
            <span className="tracking-widest uppercase">{new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })}</span>
          </div>
        </header>

        <main className="flex-1 flex overflow-hidden relative">
          <div className="scanline"></div>
          {activeView === 'Police Command' && <PoliceCommandDashboard />}
          {activeView === 'Identity Resolution' && <IdentityResolutionView />}
          {activeView === 'System Performance' && <TheNumbersView />}
          {activeView === 'Investigation Workspace' && (
            <>
              <section className="flex-1 overflow-y-auto border-r border-neutral-900 p-8 lg:p-12 relative bg-black/50">
                {error && (
                  <div className="max-w-3xl mx-auto mb-8 border border-red-500/30 bg-red-950/20 rounded p-5 flex items-start gap-4">
                    <AlertTriangle size={20} className="text-red-500 shrink-0 mt-0.5" />
                    <div>
                      <div className="text-red-500 font-mono font-bold tracking-widest uppercase text-sm mb-1">Request failed</div>
                      <div className="text-red-400/80 text-sm">{error}</div>
                    </div>
                  </div>
                )}

                {notice && (
                  <div className="max-w-3xl mx-auto mb-8 border border-cyan-500/30 bg-cyan-950/20 rounded p-5 flex items-start gap-4">
                    <Volume2 size={20} className="text-cyan-500 shrink-0 mt-0.5" />
                    <div className="text-sm text-cyan-300/80 leading-relaxed">{notice}</div>
                  </div>
                )}

                {people && !loading && (
                  <div className="max-w-3xl mx-auto mb-10">
                    <div className="flex items-center gap-3 mb-4">
                      <Users className="w-5 h-5 text-cyan-500" />
                      <h3 className="text-sm font-bold font-mono uppercase text-white tracking-widest">
                        {people.length} Person(s) Match
                      </h3>
                    </div>
                    <div className="space-y-3">
                      {people.map((p: any) => (
                        <button key={p.accused_id}
                          onClick={() => { setPeople(null); executeSearch(String(p.cases[0])); }}
                          className="w-full group text-left bg-panel border border-neutral-800 hover:border-cyan-500/50 hover:bg-panelHover rounded p-5 transition-all duration-300 relative overflow-hidden hover:-translate-y-1 hover:shadow-[0_10px_30px_-10px_rgba(34,211,238,0.2)]">
                          <div className="absolute left-0 top-0 bottom-0 w-1 bg-cyan-500/0 group-hover:bg-cyan-500 transition-colors duration-300"></div>
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-white font-semibold text-lg">{p.name}</span>
                            <span className="text-xs font-mono text-cyan-500/80 uppercase tracking-widest bg-cyan-950/30 px-2 py-1 rounded border border-cyan-500/10">Match {p.match_score}</span>
                          </div>
                          <div className="text-sm text-neutral-400 font-mono">
                            AGE: {p.age ?? 'UNK'} <span className="mx-2 text-neutral-700">|</span> {p.case_count} CASE(S): <span className="text-neutral-300">{p.cases.slice(0, 6).join(', ')}</span>
                            {p.resolved_identity && (
                              <span className="ml-4 text-cyan-400 font-bold bg-cyan-950/40 px-2 py-1 rounded border border-cyan-500/20 shadow-[0_0_10px_rgba(34,211,238,0.15)]">
                                ★ RESOLVED (ACROSS {p.linked_records} RECORDS)
                              </span>
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                    <p className="text-xs font-mono text-neutral-600 mt-4 uppercase tracking-widest">
                      KAVERI ranks candidates. It never auto-merges them.
                    </p>
                  </div>
                )}

                {loading ? (
                  <div className="flex flex-col items-center justify-center h-full text-cyan-500">
                    <Loader2 className="w-8 h-8 animate-spin mb-4" />
                    <div className="font-mono text-sm tracking-widest uppercase">Querying Intelligence...</div>
                  </div>
                ) : data ? (
                  <div className="max-w-3xl mx-auto space-y-10 relative">
                    
                    <div className="flex flex-col md:flex-row md:items-start justify-between gap-6 pb-6 border-b border-neutral-900">
                      <div>
                        <div className="text-[10px] text-cyan-500 font-mono font-bold uppercase tracking-widest mb-2">Intelligence Report</div>
                        <h2 className="text-4xl font-bold tracking-tight text-white mb-4 uppercase">FIR {data.case_id}</h2>
                        {data.sections && (
                          <div className="flex flex-wrap gap-2">
                            {data.sections.map(s => (
                              <span key={s} className="px-2.5 py-1 text-[11px] font-mono bg-neutral-900 border border-neutral-800 rounded text-neutral-400 uppercase tracking-wider">{s}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      
                      <div className="flex flex-col items-end gap-3 shrink-0">
                        <button
                          onClick={() => (speaking ? stopAll() : speak(data.narrative || ''))}
                          title={speaking ? 'Stop reading' : 'Read this briefing aloud'}
                          className={`flex items-center justify-center w-10 h-10 rounded-full transition-all ${speaking
                            ? 'bg-red-500/20 text-red-500 border border-red-500/50 shadow-[0_0_15px_rgba(239,68,68,0.3)]'
                            : 'bg-neutral-900 text-neutral-400 hover:text-cyan-400 hover:bg-cyan-950 hover:border-cyan-500/50 border border-neutral-800'}`}
                        >
                          {speaking ? <Square size={16} className="fill-current" /> : <Volume2 size={16} />}
                        </button>
                        {data.narrative_source === 'catalyst_glm' ? (
                          <div className="flex items-center gap-2 bg-cyan-950/30 border border-cyan-500/30 px-3 py-1.5 rounded text-cyan-400 text-[10px] font-mono font-bold uppercase tracking-widest">
                            <Shield size={12} /> Catalyst GLM-4.7
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 bg-amber-950/30 border border-amber-500/30 px-3 py-1.5 rounded text-amber-500 text-[10px] font-mono font-bold uppercase tracking-widest">
                            <AlertTriangle size={12} /> Deterministic
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="prose prose-invert max-w-none text-neutral-300 leading-relaxed font-light text-lg">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.narrative || ''}</ReactMarkdown>
                    </div>

                    {data.citations && data.citations.length > 0 && (
                      <div className="pt-8 border-t border-neutral-900">
                        <div className="flex items-center gap-2 mb-4">
                          <Database className="w-4 h-4 text-cyan-500" />
                          <h3 className="text-xs font-bold font-mono uppercase text-neutral-400 tracking-widest">Verified Sources</h3>
                        </div>
                        <div className="flex flex-wrap gap-3">
                          {data.citations.map(c => (
                            <button key={c} onClick={() => executeSearch(String(c))}
                              className="px-4 py-2 bg-panel border border-neutral-800 hover:border-cyan-500/50 hover:text-cyan-400 hover:-translate-y-0.5 hover:shadow-[0_5px_15px_-5px_rgba(34,211,238,0.3)] rounded font-mono text-xs transition-all duration-300">
                              FIR {c}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {data.recommended_leads && data.recommended_leads.length > 0 && (
                      <div className="pt-8 border-t border-neutral-900">
                        <div className="flex items-center gap-2 mb-4">
                          <Activity className="w-4 h-4 text-cyan-500" />
                          <h3 className="text-xs font-bold font-mono uppercase text-neutral-400 tracking-widest">Recommended Actions</h3>
                        </div>
                        <ul className="space-y-3">
                          {data.recommended_leads.map((lead, i) => (
                            <li key={i} className="flex items-start gap-4 bg-neutral-900/30 p-4 rounded border border-neutral-800/50 relative overflow-hidden">
                              <div className="absolute left-0 top-0 bottom-0 w-[2px] bg-cyan-500/50"></div>
                              <CheckCircle2 size={18} className="text-cyan-500 mt-0.5 shrink-0" />
                              <span className="text-neutral-300 font-light">{lead}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-neutral-700">
                    <Shield size={64} className="mb-6 opacity-20" strokeWidth={1} />
                    <p className="text-sm font-mono uppercase tracking-widest text-neutral-500 text-center">
                      Awaiting Input<br/>
                      <span className="text-[10px] text-neutral-600 mt-2 block">Enter Case # or use Voice Input</span>
                    </p>
                  </div>
                )}
              </section>

              {/* RIGHT ASIDE (TABS + NETWORK) */}
              <aside className="w-[480px] flex-shrink-0 bg-panel flex flex-col min-h-0 border-l border-neutral-900">
                <div className="flex border-b border-neutral-900 pt-2 px-2 gap-1 bg-panel">
                  {['Crime Network', 'Identity Panel', 'Similar Cases'].map(t => (
                    <button key={t} onClick={() => setActiveTab(t)}
                      className={`flex-1 py-3 text-[11px] font-mono font-bold uppercase tracking-widest transition-all rounded-t-sm ${activeTab === t ? 'text-cyan-400 bg-panelHover border-b-2 border-cyan-500' : 'text-neutral-600 hover:text-neutral-300 hover:bg-neutral-900'}`}>
                      {t}
                    </button>
                  ))}
                </div>

                <div className="flex-1 relative overflow-hidden bg-black">
                  {activeTab === 'Crime Network' && (
                    data?.network
                      ? <NetworkGraph network={data.network} rootCase={data.case_id} />
                      : <div className="absolute inset-0 flex items-center justify-center text-xs font-mono uppercase tracking-widest text-neutral-600 p-8 text-center bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:16px_16px]">
                          NO NETWORK DATA
                        </div>
                  )}
                  {activeTab === 'Identity Panel' && (
                    (data?.network?.accused?.length || data?.network?.linked_cases?.length)
                      ? <div className="absolute inset-0 overflow-y-auto p-5 space-y-4 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:32px_32px]">
                          {/* ACCUSED — resolved identities */}
                          {data.network?.accused?.length ? (
                            <div>
                              <div className="text-[10px] font-mono uppercase tracking-widest text-cyan-600 mb-2">Accused · cross-case identity</div>
                              <div className="space-y-2">
                                {data.network.accused.map(a => (
                                  <div key={a.accused_id} className="bg-panel border border-neutral-800 rounded p-3 flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                      <Users size={16} className="text-cyan-500 shrink-0" />
                                      <span className="text-sm font-bold text-white">{a.name}</span>
                                    </div>
                                    <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/30 px-2 py-0.5 rounded border border-cyan-500/10">{a.identity}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : null}

                          {/* LINKED CASES — the network this case belongs to */}
                          {data.network?.linked_cases?.length ? (
                            <div>
                              <div className="text-[10px] font-mono uppercase tracking-widest text-cyan-600 mb-2">Linked cases · {data.network.linked_cases.length} via shared evidence</div>
                              <div className="flex flex-wrap gap-2">
                                {data.network.linked_cases.map(cid => (
                                  <button key={cid} onClick={() => executeSearch(String(cid))}
                                    className="text-xs font-mono bg-panel border border-neutral-800 hover:border-cyan-500/50 hover:text-cyan-300 text-neutral-300 px-3 py-1.5 rounded transition-colors">
                                    FIR {cid}
                                  </button>
                                ))}
                              </div>
                            </div>
                          ) : null}

                          {/* SHARED EVIDENCE — what corroborates the identity */}
                          {(data.network?.shared_phones?.length || data.network?.shared_vehicles?.length) ? (
                            <div>
                              <div className="text-[10px] font-mono uppercase tracking-widest text-cyan-600 mb-2">Corroborating evidence</div>
                              <div className="space-y-1.5">
                                {data.network?.shared_phones?.map(ph => (
                                  <div key={ph} className="text-xs font-mono text-neutral-400 bg-panel border border-neutral-800 rounded px-3 py-2">📞 {ph}</div>
                                ))}
                                {data.network?.shared_vehicles?.map(v => (
                                  <div key={v} className="text-xs font-mono text-neutral-400 bg-panel border border-neutral-800 rounded px-3 py-2">🚗 {v}</div>
                                ))}
                              </div>
                            </div>
                          ) : null}

                          <button onClick={() => setActiveView('Identity Resolution')}
                            className="w-full text-center text-[10px] font-mono uppercase tracking-widest text-cyan-500 hover:text-cyan-300 border border-cyan-500/20 hover:border-cyan-500/50 rounded py-2.5 transition-colors mt-2">
                            See how the resolution engine works →
                          </button>
                        </div>
                      : <div className="absolute inset-0 flex flex-col items-center justify-center text-xs font-mono uppercase tracking-widest text-neutral-600 p-8 text-center bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:16px_16px]">
                          <Users size={32} className="mb-4 opacity-30" />
                          NO CROSS-CASE IDENTITY FOR THIS FIR
                        </div>
                  )}
                  {activeTab === 'Similar Cases' && (
                    data?.similar_cases?.length
                      ? <div className="absolute inset-0 overflow-y-auto p-5 space-y-3 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:32px_32px]">
                          {data.similar_cases.map(sc => (
                            <button key={sc.case_id} onClick={() => executeSearch(String(sc.case_id))}
                              className="w-full text-left bg-panel border border-neutral-800 hover:border-cyan-500/50 hover:bg-panelHover rounded p-4 transition-all duration-300 relative overflow-hidden group hover:-translate-y-1 hover:shadow-[0_10px_20px_-10px_rgba(34,211,238,0.25)]">
                              <div className="absolute left-0 top-0 bottom-0 w-1 bg-transparent group-hover:bg-cyan-500 transition-colors duration-300"></div>
                              <div className="flex justify-between items-center mb-2">
                                <span className="text-sm font-bold text-white uppercase tracking-wider">FIR {sc.case_id}</span>
                                <span className="text-[10px] font-mono text-cyan-400 font-bold bg-cyan-950/30 px-2 py-0.5 rounded border border-cyan-500/10">SIMILARITY {sc.score.toFixed(3)}</span>
                              </div>
                              <div className="text-xs text-neutral-400 line-clamp-2 leading-relaxed">{sc.brief}</div>
                            </button>
                          ))}
                        </div>
                      : <div className="absolute inset-0 flex flex-col items-center justify-center text-xs font-mono uppercase tracking-widest text-neutral-600 p-8 text-center bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:16px_16px]">
                          <Database size={32} className="mb-4 opacity-30" />
                          NO MO MATCHES FOUND
                        </div>
                  )}
                </div>

                {data && (
                  <div className="h-64 border-t border-neutral-900 p-6 overflow-y-auto bg-panel">
                    <h3 className="text-[10px] font-mono font-bold uppercase tracking-widest text-cyan-600 mb-5">Risk &amp; Insights</h3>
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
    <button onClick={onClick} className={`w-full flex items-center gap-3 px-4 py-3 rounded text-sm font-medium transition-all border-l-[3px] ${active ? 'bg-cyan-950/30 text-cyan-400 border-cyan-500' : 'text-neutral-500 hover:bg-neutral-900/50 hover:text-white border-transparent'}`}>
      <span className={active ? "text-cyan-400" : "text-neutral-600"}>{icon}</span>
      {label}
    </button>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-panel border border-neutral-800 p-4 rounded relative overflow-hidden group hover:-translate-y-1 hover:shadow-[0_10px_20px_-10px_rgba(34,211,238,0.2)] transition-all duration-300">
      <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-cyan-900 to-transparent group-hover:via-cyan-400 transition-colors duration-300"></div>
      <div className="text-[9px] uppercase font-mono font-bold tracking-widest text-neutral-500 mb-2">{label}</div>
      <div className="text-2xl font-mono font-bold text-white group-hover:text-cyan-400 transition-colors duration-300">{value}</div>
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
      className: 'pulse-node-danger',
      style: { background: '#ef4444', color: '#fff', border: '2px solid #7f1d1d', width: 64, height: 64, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 'bold', fontFamily: 'monospace', boxShadow: '0 0 20px rgba(239,68,68,0.4)' },
    });

    const items: [string, string, string, number, string][] = [];
    (network.linked_cases || []).forEach((c: string) => items.push([`case-${c}`, `FIR ${c}`, '#ef4444', 22, '#7f1d1d']));
    (network.accused || []).forEach((a: any) => items.push([`acc-${a.accused_id}`, a.name, '#f59e0b', 28, '#78350f']));
    (network.shared_phones || []).forEach((p: string) => items.push([`ph-${p}`, p.slice(-5), '#06b6d4', 18, '#164e63']));
    (network.shared_vehicles || []).forEach((v: string) => items.push([`veh-${v}`, v, '#10b981', 18, '#064e3b']));

    const n = Math.max(items.length, 1);
    items.forEach(([id, label, color, radius, border], i) => {
      const angle = (Math.PI * 2 * i) / n;
      newNodes.push({
        id,
        position: { x: 240 + Math.cos(angle) * 160, y: 180 + Math.sin(angle) * 160 },
        data: { label },
        style: { background: color, color: '#fff', border: `1px solid ${border}`, width: radius * 2, height: radius * 2, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, textAlign: 'center', fontFamily: 'monospace', fontWeight: 'bold', boxShadow: `0 0 10px ${color}40` },
      });
      newEdges.push({
        id: `e-${rootCase}-${id}`,
        source: `case-${rootCase}`,
        target: id,
        animated: true,
        style: { stroke: 'rgba(255,255,255,0.15)', strokeWidth: 1.5 },
      });
    });

    setNodes(newNodes);
    setEdges(newEdges);
  }, [network, rootCase, setNodes, setEdges]);

  return (
    <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }} className="bg-black">
      <Background color="#1a1a1a" gap={20} size={1.5} />
      <Controls className="!bg-panel !border-neutral-800 !text-neutral-400" />
    </ReactFlow>
  );
}
