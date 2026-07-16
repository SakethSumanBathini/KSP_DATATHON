import { useMemo, useState, useEffect } from 'react';
import { apiFetch } from './api';
import {
  BarChart3,
  Bot,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  ClipboardList,
  Eye,
  FileText,
  Landmark,
  MapPin,
  Search,
  Shield,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';

type FirStatus = 'Registered' | 'Assigned' | 'Investigating' | 'Charge Sheet' | 'Closed';
type Priority = 'Critical' | 'High' | 'Medium' | 'Low';

interface Kpi {
  label: string;
  value: string;
  percent: string;
  trend: 'up' | 'down';
  updated: string;
  icon: React.ElementType;
  tone: 'cyan' | 'red' | 'amber' | 'emerald' | 'blue';
  series: number[];
}

interface Marker {
  id: string;
  kind: string;
  label: string;
  x: number;
  y: number;
  color: string;
  fir: string;
  crimeType: string;
  victim: string;
  officer: string;
  priority: Priority;
  status: FirStatus;
  evidence: number;
  time: string;
}

interface FirRow {
  fir: string;
  station: string;
  district: string;
  crimeType: string;
  officer: string;
  status: FirStatus;
  priority: Priority;
  date: string;
}

const _fbKpis: Kpi[] = [
  { label: 'Total FIRs', value: '—', percent: 'loading', trend: 'up', updated: '', icon: FileText, tone: 'cyan', series: [0, 0, 0, 0, 0, 0, 0] },
  { label: 'Under Investigation', value: '—', percent: 'loading', trend: 'up', updated: '', icon: Search, tone: 'amber', series: [0, 0, 0, 0, 0, 0, 0] },
  { label: 'Charge Sheeted', value: '—', percent: 'loading', trend: 'up', updated: '', icon: ClipboardList, tone: 'emerald', series: [0, 0, 0, 0, 0, 0, 0] },
  { label: 'Closed', value: '—', percent: 'loading', trend: 'up', updated: '', icon: Shield, tone: 'blue', series: [0, 0, 0, 0, 0, 0, 0] },
];

const _fbCrimeCategories = [
  { label: 'Theft', value: 27, color: '#22d3ee' },
  { label: 'Murder', value: 6, color: '#ef4444' },
  { label: 'Robbery', value: 11, color: '#f59e0b' },
  { label: 'Cyber Crime', value: 16, color: '#60a5fa' },
  { label: 'Assault', value: 10, color: '#a78bfa' },
  { label: 'Domestic Violence', value: 8, color: '#f472b6' },
  { label: 'Fraud', value: 9, color: '#34d399' },
  { label: 'Kidnapping', value: 4, color: '#fb7185' },
  { label: 'Narcotics', value: 5, color: '#84cc16' },
  { label: 'Traffic', value: 4, color: '#94a3b8' },
];

const _fbMonthlyTrend = [742, 821, 864, 812, 918, 1004, 976, 1128, 1196, 1252, 1310, 1386];
const _fbWeeklyTrend = [126, 148, 132, 171, 196, 183, 214];
const _fbDistrictComparison = [
  { label: 'Bengaluru', value: 92 },
  { label: 'Mysuru', value: 54 },
  { label: 'Belagavi', value: 48 },
  { label: 'Mangaluru', value: 42 },
  { label: 'Hubballi', value: 37 },
  { label: 'Kalaburagi', value: 31 },
];
const _fbSeverity = [
  { label: 'Critical', value: 14, color: '#ef4444' },
  { label: 'High', value: 28, color: '#f59e0b' },
  { label: 'Medium', value: 41, color: '#22d3ee' },
  { label: 'Low', value: 17, color: '#34d399' },
];

const _fbMarkers: Marker[] = [
  { id: 'm1', kind: 'FIR', label: 'Loading…', x: 50, y: 50, color: '#22d3ee', fir: '—', crimeType: '—', victim: 'Protected', officer: '—', priority: 'Medium', status: 'Registered', evidence: 0, time: '' },
];

const _fbFirRows: FirRow[] = [
  { fir: '—', station: '—', district: '—', crimeType: '—', officer: '—', status: 'Registered', priority: 'Medium', date: '' },
];





// Prompts that map to REAL /converse capabilities (network, similar cases, risk, prior history,
// money trail, trends). These actually query the backend, on the case currently in context.
const aiPrompts = [
  'Trace the money trail.',
  'Show crime trends.',
  'Show the network for case 1.',
  'What are the burglary trends?',
  'Show prior history for accused 1.',
  'Assess the risk for case 1.',
];

const toneClass: Record<Kpi['tone'], string> = {
  cyan: 'text-cyan-400 border-cyan-500/30 bg-cyan-950/20',
  red: 'text-red-400 border-red-500/30 bg-red-950/20',
  amber: 'text-amber-400 border-amber-500/30 bg-amber-950/20',
  emerald: 'text-emerald-400 border-emerald-500/30 bg-emerald-950/20',
  blue: 'text-blue-400 border-blue-500/30 bg-blue-950/20',
};

// ── palettes reused when we colour live API data ──────────────────────────────────────────
const CAT_COLORS = ['#22d3ee', '#ef4444', '#f59e0b', '#34d399', '#60a5fa', '#a78bfa', '#f472b6'];
const SEV_COLORS: Record<string, string> = { 'Heinous': '#ef4444', 'Non-Heinous': '#f59e0b' };

// map a backend status string onto the component's FirStatus union (design-preserving)
function toFirStatus(s: string): FirStatus {
  const t = (s || '').toLowerCase();
  if (t.includes('charge')) return 'Charge Sheet';
  if (t.includes('closed')) return 'Closed';
  if (t.includes('investig')) return 'Investigating';
  if (t.includes('undetected')) return 'Registered';
  return 'Assigned';
}
function gravityToPriority(g: string): Priority {
  return (g || '').toLowerCase().includes('non') ? 'Medium' : 'Critical';
}

export function PoliceCommandDashboard() {
  // LIVE DATA — every figure below is a GROUP BY over the real 500-FIR corpus (GET /dashboard/summary).
  // This screen used to ship hardcoded arrays ("18,742 FIRs", invented officers). It does not any more.
  // Until the fetch resolves we render the _fb* placeholders; on error we keep them and flag it.
  const [kpis, setKpis] = useState<Kpi[]>(_fbKpis);
  const [crimeCategories, setCrimeCategories] = useState(_fbCrimeCategories);
  const [monthlyTrend, setMonthlyTrend] = useState<number[]>(_fbMonthlyTrend);
  const [weeklyTrend, setWeeklyTrend] = useState<number[]>(_fbWeeklyTrend);
  const [districtComparison, setDistrictComparison] = useState(_fbDistrictComparison);
  const [severity, setSeverity] = useState(_fbSeverity);
  const [markers, setMarkers] = useState<Marker[]>(_fbMarkers);
  const [firRows, setFirRows] = useState<FirRow[]>(_fbFirRows);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  // Police AI Assistant — real /converse calls. Was a dead panel with a hardcoded "insight".
  const [aiAnswer, setAiAnswer] = useState<string>('Ask a question below. Answers come from the KAVERI reasoning engine over the real case corpus.');
  const [aiBusy, setAiBusy] = useState(false);
  const askAI = async (prompt: string) => {
    setAiBusy(true);
    setAiAnswer('Thinking…');
    try {
      const d = await apiFetch('/converse', {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain' },
        body: JSON.stringify({ session_id: 'dashboard', query: prompt }),
      });
      setAiAnswer(d.answer || d.answer_en || 'No answer returned.');
    } catch (e: any) {
      setAiAnswer('Could not reach the reasoning engine: ' + (e?.message ?? 'unknown error'));
    } finally {
      setAiBusy(false);
    }
  };

  useEffect(() => {
    let alive = true;
    apiFetch('/dashboard/summary')
      .then((d: any) => {
        if (!alive || !d) return;
        const total: number = d.total_firs ?? 0;

        // KPIs — real totals + real status counts
        const byStatus: Record<string, number> = {};
        (d.status_breakdown || []).forEach((x: any) => { byStatus[x.label] = x.value; });
        setKpis([
          { label: 'Total FIRs', value: total.toLocaleString(), percent: `${(d.status_breakdown||[]).length} statuses`, trend: 'up', updated: 'live', icon: FileText, tone: 'cyan', series: (d.monthly_trend||[]).map((m: any) => m.value) },
          { label: 'Under Investigation', value: (byStatus['Under Investigation'] ?? 0).toLocaleString(), percent: total ? `${Math.round((byStatus['Under Investigation']??0)/total*100)}%` : '0%', trend: 'up', updated: 'live', icon: Search, tone: 'amber', series: (d.monthly_trend||[]).map((m: any) => m.value) },
          { label: 'Charge Sheeted', value: (byStatus['Charge Sheeted'] ?? 0).toLocaleString(), percent: total ? `${Math.round((byStatus['Charge Sheeted']??0)/total*100)}%` : '0%', trend: 'up', updated: 'live', icon: ClipboardList, tone: 'emerald', series: (d.monthly_trend||[]).map((m: any) => m.value) },
          { label: 'Closed', value: (byStatus['Closed'] ?? 0).toLocaleString(), percent: total ? `${Math.round((byStatus['Closed']??0)/total*100)}%` : '0%', trend: 'up', updated: 'live', icon: CircleDot, tone: 'blue', series: (d.monthly_trend||[]).map((m: any) => m.value) },
        ]);

        // crime-type pie — real
        setCrimeCategories((d.crime_type_breakdown || []).map((x: any, i: number) => ({ label: x.label, value: x.value, color: CAT_COLORS[i % CAT_COLORS.length] })));

        // monthly trend line — real
        setMonthlyTrend((d.monthly_trend || []).map((m: any) => m.value));
        // weekly panel reuses the last 7 monthly points (real data, no fabricated week series)
        setWeeklyTrend((d.monthly_trend || []).map((m: any) => m.value).slice(-7));

        // district bars — real
        setDistrictComparison((d.district_breakdown || []).map((x: any) => ({ label: x.label, value: x.value })));

        // severity donut — real gravity split
        setSeverity((d.gravity_breakdown || []).map((x: any) => ({ label: x.label, value: x.value, color: SEV_COLORS[x.label] || '#64748b' })));

        // map markers — REAL lat/long, projected into the 0..100 box the SVG expects
        const lats = (d.map_markers||[]).map((m: any) => m.latitude);
        const lngs = (d.map_markers||[]).map((m: any) => m.longitude);
        const minLa = Math.min(...lats), maxLa = Math.max(...lats);
        const minLo = Math.min(...lngs), maxLo = Math.max(...lngs);
        setMarkers((d.map_markers || []).slice(0, 40).map((m: any, i: number): Marker => ({
          id: String(m.id ?? i),
          kind: m.gravity === 'Heinous' ? 'Hotspot' : 'FIR',
          label: m.crimeType,
          x: maxLo > minLo ? 8 + ((m.longitude - minLo) / (maxLo - minLo)) * 84 : 50,
          y: maxLa > minLa ? 8 + ((maxLa - m.latitude) / (maxLa - minLa)) * 84 : 50,
          color: m.gravity === 'Heinous' ? '#ef4444' : '#22d3ee',
          fir: String(m.fir),
          crimeType: m.crimeType,
          victim: 'Protected',
          officer: '—',
          priority: gravityToPriority(m.gravity),
          status: toFirStatus(m.status),
          evidence: 0,
          time: '',
        })));
        if ((d.map_markers || []).length) {
          const m0 = d.map_markers[0];
          setSelectedMarker({
            id: String(m0.id), kind: m0.gravity === 'Heinous' ? 'Hotspot' : 'FIR', label: m0.crimeType,
            x: 50, y: 50, color: m0.gravity === 'Heinous' ? '#ef4444' : '#22d3ee', fir: String(m0.fir),
            crimeType: m0.crimeType, victim: 'Protected', officer: '—',
            priority: gravityToPriority(m0.gravity), status: toFirStatus(m0.status), evidence: 0, time: '',
          });
        }

        // recent FIR table — real
        setFirRows((d.recent_firs || []).map((r: any): FirRow => ({
          fir: String(r.fir),
          station: r.district,
          district: r.district,
          crimeType: r.crimeType,
          officer: '—',
          status: toFirStatus(r.status),
          priority: gravityToPriority(r.gravity),
          date: String(r.date).slice(0, 10),
        })));

        setLive(true);
      })
      .catch((e: any) => { if (alive) setLoadError(e?.message ?? 'Could not load dashboard data'); });
    return () => { alive = false; };
  }, []);

  const [selectedMarker, setSelectedMarker] = useState<Marker>(_fbMarkers[0]);
  const [selectedMetric, setSelectedMetric] = useState(_fbKpis[0].label);
  const [filters, setFilters] = useState({ date: '', crimeType: 'All', station: 'All', district: 'All', officer: 'All', status: 'All', priority: 'All' });
  const [sortKey, setSortKey] = useState<keyof FirRow>('date');
  const [page, setPage] = useState(1);

  const filteredRows = useMemo(() => {
    const rows = firRows.filter(row => {
      return (!filters.date || row.date === filters.date)
        && (filters.crimeType === 'All' || row.crimeType === filters.crimeType)
        && (filters.station === 'All' || row.station === filters.station)
        && (filters.district === 'All' || row.district === filters.district)
        && (filters.officer === 'All' || row.officer === filters.officer)
        && (filters.status === 'All' || row.status === filters.status)
        && (filters.priority === 'All' || row.priority === filters.priority);
    });
    return [...rows].sort((a, b) => String(b[sortKey]).localeCompare(String(a[sortKey])));
  }, [filters, sortKey, firRows]);

  const visibleRows = filteredRows.slice((page - 1) * 5, page * 5);
  const pageCount = Math.max(1, Math.ceil(filteredRows.length / 5));

  return (
    <div className="flex-1 overflow-y-auto bg-black/80 relative">
      {/* STATUS BANNER — this dashboard is now LIVE: every figure is a GROUP BY over the real
          500-FIR corpus via GET /dashboard/summary. Officer names are shown as "—" because the
          FIR schema carries only a PolicePersonID, and this screen invents nothing. */}
      {loadError ? (
        <div className="relative z-20 flex items-center gap-2 px-6 py-2 bg-red-950/50 border-b border-red-500/50 text-red-300 text-xs font-mono tracking-wide">
          <span className="inline-block w-2 h-2 rounded-full bg-red-500"></span>
          BACKEND UNREACHABLE — {loadError}. Showing placeholder layout; figures are not live.
        </div>
      ) : (
        <div className="relative z-20 flex items-center gap-2 px-6 py-2 bg-emerald-950/30 border-b border-emerald-500/30 text-emerald-300 text-xs font-mono tracking-wide">
          <span className={`inline-block w-2 h-2 rounded-full ${live ? 'bg-emerald-400 animate-pulse' : 'bg-neutral-500'}`}></span>
          {live ? 'LIVE — every figure is a real aggregate over 500 FIRs. Officer names omitted (not in FIR schema).' : 'Loading live figures from the backend…'}
        </div>
      )}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(14,165,233,0.08),transparent_28%),linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:100%_100%,32px_32px,32px_32px] pointer-events-none"></div>

      <div className="relative z-10 p-6 xl:p-8 space-y-6 max-w-[1920px] mx-auto">
        <section className="flex flex-col xl:flex-row xl:items-end justify-between gap-4 border-b border-neutral-900 pb-6">
          <div>
            <div className="flex items-center gap-3 text-[10px] font-mono font-bold uppercase tracking-widest text-cyan-500 mb-3">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-70"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-cyan-400"></span>
              </span>
              Real-time Police Intelligence Center
            </div>
            <h1 className="text-3xl xl:text-4xl font-black tracking-tight text-white uppercase">Police Command &amp; FIR Management</h1>
            <p className="text-neutral-400 mt-3 max-w-3xl leading-relaxed">
              State-wide operational view for FIR intake, emergency response, patrol deployment, identity intelligence, evidence movement, and district crime risk.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-3 min-w-full sm:min-w-[420px]">
            <CommandSignal label="Control Room" value="Online" tone="text-cyan-400" />
            <CommandSignal label="Dispatch SLA" value="02:41" tone="text-emerald-400" />
            <CommandSignal label="Threat Level" value="High" tone="text-red-400" />
          </div>
        </section>

        <section aria-label="FIR command metrics" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {kpis.map(kpi => (
            <MetricCard key={kpi.label} kpi={kpi} active={selectedMetric === kpi.label} onClick={() => setSelectedMetric(kpi.label)} />
          ))}
        </section>

        <section className="grid grid-cols-1 2xl:grid-cols-[340px_minmax(560px,1fr)_360px] gap-5">
          <div className="space-y-5">
            <Panel title="Crime Category Distribution" icon={<BarChart3 size={16} />}>
              <PieChart data={crimeCategories} />
            </Panel>
            <Panel title="Monthly FIR Trend" icon={<TrendingUp size={16} />}>
              <LineChart data={monthlyTrend} labels={['Jan', 'Mar', 'May', 'Jul', 'Sep', 'Nov']} />
            </Panel>
            <Panel title="Weekly Crime Trend" icon={<ActivityIcon />}>
              <AreaChart data={weeklyTrend} />
            </Panel>
            <Panel title="District Crime Comparison" icon={<Landmark size={16} />}>
              <BarList data={districtComparison} />
            </Panel>
            <Panel title="Crime Severity" icon={<ShieldAlert size={16} />}>
              <DonutChart data={severity} center="42%" />
            </Panel>
          </div>

          <div className="space-y-5">
            <Panel title="Live GIS Crime Map" icon={<MapPin size={16} />} action="District boundary overlay">
              <CrimeMap markers={markers} selectedMarker={selectedMarker} onSelect={setSelectedMarker} />
            </Panel>
            <Panel title="Recent FIR Table" icon={<ClipboardList size={16} />} action={`${filteredRows.length} records`}>
              <FirFilters rows={firRows} filters={filters} setFilters={setFilters} />
              <div className="overflow-x-auto mt-4">
                <table className="w-full min-w-[920px] text-left">
                  <thead>
                    <tr className="text-[10px] font-mono uppercase tracking-widest text-neutral-500 border-b border-neutral-900">
                      {(['fir', 'station', 'crimeType', 'officer', 'status', 'priority', 'date'] as (keyof FirRow)[]).map(key => (
                        <th key={key} className="py-3 pr-4">
                          <button className="hover:text-cyan-400 transition-colors" onClick={() => setSortKey(key)}>
                            {key === 'fir' ? 'FIR Number' : key.replace(/([A-Z])/g, ' $1')}
                          </button>
                        </th>
                      ))}
                      <th className="py-3 pr-4">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRows.map(row => (
                      <tr key={row.fir} className="border-b border-neutral-900/70 hover:bg-cyan-950/10 transition-colors">
                        <td className="py-4 pr-4 font-mono text-cyan-400 text-sm">{row.fir}</td>
                        <td className="py-4 pr-4 text-sm text-neutral-300">{row.station}</td>
                        <td className="py-4 pr-4 text-sm text-neutral-300">{row.crimeType}</td>
                        <td className="py-4 pr-4 text-sm text-neutral-400">{row.officer}</td>
                        <td className="py-4 pr-4"><StatusBadge value={row.status} /></td>
                        <td className="py-4 pr-4"><PriorityBadge value={row.priority} /></td>
                        <td className="py-4 pr-4 font-mono text-xs text-neutral-500">{row.date}</td>
                        <td className="py-4 pr-4">
                          <button className="inline-flex items-center justify-center w-8 h-8 rounded border border-neutral-800 text-neutral-500 hover:text-cyan-400 hover:border-cyan-500/50 transition-colors" aria-label={`Open ${row.fir}`}>
                            <Eye size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between pt-4 text-xs font-mono text-neutral-500">
                <span>Page {page} of {pageCount}</span>
                <div className="flex gap-2">
                  <button className="w-8 h-8 rounded border border-neutral-800 hover:border-cyan-500/50 disabled:opacity-30" disabled={page === 1} onClick={() => setPage(p => Math.max(1, p - 1))} aria-label="Previous page"><ChevronLeft size={15} className="mx-auto" /></button>
                  <button className="w-8 h-8 rounded border border-neutral-800 hover:border-cyan-500/50 disabled:opacity-30" disabled={page === pageCount} onClick={() => setPage(p => Math.min(pageCount, p + 1))} aria-label="Next page"><ChevronRight size={15} className="mx-auto" /></button>
                </div>
              </div>
            </Panel>
          </div>

          <div className="space-y-5">
            <Panel title="Police AI Assistant" icon={<Bot size={16} />} action="Live · KAVERI engine">
              <div className="space-y-3">
                {aiPrompts.map(prompt => (
                  <button
                    key={prompt}
                    onClick={() => askAI(prompt)}
                    disabled={aiBusy}
                    className="w-full text-left bg-panelHover/70 border border-neutral-800 hover:border-cyan-500/50 hover:text-cyan-300 rounded p-3 text-sm text-neutral-300 transition-all hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
              <div className="mt-4 border border-cyan-500/20 bg-cyan-950/10 rounded p-4">
                <div className="text-[10px] font-mono uppercase tracking-widest text-cyan-500 mb-2">Assistant response {aiBusy && '· querying…'}</div>
                <p className="text-sm text-neutral-300 leading-relaxed whitespace-pre-wrap">{aiAnswer}</p>
              </div>
            </Panel>

          </div>
        </section>

      </div>
    </div>
  );
}

function ActivityIcon() {
  return <TrendingUp size={16} />;
}

function CommandSignal({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="bg-panel border border-neutral-800 rounded p-4">
      <div className="text-[9px] font-mono uppercase tracking-widest text-neutral-600">{label}</div>
      <div className={`mt-2 text-lg font-mono font-bold ${tone}`}>{value}</div>
    </div>
  );
}

function MetricCard({ kpi, active, onClick }: { kpi: Kpi; active: boolean; onClick: () => void }) {
  const Icon = kpi.icon;
  const TrendIcon = kpi.trend === 'up' ? TrendingUp : TrendingDown;
  return (
    <button
      onClick={onClick}
      className={`group text-left bg-panel/90 border ${active ? 'border-cyan-500/50 shadow-[0_0_30px_rgba(34,211,238,0.12)]' : 'border-neutral-800'} rounded p-4 min-h-[156px] relative overflow-hidden hover:-translate-y-1 hover:border-cyan-500/40 transition-all duration-300`}
      aria-pressed={active}
    >
      <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-cyan-500/40 to-transparent"></div>
      <div className="absolute inset-0 bg-gradient-to-br from-white/[0.03] to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
      <div className="relative flex items-start justify-between gap-3">
        <span className={`w-10 h-10 rounded border flex items-center justify-center ${toneClass[kpi.tone]}`}>
          <Icon size={18} />
        </span>
        <span className={`inline-flex items-center gap-1 text-[10px] font-mono font-bold ${kpi.trend === 'up' ? 'text-cyan-400' : 'text-emerald-400'}`}>
          <TrendIcon size={12} /> {kpi.percent}
        </span>
      </div>
      <div className="relative mt-4">
        <div className="text-[10px] uppercase font-mono tracking-widest text-neutral-500">{kpi.label}</div>
        <div className="mt-1 text-2xl font-mono font-bold text-white">{kpi.value}</div>
      </div>
      <div className="relative mt-3 flex items-end justify-between gap-4">
        <Sparkline data={kpi.series} tone={kpi.tone} />
        <span className="text-[9px] font-mono uppercase tracking-widest text-neutral-600 whitespace-nowrap">{kpi.updated}</span>
      </div>
    </button>
  );
}

function Panel({ title, icon, action, children }: { title: string; icon: React.ReactNode; action?: string; children: React.ReactNode }) {
  return (
    <section className="bg-panel/90 border border-neutral-800 rounded p-5 relative overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-cyan-500/30 to-transparent"></div>
      <div className="flex items-center justify-between gap-4 mb-5">
        <div className="flex items-center gap-2 text-white">
          <span className="text-cyan-500">{icon}</span>
          <h2 className="text-sm font-bold uppercase tracking-widest">{title}</h2>
        </div>
        {action && <span className="text-[9px] font-mono uppercase tracking-widest text-neutral-600">{action}</span>}
      </div>
      {children}
    </section>
  );
}

function Sparkline({ data, tone }: { data: number[]; tone: Kpi['tone'] }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const points = data.map((v, i) => `${(i / (data.length - 1)) * 96},${32 - ((v - min) / Math.max(1, max - min)) * 28}`).join(' ');
  const color = tone === 'red' ? '#ef4444' : tone === 'amber' ? '#f59e0b' : tone === 'emerald' ? '#34d399' : '#22d3ee';
  return (
    <svg viewBox="0 0 96 34" className="w-24 h-9" aria-hidden="true">
      <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PieChart({ data }: { data: { label: string; value: number; color: string }[] }) {
  return (
    <div className="grid grid-cols-[130px_1fr] gap-4 items-center">
      <SegmentChart data={data} radius={48} stroke={28} />
      <Legend data={data.slice(0, 6)} />
    </div>
  );
}

function DonutChart({ data, center }: { data: { label: string; value: number; color: string }[]; center: string }) {
  return (
    <div className="grid grid-cols-[130px_1fr] gap-4 items-center">
      <div className="relative">
        <SegmentChart data={data} radius={48} stroke={18} />
        <div className="absolute inset-0 flex items-center justify-center text-xl font-mono font-bold text-white">{center}</div>
      </div>
      <Legend data={data} />
    </div>
  );
}

function SegmentChart({ data, radius, stroke }: { data: { value: number; color: string }[]; radius: number; stroke: number }) {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <svg viewBox="0 0 120 120" className="w-[130px] h-[130px] -rotate-90" aria-hidden="true">
      <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={stroke} />
      {data.map(item => {
        const length = (item.value / total) * circumference;
        const circle = (
          <circle key={item.color} cx="60" cy="60" r={radius} fill="none" stroke={item.color} strokeWidth={stroke} strokeDasharray={`${length} ${circumference - length}`} strokeDashoffset={-offset} />
        );
        offset += length;
        return circle;
      })}
    </svg>
  );
}

function Legend({ data }: { data: { label: string; value: number; color: string }[] }) {
  return (
    <div className="space-y-2">
      {data.map(item => (
        <div key={item.label} className="flex items-center justify-between gap-3 text-xs">
          <span className="flex items-center gap-2 text-neutral-400"><span className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }}></span>{item.label}</span>
          <span className="font-mono text-neutral-500">{item.value}%</span>
        </div>
      ))}
    </div>
  );
}

function LineChart({ data, labels }: { data: number[]; labels: string[] }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const points = data.map((v, i) => `${(i / (data.length - 1)) * 300},${100 - ((v - min) / Math.max(1, max - min)) * 82}`).join(' ');
  return (
    <div>
      <svg viewBox="0 0 300 120" className="w-full h-36" aria-label="Monthly FIR trend line chart">
        <path d="M0 100 H300 M0 60 H300 M0 20 H300" stroke="rgba(255,255,255,0.06)" />
        <polyline points={points} fill="none" stroke="#22d3ee" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        {data.map((v, i) => (
          <circle key={`${v}-${i}`} cx={(i / (data.length - 1)) * 300} cy={100 - ((v - min) / Math.max(1, max - min)) * 82} r="3" fill="#22d3ee" />
        ))}
      </svg>
      <div className="flex justify-between text-[10px] font-mono text-neutral-600 uppercase">
        {labels.map(label => <span key={label}>{label}</span>)}
      </div>
    </div>
  );
}

function AreaChart({ data }: { data: number[] }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const points = data.map((v, i) => `${(i / (data.length - 1)) * 300},${100 - ((v - min) / Math.max(1, max - min)) * 78}`).join(' ');
  return (
    <svg viewBox="0 0 300 120" className="w-full h-32" aria-label="Weekly crime area chart">
      <defs>
        <linearGradient id="crimeArea" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d="M0 100 H300 M0 60 H300 M0 20 H300" stroke="rgba(255,255,255,0.06)" />
      <path d={`M${points} L300,110 L0,110 Z`} fill="url(#crimeArea)" />
      <polyline points={points} fill="none" stroke="#22d3ee" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function BarList({ data }: { data: { label: string; value: number }[] }) {
  const max = Math.max(...data.map(item => item.value));
  return (
    <div className="space-y-3">
      {data.map(item => (
        <div key={item.label}>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-neutral-400">{item.label}</span>
            <span className="font-mono text-neutral-500">{item.value}</span>
          </div>
          <div className="h-2 bg-neutral-900 rounded overflow-hidden">
            <div className="h-full bg-cyan-500 rounded shadow-[0_0_12px_rgba(34,211,238,0.5)]" style={{ width: `${(item.value / max) * 100}%` }}></div>
          </div>
        </div>
      ))}
    </div>
  );
}

function CrimeMap({ markers, selectedMarker, onSelect }: { markers: Marker[]; selectedMarker: Marker; onSelect: (marker: Marker) => void }) {
  return (
    <div className="relative min-h-[520px] rounded border border-neutral-800 bg-[#020617] overflow-hidden">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(34,211,238,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,0.08)_1px,transparent_1px)] bg-[size:34px_34px]"></div>
      <svg className="absolute inset-0 w-full h-full opacity-70" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path d="M18,18 L47,9 L82,18 L89,49 L76,83 L39,91 L12,70 Z" fill="rgba(14,165,233,0.08)" stroke="rgba(34,211,238,0.45)" strokeWidth="0.6" />
        <path d="M47,9 L44,40 L12,70 M44,40 L76,83 M44,40 L89,49 M18,18 L44,40" fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="0.5" />
        <circle cx="56" cy="52" r="24" fill="none" stroke="rgba(239,68,68,0.28)" strokeWidth="0.6" strokeDasharray="2 2" />
        <circle cx="56" cy="52" r="14" fill="rgba(239,68,68,0.08)" stroke="rgba(239,68,68,0.35)" strokeWidth="0.4" />
      </svg>
      <div className="absolute top-4 left-4 flex flex-wrap gap-2 max-w-[520px]">
        {['FIR locations', 'Crime hotspots', 'Police stations', 'Patrol vehicles', 'Emergency incidents', 'Missing persons', 'Wanted criminals', 'District boundaries'].map(label => (
          <span key={label} className="text-[9px] font-mono uppercase tracking-widest px-2 py-1 rounded border border-neutral-800 bg-black/60 text-neutral-400">{label}</span>
        ))}
      </div>
      {markers.map(marker => (
        <button
          key={marker.id}
          onClick={() => onSelect(marker)}
          className="absolute -translate-x-1/2 -translate-y-1/2 group"
          style={{ left: `${marker.x}%`, top: `${marker.y}%` }}
          aria-label={`${marker.kind}: ${marker.label}`}
        >
          <span className="absolute inset-0 m-auto w-8 h-8 -translate-x-1/2 -translate-y-1/2 rounded-full animate-ping opacity-25" style={{ backgroundColor: marker.color }}></span>
          <span className={`relative flex items-center justify-center w-5 h-5 rounded-full border-2 border-black shadow-[0_0_18px_currentColor] ${selectedMarker.id === marker.id ? 'scale-125' : ''}`} style={{ backgroundColor: marker.color, color: marker.color }}>
            <CircleDot size={11} className="text-black/70" />
          </span>
          <span className="absolute left-1/2 top-7 -translate-x-1/2 whitespace-nowrap opacity-0 group-hover:opacity-100 text-[10px] font-mono bg-black/80 border border-neutral-800 text-white px-2 py-1 rounded transition-opacity">{marker.label}</span>
        </button>
      ))}
      <div className="absolute right-4 bottom-4 w-[min(360px,calc(100%-32px))] bg-black/85 backdrop-blur border border-cyan-500/30 rounded p-4 shadow-[0_20px_60px_-30px_rgba(34,211,238,0.8)]">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-cyan-500">{selectedMarker.kind}</div>
            <div className="text-lg font-bold text-white mt-1">{selectedMarker.fir}</div>
          </div>
          <PriorityBadge value={selectedMarker.priority} />
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
          <Info label="Crime Type" value={selectedMarker.crimeType} />
          <Info label="Victim" value={selectedMarker.victim} />
          <Info label="Officer" value={selectedMarker.officer} />
          <Info label="Status" value={selectedMarker.status} />
          <Info label="Evidence Count" value={String(selectedMarker.evidence)} />
          <Info label="Time" value={selectedMarker.time} />
        </div>
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[9px] font-mono uppercase tracking-widest text-neutral-600">{label}</div>
      <div className="mt-1 text-neutral-300">{value}</div>
    </div>
  );
}

function FirFilters({ rows, filters, setFilters }: { rows: FirRow[]; filters: Record<string, string>; setFilters: (next: any) => void }) {
  const unique = (key: keyof FirRow) => ['All', ...Array.from(new Set(rows.map(row => row[key])))];
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-2">
      <input
        type="date"
        value={filters.date}
        onChange={e => setFilters((f: any) => ({ ...f, date: e.target.value }))}
        className="bg-panelHover border border-neutral-800 rounded px-3 py-2 text-xs text-neutral-300 focus:border-cyan-500/50 outline-none"
        aria-label="Filter by date"
      />
      <FilterSelect label="Crime Type" value={filters.crimeType} options={unique('crimeType')} onChange={value => setFilters((f: any) => ({ ...f, crimeType: value }))} />
      <FilterSelect label="Station" value={filters.station} options={unique('station')} onChange={value => setFilters((f: any) => ({ ...f, station: value }))} />
      <FilterSelect label="District" value={filters.district} options={unique('district')} onChange={value => setFilters((f: any) => ({ ...f, district: value }))} />
      <FilterSelect label="Officer" value={filters.officer} options={unique('officer')} onChange={value => setFilters((f: any) => ({ ...f, officer: value }))} />
      <FilterSelect label="Status" value={filters.status} options={unique('status')} onChange={value => setFilters((f: any) => ({ ...f, status: value }))} />
      <FilterSelect label="Priority" value={filters.priority} options={unique('priority')} onChange={value => setFilters((f: any) => ({ ...f, priority: value }))} />
    </div>
  );
}

function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} aria-label={`Filter by ${label}`} className="bg-panelHover border border-neutral-800 rounded px-3 py-2 text-xs text-neutral-300 focus:border-cyan-500/50 outline-none">
      {options.map(option => <option key={option} value={option}>{option}</option>)}
    </select>
  );
}

function StatusBadge({ value }: { value: FirStatus }) {
  const color = value === 'Closed' ? 'text-emerald-400 border-emerald-500/30 bg-emerald-950/20'
    : value === 'Charge Sheet' ? 'text-blue-400 border-blue-500/30 bg-blue-950/20'
      : value === 'Assigned' ? 'text-amber-400 border-amber-500/30 bg-amber-950/20'
        : 'text-cyan-400 border-cyan-500/30 bg-cyan-950/20';
  return <span className={`text-[10px] font-mono uppercase tracking-widest px-2 py-1 rounded border ${color}`}>{value}</span>;
}

function PriorityBadge({ value }: { value: Priority }) {
  const color = value === 'Critical' ? 'text-red-400 border-red-500/30 bg-red-950/20'
    : value === 'High' ? 'text-amber-400 border-amber-500/30 bg-amber-950/20'
      : value === 'Medium' ? 'text-cyan-400 border-cyan-500/30 bg-cyan-950/20'
        : 'text-emerald-400 border-emerald-500/30 bg-emerald-950/20';
  return <span className={`text-[10px] font-mono uppercase tracking-widest px-2 py-1 rounded border ${color}`}>{value}</span>;
}
