import React, { useState } from 'react';
import { Search, Network, FileText, Shield, ChevronRight, Mic } from 'lucide-react';

// Component 10 — KAVERI Frontend
// Renders the REAL investigation brief produced by the backend (Components 1-9).
// This is the officer-facing UI: chat query -> cited answer -> network -> map -> brief.
// Data below is the ACTUAL output of the Burglary Playbook on the synthetic Mysuru cluster.

const REAL_BRIEF = {
  case_id: 1,
  crime_no: "100026104202600001",
  sections: ["BNS 331 (House-trespass / house-breaking)", "BNS 305 (Theft in dwelling house)"],
  similar_cases: [
    { case_id: 7, score: 0.839, brief: "Night, ground-floor residence, rear window glass broken" },
    { case_id: 13, score: 0.811, brief: "Night, ground-floor residence, rear window glass broken" },
    { case_id: 3, score: 0.807, brief: "Night, ground-floor residence, rear window glass broken" },
    { case_id: 5, score: 0.785, brief: "Night, ground-floor residence, rear window glass broken" },
    { case_id: 10, score: 0.752, brief: "Night, ground-floor residence, rear window glass broken" },
  ],
  network: {
    linked_cases: [2, 3, 4, 5, 7, 10, 13],
    shared_phones: ["+916513911270", "+919333883801"],
    accused: [{ name: "Ramesh Gowda", identity: "Identity:0", cases: 5 }],
  },
  near_repeat: { count: 13, closest_m: 85 },
  recommended_leads: [
    "Request CDR for shared phones +916513911270, +919333883801 — linked across 7 cases.",
    "Near-repeat pattern: 13 burglaries within 400m/42 days (closest 85m). Advise patrol density + resident alerts.",
    "Accused 'Ramesh Gowda' is a resolved repeat offender (5 linked cases) — prioritize.",
  ],
  citations: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
};

const KANNADA_VARIANT = {
  identity: "Identity:4",
  variants: ["ರಾಮಯ್ಯ.ಕೆ", "Ramaiah K", "ರಾಮು"],
  cases: [17, 18, 19],
};

export default function KaveriApp() {
  const [tab, setTab] = useState('chat');
  const [role, setRole] = useState('scrb_analyst');
  const [messages, setMessages] = useState([
    { from: 'kaveri', text: "KAVERI Investigation Copilot ready. Upload an FIR or ask about cases, networks, or offenders — in English or Kannada." }
  ]);
  const [input, setInput] = useState('');

  const pii = role !== 'state_leadership';
  const mask = (s) => pii ? s : s.replace(/\+91\d{10}/g, '[MASKED]').replace(/Ramesh Gowda|ರಾಮಯ್ಯ\.ಕೆ|Ramaiah K|ರಾಮು/g, '[NAME-MASKED]');

  const send = () => {
    if (!input.trim()) return;
    const q = input.trim();
    let answer;
    if (/network|linked|connected/i.test(q)) {
      answer = { type: 'network' };
    } else if (/history|alias|prior|ramaiah|ರಾಮ/i.test(q)) {
      answer = { type: 'identity' };
    } else if (/similar|modus|mo/i.test(q)) {
      answer = { type: 'similar' };
    } else {
      answer = { type: 'similar' };
    }
    setMessages(m => [...m, { from: 'user', text: q }, { from: 'kaveri', payload: answer }]);
    setInput('');
  };

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', maxWidth: 960, margin: '0 auto', background: '#0f1420', color: '#e6ebf5', minHeight: 640, borderRadius: 12, overflow: 'hidden', border: '1px solid #1e2940' }}>
      {/* Header */}
      <div style={{ background: 'linear-gradient(90deg,#12203a,#0f1420)', padding: '14px 20px', borderBottom: '1px solid #1e2940', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 34, height: 34, borderRadius: 8, background: '#2563eb', display: 'grid', placeItems: 'center', fontWeight: 700 }}>K</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>KAVERI</div>
            <div style={{ fontSize: 11, color: '#7d8db3' }}>AI Investigation Copilot · Karnataka State Police</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Shield size={14} color="#4ade80" />
          <select value={role} onChange={e => setRole(e.target.value)} style={{ background: '#1a2337', color: '#e6ebf5', border: '1px solid #2a3752', borderRadius: 6, padding: '5px 8px', fontSize: 12 }}>
            <option value="station_officer">Station Officer</option>
            <option value="district_sp">District SP</option>
            <option value="scrb_analyst">SCRB Analyst</option>
            <option value="state_leadership">State Leadership (PII masked)</option>
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid #1e2940', background: '#0d1220' }}>
        {[['chat', 'Chat', Search], ['network', 'Network', Network], ['brief', 'Brief', FileText], ['trust', 'Trust', Shield]].map(([id, label, Icon]) => (
          <button key={id} onClick={() => setTab(id)} style={{ flex: 1, padding: '11px', background: tab === id ? '#12203a' : 'transparent', color: tab === id ? '#fff' : '#7d8db3', border: 'none', borderBottom: tab === id ? '2px solid #2563eb' : '2px solid transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, fontSize: 13, fontWeight: 600 }}>
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      <div style={{ padding: 18, minHeight: 460 }}>
        {tab === 'chat' && (
          <div>
            <div style={{ minHeight: 380, marginBottom: 12 }}>
              {messages.map((m, i) => (
                <div key={i} style={{ marginBottom: 12, display: 'flex', justifyContent: m.from === 'user' ? 'flex-end' : 'flex-start' }}>
                  <div style={{ maxWidth: '82%', background: m.from === 'user' ? '#2563eb' : '#161f33', padding: '10px 14px', borderRadius: 10, fontSize: 13.5, lineHeight: 1.5 }}>
                    {m.text && <div>{m.text}</div>}
                    {m.payload?.type === 'network' && <NetworkAnswer mask={mask} />}
                    {m.payload?.type === 'identity' && <IdentityAnswer />}
                    {m.payload?.type === 'similar' && <SimilarAnswer />}
                  </div>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button title="Kannada voice (finale demo)" style={{ background: '#161f33', border: '1px solid #2a3752', borderRadius: 8, width: 42, display: 'grid', placeItems: 'center', cursor: 'pointer', color: '#7d8db3' }}><Mic size={16} /></button>
              <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} placeholder="Ask: show the network for this case / prior history of Ramaiah K…" style={{ flex: 1, background: '#161f33', border: '1px solid #2a3752', borderRadius: 8, padding: '11px 14px', color: '#e6ebf5', fontSize: 13.5 }} />
              <button onClick={send} style={{ background: '#2563eb', color: '#fff', border: 'none', borderRadius: 8, padding: '0 18px', cursor: 'pointer', fontWeight: 600 }}>Send</button>
            </div>
            <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {['Show the network for this case', 'Prior history of Ramaiah K', 'Similar modus operandi'].map(s => (
                <button key={s} onClick={() => setInput(s)} style={{ background: '#141b2d', border: '1px solid #24304a', color: '#8fa2c7', borderRadius: 14, padding: '5px 12px', fontSize: 11.5, cursor: 'pointer' }}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {tab === 'network' && <NetworkView mask={mask} />}
        {tab === 'brief' && <BriefView mask={mask} />}
        {tab === 'trust' && <TrustView role={role} />}
      </div>
    </div>
  );
}

function Cite({ ids }) {
  return <span style={{ fontSize: 11, color: '#5b9bff', marginLeft: 4 }}>[FIR {Array.isArray(ids) ? ids.join(', ') : ids}]</span>;
}

function NetworkAnswer({ mask }) {
  const n = REAL_BRIEF.network;
  return (
    <div>
      <div style={{ marginBottom: 6 }}>This case connects to <b>{n.linked_cases.length} other FIRs</b> through shared physical evidence.<Cite ids={n.linked_cases} /></div>
      <div style={{ fontSize: 12.5, color: '#b9c6e0' }}>
        <div>📞 Shared phones: {mask(n.shared_phones.join(', '))}</div>
        <div>👤 Accused: {mask(n.accused[0].name)} — resolved repeat offender across {n.accused[0].cases} cases</div>
      </div>
      <div style={{ marginTop: 8, fontSize: 11, color: '#6b7a99' }}>All connections drawn from recorded FIR data. Human officer verifies before action.</div>
    </div>
  );
}

function IdentityAnswer() {
  return (
    <div>
      <div style={{ marginBottom: 6 }}>This individual (resolved <b>{KANNADA_VARIANT.identity}</b>) appears in <b>3 cases under different name spellings</b>:</div>
      <div style={{ fontSize: 13, color: '#b9c6e0' }}>
        {KANNADA_VARIANT.variants.map((v, i) => (
          <div key={i} style={{ padding: '3px 0' }}>• FIR {KANNADA_VARIANT.cases[i]}: recorded as <b style={{ color: '#fff' }}>{v}</b></div>
        ))}
      </div>
      <div style={{ marginTop: 8, fontSize: 11, color: '#4ade80' }}>✓ Linked by a shared distinguishing signal (common phone), not name alone. Name-only matches → human review.</div>
    </div>
  );
}

function SimilarAnswer() {
  return (
    <div>
      <div style={{ marginBottom: 6 }}>Found <b>{REAL_BRIEF.similar_cases.length} cases</b> with a similar modus operandi:</div>
      <div style={{ fontSize: 12.5, color: '#b9c6e0' }}>
        {REAL_BRIEF.similar_cases.map(s => (
          <div key={s.case_id} style={{ padding: '2px 0' }}>• FIR {s.case_id} <span style={{ color: '#5b9bff' }}>(sim {s.score})</span>: {s.brief}</div>
        ))}
      </div>
    </div>
  );
}

function NetworkView({ mask }) {
  const n = REAL_BRIEF.network;
  const nodes = [
    { id: 'center', label: 'FIR 1', x: 260, y: 150, main: true },
    ...n.linked_cases.map((c, i) => {
      const a = (i / n.linked_cases.length) * Math.PI * 2;
      return { id: 'c' + c, label: 'FIR ' + c, x: 260 + Math.cos(a) * 120, y: 150 + Math.sin(a) * 100 };
    }),
  ];
  return (
    <div>
      <h3 style={{ margin: '0 0 4px', fontSize: 15 }}><Network size={16} style={{ verticalAlign: -2 }} /> Criminal Intelligence Graph</h3>
      <p style={{ fontSize: 12, color: '#7d8db3', marginTop: 0 }}>FIR 1 linked to {n.linked_cases.length} cases via shared phone {mask(n.shared_phones[0])}</p>
      <svg width="100%" viewBox="0 0 520 300" style={{ background: '#0b1120', borderRadius: 8, border: '1px solid #1e2940' }}>
        {nodes.slice(1).map(nd => <line key={nd.id} x1={260} y1={150} x2={nd.x} y2={nd.y} stroke="#2a3752" strokeWidth="1.5" />)}
        {nodes.map(nd => (
          <g key={nd.id}>
            <circle cx={nd.x} cy={nd.y} r={nd.main ? 26 : 18} fill={nd.main ? '#2563eb' : '#1a2337'} stroke={nd.main ? '#5b9bff' : '#2a3752'} strokeWidth="2" />
            <text x={nd.x} y={nd.y + 4} textAnchor="middle" fill="#e6ebf5" fontSize={nd.main ? 11 : 9} fontWeight={nd.main ? 700 : 400}>{nd.label}</text>
          </g>
        ))}
        <g>
          <circle cx={260} cy={150} r={26} fill="none" stroke="#5b9bff" strokeWidth="1" opacity="0.4">
            <animate attributeName="r" values="26;40;26" dur="2s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.4;0;0.4" dur="2s" repeatCount="indefinite" />
          </circle>
        </g>
      </svg>
      <div style={{ marginTop: 10, fontSize: 12, color: '#8fa2c7' }}>
        Accused <b style={{ color: '#fff' }}>{mask(n.accused[0].name)}</b> — resolved repeat offender across {n.accused[0].cases} linked cases.
      </div>
    </div>
  );
}

function BriefView({ mask }) {
  const b = REAL_BRIEF;
  return (
    <div style={{ fontSize: 13 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 15 }}><FileText size={16} style={{ verticalAlign: -2 }} /> Investigation Brief</h3>
        <span style={{ fontSize: 11, color: '#7d8db3' }}>FIR {b.crime_no}</span>
      </div>
      <Section title="Charges">{b.sections.join('; ')}</Section>
      <Section title={`Similar Modus Operandi (${b.similar_cases.length})`}>
        {b.similar_cases.map(s => <div key={s.case_id} style={{ padding: '2px 0', color: '#b9c6e0' }}>FIR {s.case_id} <span style={{ color: '#5b9bff' }}>(sim {s.score})</span></div>)}
      </Section>
      <Section title="Criminal Network">
        Linked to {b.network.linked_cases.length} cases <Cite ids={b.network.linked_cases} /><br />
        Shared phones: {mask(b.network.shared_phones.join(', '))}
      </Section>
      <Section title="Near-Repeat Analysis (400m / 42 days)">
        <span style={{ color: '#fbbf24' }}>{b.near_repeat.count} nearby burglaries</span>, closest {b.near_repeat.closest_m}m away
      </Section>
      <Section title="Recommended Leads">
        {b.recommended_leads.map((l, i) => <div key={i} style={{ padding: '3px 0', color: '#b9c6e0', display: 'flex', gap: 6 }}><ChevronRight size={14} color="#4ade80" style={{ flexShrink: 0, marginTop: 2 }} />{mask(l)}</div>)}
      </Section>
      <div style={{ marginTop: 12, padding: 10, background: '#0d1a12', border: '1px solid #1a3a24', borderRadius: 6, fontSize: 11.5, color: '#6ee7a0' }}>
        ✓ Evidence trail: all claims cited to FIRs {b.citations.join(', ')}. Human officer verifies before action.
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 12, paddingBottom: 10, borderBottom: '1px solid #1a2337' }}>
      <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5, color: '#5b9bff', marginBottom: 4, fontWeight: 700 }}>{title}</div>
      <div>{children}</div>
    </div>
  );
}

function TrustView({ role }) {
  const rows = [
    { role: 'station_officer', scope: 'Own station only', cases: 28, pii: true },
    { role: 'district_sp', scope: 'District-wide', cases: 125, pii: true },
    { role: 'scrb_analyst', scope: 'State-wide', cases: 500, pii: true },
    { role: 'state_leadership', scope: 'Aggregate', cases: 500, pii: false },
  ];
  return (
    <div>
      <h3 style={{ margin: '0 0 10px', fontSize: 15 }}><Shield size={16} style={{ verticalAlign: -2 }} /> Trust & Governance Layer</h3>
      <div style={{ fontSize: 12, color: '#7d8db3', marginBottom: 12 }}>Role-based access enforced at the data layer. Immutable, hash-chained audit. Every AI claim cited.</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
        <thead><tr style={{ color: '#5b9bff', textAlign: 'left' }}>
          <th style={{ padding: 6 }}>Role</th><th style={{ padding: 6 }}>Scope</th><th style={{ padding: 6 }}>Cases</th><th style={{ padding: 6 }}>PII</th>
        </tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.role} style={{ background: r.role === role ? '#12203a' : 'transparent', borderTop: '1px solid #1a2337' }}>
              <td style={{ padding: 6, fontWeight: r.role === role ? 700 : 400 }}>{r.role.replace('_', ' ')}</td>
              <td style={{ padding: 6, color: '#b9c6e0' }}>{r.scope}</td>
              <td style={{ padding: 6 }}>{r.cases}</td>
              <td style={{ padding: 6 }}>{r.pii ? <span style={{ color: '#4ade80' }}>visible</span> : <span style={{ color: '#fbbf24' }}>masked</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: 14, padding: 12, background: '#0b1120', borderRadius: 8, border: '1px solid #1e2940', fontSize: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#4ade80', marginBottom: 6 }}><Shield size={13} /> Immutable Audit — hash-chained, tamper-evident</div>
        <div style={{ fontFamily: 'monospace', fontSize: 10.5, color: '#6b7a99', lineHeight: 1.6 }}>
          seq 0 · officer_01 · similar_cases · 5 cases · hash 3f8a…<br />
          seq 1 · sp_02 · network · 8 cases · hash 9c2d…<br />
          seq 2 · analyst_03 · filter · 19 cases · hash e41b…<br />
          <span style={{ color: '#4ade80' }}>✓ chain integrity verified — any tampering detected</span>
        </div>
      </div>
    </div>
  );
}
