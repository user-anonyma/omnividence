'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Uploader from '@/components/Uploader';
import ResultsGrid from '@/components/ResultsGrid';
import FilterSort from '@/components/FilterSort';
import DetectionPanel from '@/components/DetectionPanel';
import MatchLegend from '@/components/MatchLegend';
import { apiGetSearch } from '@/lib/api';

// Main search page. Holds search state and wires the pipeline:
//   Uploader -> SearchResponse -> FilterSort + ResultsGrid + LoadMore
//   plus an optional, toggle-gated DetectionPanel (experimental forensics).
// This page never constructs identity language; it only renders backend data.

const DEFAULT_FILTER = { source: 'all', band: 'all', sort: 'score_desc' };
const PAGE_SIZE = 24;

export default function HomePage() {
  // The uploaded File, surfaced by the Uploader (onFile). The experimental
  // DetectionPanel runs its forensics on this exact file.
  const [file, setFile] = useState(null);
  // The full SearchResponse from the backend (or null before first search).
  const [search, setSearch] = useState(null);
  // Accumulated results across the initial search + every "load more" batch.
  const [results, setResults] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState(DEFAULT_FILTER);
  const [detectionEnabled, setDetectionEnabled] = useState(false);
  // How many of the (filtered) results to show; "Show more" reveals another page.
  const [shown, setShown] = useState(PAGE_SIZE);
  // Streaming search state: 'running' while providers are still being fetched in
  // the background, 'done' when finished. progress climbs 0..100.
  const [status, setStatus] = useState('done');
  const [progress, setProgress] = useState(0);

  // Honest notes from the backend (e.g. "yandex: blocked").
  const notes = search?.note || [];
  const searchId = search?.search_id || '';

  // ---- handlers --------------------------------------------------------------

  function handleResult(res) {
    setSearch(res);
    setResults(Array.isArray(res?.results) ? res.results : []);
    setHasMore(Boolean(res?.has_more));
    setFilter(DEFAULT_FILTER);
    setShown(PAGE_SIZE);
    setError('');
    const st = res?.status || 'done';
    setStatus(st);
    setProgress(typeof res?.progress === 'number' ? res.progress : st === 'done' ? 100 : 0);
    // Stay "busy" while the background fan-out is still running (we poll below).
    setBusy(st === 'running');
  }

  // Poll for streaming results + progress while a search is running. The bar is
  // driven by max(backend progress, a time-based estimate) so it always creeps
  // forward smoothly even when a single provider gives coarse 5%->done steps.
  const startRef = useRef(0);
  const backendProgRef = useRef(5);
  useEffect(() => {
    if (status !== 'running' || !searchId) return undefined;
    let cancelled = false;
    startRef.current = Date.now();
    backendProgRef.current = 5;

    const poll = async () => {
      try {
        const res = await apiGetSearch(searchId);
        if (cancelled) return;
        setResults(Array.isArray(res?.results) ? res.results : []);
        setHasMore(Boolean(res?.has_more));
        if (Array.isArray(res?.note)) setSearch((s) => ({ ...(s || {}), note: res.note }));
        if (typeof res?.progress === 'number') {
          backendProgRef.current = Math.max(backendProgRef.current, res.progress);
        }
        if (res?.status === 'done') {
          setStatus('done');
          setProgress(100);
          setBusy(false);
        }
      } catch (_e) {
        // transient poll error — keep trying; the search runs server-side
      }
    };
    const smooth = () => {
      const elapsed = (Date.now() - startRef.current) / 1000;
      const estimate = Math.min(92, 5 + (elapsed / 45) * 87); // ~45s to 92%
      setProgress((p) => Math.max(p, Math.round(Math.max(backendProgRef.current, estimate))));
    };

    const pollId = setInterval(poll, 2500);
    const smoothId = setInterval(smooth, 500);
    poll();
    smooth();
    return () => {
      cancelled = true;
      clearInterval(pollId);
      clearInterval(smoothId);
    };
  }, [status, searchId]);

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
    if (filter.source && filter.source !== 'all') {
      rows = rows.filter((r) => (r.source_category || 'other') === filter.source);
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

  const certainCount = results.filter((r) => (r.score ?? 0) >= 90).length;

  return (
    <main className="app-main">
      <header className="app-header">
        <h1>
          Omni<span className="app-header__accent">vidence</span>
        </h1>
        <p className="subtitle">Find similar faces across public images by photo.</p>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      <section className="layout">
        {/* LEFT: the input image + search controls, pinned top-left */}
        <aside className="layout__left">
          <Uploader
            onResult={handleResult}
            onError={handleError}
            onFile={setFile}
            onStart={() => setBusy(true)}
            busy={busy}
          />
          {hasSearched ? (
            <DetectionPanel
              file={file}
              enabled={detectionEnabled}
              onToggle={setDetectionEnabled}
            />
          ) : null}
        </aside>

        {/* RIGHT: legend + progress + the (smaller) results grid */}
        <div className="layout__right">
          {hasSearched ? (
            <>
              <MatchLegend />

              {status === 'running' ? (
                <div className="search-progress" role="status" aria-live="polite">
                  <div className="search-progress__label">
                    Searching public images… {progress}%
                    {results.length > 0 ? ` · ${results.length} found` : ''}
                  </div>
                  <div className="search-progress__track">
                    <div
                      className="search-progress__bar"
                      style={{ width: `${Math.max(3, Math.min(100, progress))}%` }}
                    />
                  </div>
                </div>
              ) : (
                <div className="results-summary">
                  {results.length > 0
                    ? `${results.length} match${results.length === 1 ? '' : 'es'}${
                        certainCount > 0 ? ` · ${certainCount} certain` : ''
                      }`
                    : 'Search complete'}
                </div>
              )}

              {notes.length > 0 ? (
                <div className="notes">
                  <ul>
                    {notes.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {results.length > 0 ? (
                <FilterSort
                  results={results}
                  value={filter}
                  onChange={(f) => {
                    setFilter(f);
                    setShown(PAGE_SIZE);
                  }}
                />
              ) : null}

              <ResultsGrid
                results={visibleResults.slice(0, shown)}
                searchId={searchId}
                notes={notes}
              />

              {visibleResults.length > shown ? (
                <div className="load-more-wrap">
                  <button
                    type="button"
                    className="omni-btn omni-btn--primary"
                    onClick={() => setShown((n) => n + PAGE_SIZE)}
                  >
                    Show more ({visibleResults.length - shown} left)
                  </button>
                </div>
              ) : null}
            </>
          ) : (
            <div className="right-placeholder">
              <p>Drop a clear, front-facing photo on the left to begin.</p>
              <p className="right-placeholder__sub">
                Matches appear here, ranked by face similarity, highest first.
              </p>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
