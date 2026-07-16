
export function TheNumbersView() {
  return (
    <div className="flex-1 bg-black text-neutral-300 flex flex-col relative overflow-hidden font-sans">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:32px_32px] pointer-events-none z-0"></div>
      
      <div className="relative z-10 flex-1 flex flex-col items-center justify-center p-12">
        <div className="w-full max-w-6xl">
          <div className="text-center mb-24">
            <div className="text-cyan-500 text-sm font-mono font-bold tracking-[0.3em] uppercase mb-4 shadow-[0_0_10px_rgba(34,211,238,0.3)] inline-block border border-cyan-500/30 px-4 py-1.5 bg-cyan-950/20 rounded">
              Performance Telemetry
            </div>
            <h1 className="text-5xl md:text-6xl font-black tracking-tight text-white uppercase">
              Identity Collisions
            </h1>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-24">
            <div className="flex flex-col items-center bg-panel border border-neutral-800 rounded p-12 relative overflow-hidden group hover:-translate-y-2 hover:shadow-[0_15px_40px_-15px_rgba(239,68,68,0.3)] transition-all duration-300 cursor-default">
              <div className="absolute top-0 left-0 w-full h-[2px] bg-red-500 shadow-[0_0_15px_rgba(239,68,68,1)] group-hover:h-[4px] transition-all duration-300"></div>
              <div className="text-7xl font-light text-red-500 mb-6 font-mono group-hover:scale-110 transition-transform duration-500 group-hover:drop-shadow-[0_0_20px_rgba(239,68,68,0.5)]">2,277</div>
              <div className="text-xl font-bold text-white uppercase tracking-widest mb-3">Naive SQL</div>
              <div className="text-sm font-mono text-neutral-500 uppercase tracking-widest text-center group-hover:text-neutral-400 transition-colors">Exact name matches leading to false merges.</div>
            </div>
            
            <div className="flex flex-col items-center bg-panel border border-neutral-800 rounded p-12 relative overflow-hidden group hover:-translate-y-2 hover:shadow-[0_15px_40px_-15px_rgba(245,158,11,0.3)] transition-all duration-300 cursor-default">
              <div className="absolute top-0 left-0 w-full h-[2px] bg-amber-500 shadow-[0_0_15px_rgba(245,158,11,1)] group-hover:h-[4px] transition-all duration-300"></div>
              <div className="text-7xl font-light text-amber-500 mb-6 font-mono group-hover:scale-110 transition-transform duration-500 group-hover:drop-shadow-[0_0_20px_rgba(245,158,11,0.5)]">2,369</div>
              <div className="text-xl font-bold text-white uppercase tracking-widest mb-3">Fuzzy Matcher</div>
              <div className="text-sm font-mono text-neutral-500 uppercase tracking-widest text-center group-hover:text-neutral-400 transition-colors">Soundex / Levenshtein over-correcting.</div>
            </div>

            <div className="flex flex-col items-center bg-cyan-950/10 border border-cyan-900/50 rounded p-12 relative overflow-hidden group hover:-translate-y-2 hover:shadow-[0_20px_50px_-15px_rgba(34,211,238,0.4),inset_0_0_30px_rgba(34,211,238,0.1)] transition-all duration-500 cursor-default">
              <div className="absolute top-0 left-0 w-full h-[2px] bg-cyan-400 shadow-[0_0_15px_rgba(34,211,238,1)] group-hover:h-[4px] transition-all duration-300"></div>
              <div className="absolute inset-0 bg-cyan-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
              <div className="text-7xl font-bold text-cyan-400 mb-6 font-mono group-hover:scale-110 transition-transform duration-500 drop-shadow-[0_0_10px_rgba(34,211,238,0.2)] group-hover:drop-shadow-[0_0_30px_rgba(34,211,238,0.8)]">0</div>
              <div className="text-xl font-black text-white uppercase tracking-[0.2em] mb-3">KAVERI</div>
              <div className="text-sm font-mono text-cyan-500/80 uppercase tracking-widest text-center font-bold">Zero unevidenced identity merges.</div>
            </div>
          </div>

          <div className="max-w-3xl mx-auto border border-neutral-800 bg-panel p-8 rounded relative overflow-hidden">
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-cyan-500/50"></div>
            <div className="text-2xl text-white font-light leading-relaxed font-serif italic text-center">
              "Being cleverer about names makes it worse. The problem is deciding on a name at all."
            </div>
            <div className="text-right mt-4 text-xs font-mono uppercase tracking-widest text-neutral-500">
              — Catalyst Analytics
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
