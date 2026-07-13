import React from 'react';

export function TheNumbersView() {
  return (
    <div className="flex-1 bg-bg-base flex items-center justify-center animate-in fade-in slide-in-from-bottom-4 duration-500 p-10">
      <div className="w-full max-w-6xl text-center">
        <h1 className="text-4xl md:text-5xl font-bold tracking-tighter text-text-primary mb-24 uppercase">
          Identity Collisions
        </h1>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-16 mb-24">
          <div className="flex flex-col items-center">
            <div className="text-7xl font-light text-status-critical mb-4">2,277</div>
            <div className="text-xl font-medium text-text-secondary uppercase tracking-widest">Naive SQL</div>
            <div className="text-sm text-text-muted mt-2">Exact name matches leading to false merges.</div>
          </div>
          
          <div className="flex flex-col items-center">
            <div className="text-7xl font-light text-status-warning mb-4">2,369</div>
            <div className="text-xl font-medium text-text-secondary uppercase tracking-widest">Fuzzy Matcher</div>
            <div className="text-sm text-text-muted mt-2">Soundex / Levenshtein over-correcting.</div>
          </div>

          <div className="flex flex-col items-center">
            <div className="text-7xl font-medium text-status-success mb-4">0</div>
            <div className="text-xl font-bold text-text-primary uppercase tracking-widest">KAVERI</div>
            <div className="text-sm text-text-muted mt-2">Zero unevidenced identity merges.</div>
          </div>
        </div>

        <div className="text-2xl text-text-muted font-medium max-w-3xl mx-auto leading-relaxed italic border-t border-border-subtle pt-12">
          "Being cleverer about names makes it worse. The problem is deciding on a name at all."
        </div>
      </div>
    </div>
  );
}
