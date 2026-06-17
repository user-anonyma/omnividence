'use client';

import ResultCard from '@/components/ResultCard';

// ResultsGrid
// Props: { results: Result[]; searchId: string; notes?: string[] }
//
// Responsive grid of ResultCard. The empty state shows the backend note(s)
// honestly (e.g. "google_lens: provider not configured") rather than implying a
// failed search or fabricating results.

export default function ResultsGrid({ results, searchId, notes }) {
  const hasResults = Array.isArray(results) && results.length > 0;

  if (!hasResults) {
    return (
      <div className="omni-empty">
        <p className="omni-empty__head">No results to show.</p>
        {Array.isArray(notes) && notes.length > 0 ? (
          <ul className="omni-empty__notes">
            {notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        ) : (
          <p className="omni-empty__sub">
            No public image results were returned for this face.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="card2-grid">
      {results.map((r) => (
        <ResultCard
          key={r.id ?? `${r.provider}:${r.image_url}`}
          result={r}
          searchId={searchId}
        />
      ))}
    </div>
  );
}
