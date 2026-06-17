'use client';

import { useMemo, useState } from 'react';
import Uploader from '@/components/Uploader';
import ResultsGrid from '@/components/ResultsGrid';
import FilterSort from '@/components/FilterSort';
import LoadMore from '@/components/LoadMore';
import DetectionPanel from '@/components/DetectionPanel';

// Main search page. Holds search state and wires the pipeline:
//   Uploader -> SearchResponse -> FilterSort + ResultsGrid + LoadMore
//   plus an optional, toggle-gated DetectionPanel (experimental forensics).
// This page never constructs identity language; it only renders backend data.

const DEFAULT_FILTER = { provider: 'all', band: 'all', sort: 'score_desc' };

export default function HomePage() {
  // The uploaded file, if the Uploader surfaces it (the experimental
  // DetectionPanel consumes it). With the current Uploader contract the file is
  // not surfaced to the parent, so this stays null and the panel shows its
  // "choose an image" state — see the documented limitation in the handoff.
  const [file] = useState(null);
  // The full SearchResponse from the backend (or null before first search).
  const [search, setSearch] = useState(null);
  // Accumulated results across the initial search + every "load more" batch.
  const [results, setResults] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState(DEFAULT_FILTER);
  const [detectionEnabled, setDetectionEnabled] = useState(false);

  // Honest notes from the backend (e.g. "yandex: provider not configured").
  const notes = search?.note || [];
  const searchId = search?.search_id || '';

  // ---- handlers --------------------------------------------------------------

  function handleResult(res) {
    setSearch(res);
    setResults(Array.isArray(res?.results) ? res.results : []);
    setHasMore(Boolean(res?.has_more));
    setFilter(DEFAULT_FILTER);
    setError('');
    setBusy(false);
  }

  function handleError(msg) {
    setError(msg || 'Something went wrong.');
    setBusy(false);
  }

  // LoadMore reports the newly-added results and the updated has_more flag.
  function handleMore(newResults, more) {
    if (Array.isArray(newResults) && newResults.length > 0) {
      // Dedup by image_url (backend already ranks globally; we merge by key,
      // preferring the freshly-ranked row for any repeated image_url).
      setResults((prev) => {
        const byUrl = new Map();
        for (const r of prev) byUrl.set(r.image_url, r);
        for (const r of newResults) byUrl.set(r.image_url, r);
        return Array.from(byUrl.values()).sort(
          (a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9)
        );
      });
    }
    setHasMore(Boolean(more));
  }

  // ---- derived (client-side filter/sort mirror of backend query params) ------

  const visibleResults = useMemo(() => {
    let rows = results.slice();
    if (filter.provider && filter.provider !== 'all') {
      rows = rows.filter((r) => r.provider === filter.provider);
    }
    if (filter.band && filter.band !== 'all') {
      rows = rows.filter((r) => r.band === filter.band);
    }
    const dir = filter.sort === 'score_asc' ? 1 : -1;
    rows.sort((a, b) => {
      // null scores (no_face) always rank last regardless of direction.
      const sa = a.score === null || a.score === undefined ? -1 : a.score;
      const sb = b.score === null || b.score === undefined ? -1 : b.score;
      if (sa !== sb) return (sa - sb) * dir;
      // Stable tie-break mirrors backend: provider asc, then image_url asc.
      if (a.provider !== b.provider) return a.provider < b.provider ? -1 : 1;
      return a.image_url < b.image_url ? -1 : a.image_url > b.image_url ? 1 : 0;
    });
    return rows;
  }, [results, filter]);

  const hasSearched = search !== null;

  return (
    <main className="app-main">
      <header className="app-header">
        <h1>Omnividence</h1>
        <p className="subtitle">
          Face similarity search across public images. Upload a photo to find
          visually similar faces. This is a school demo, not an identity tool.
        </p>
      </header>

      <section className="panel">
        <Uploader onResult={handleResult} onError={handleError} busy={busy} />
      </section>

      {error ? <div className="error-banner">{error}</div> : null}

      {hasSearched ? (
        <>
          {notes.length > 0 ? (
            <div className="notes">
              <strong>Notes</strong>
              <ul>
                {notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <FilterSort results={results} value={filter} onChange={setFilter} />

          <ResultsGrid results={visibleResults} searchId={searchId} notes={notes} />

          <div className="load-more-wrap">
            <LoadMore
              searchId={searchId}
              hasMore={hasMore}
              busy={busy}
              onMore={handleMore}
              onError={handleError}
            />
          </div>

          <DetectionPanel
            file={file}
            enabled={detectionEnabled}
            onToggle={setDetectionEnabled}
          />
        </>
      ) : null}
    </main>
  );
}
