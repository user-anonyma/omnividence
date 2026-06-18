'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Landing from '@/components/Landing';
import Loading from '@/components/Loading';
import Results from '@/components/Results';
import { apiGetSearch, apiSearch, apiForensics, queryFaceUrl } from '@/lib/api';

const DEFAULT_FILTER = { source: 'all', tier: 'all', sort: 'score_desc' };
const PAGE_SIZE = 24;

// Orchestrates the three screens (landing -> loading -> results), the streaming
// search (POST then poll), client-side filter/sort/paging, and the forensics
// readout. All real backend data; never invents identity language.
export default function HomePage() {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [search, setSearch] = useState(null); // SearchResponse or null
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState('idle'); // idle | running | done
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState(DEFAULT_FILTER);
  const [shown, setShown] = useState(PAGE_SIZE);
  const [forensics, setForensics] = useState(null);

  const notes = search?.note || [];
  const searchId = search?.search_id || '';
  const queryFaceSrc = searchId ? queryFaceUrl(searchId) : null;

  // ---- run a search ----------------------------------------------------------
  async function runSearch(f) {
    if (!f) return;
    setError('');
    setForensics(null);
    setResults([]);
    setShown(PAGE_SIZE);
    setFilter(DEFAULT_FILTER);
    setStatus('running');
    setProgress(0);
    try {
      const res = await apiSearch(f);
      if (res?.query_face && res.query_face.detected === false) {
        setStatus('idle');
        setError('No face was detected in the uploaded image. Try a clear, front-facing photo.');
        return;
      }
      setSearch(res);
      setResults(Array.isArray(res?.results) ? res.results : []);
      setProgress(typeof res?.progress === 'number' ? res.progress : 5);
      // kick off forensics on the same file (optional, never blocks)
      apiForensics(f).then((fx) => setForensics(fx)).catch(() => {});
    } catch (err) {
      setStatus('idle');
      setError(err?.message || 'The image could not be processed. Try a different photo.');
    }
  }

  function handlePick(f) {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(f);
    setPreviewUrl(f ? URL.createObjectURL(f) : null);
  }

  function reset() {
    setSearch(null);
    setResults([]);
    setStatus('idle');
    setProgress(0);
    setError('');
    setForensics(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setFile(null);
  }

  // ---- poll while running ----------------------------------------------------
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
        if (Array.isArray(res?.note)) setSearch((s) => ({ ...(s || {}), note: res.note }));
        if (typeof res?.progress === 'number') {
          backendProgRef.current = Math.max(backendProgRef.current, res.progress);
        }
        if (res?.status === 'done') {
          setProgress(100);
          setStatus('done');
        }
      } catch (_e) {
        /* transient; keep polling */
      }
    };
    const smooth = () => {
      const elapsed = (Date.now() - startRef.current) / 1000;
      const est = Math.min(94, 5 + (elapsed / 55) * 89);
      setProgress((p) => Math.max(p, Math.round(Math.max(backendProgRef.current, est))));
    };
    const pollId = setInterval(poll, 2500);
    const smoothId = setInterval(smooth, 400);
    poll();
    smooth();
    return () => {
      cancelled = true;
      clearInterval(pollId);
      clearInterval(smoothId);
    };
  }, [status, searchId]);

  // ---- derived: filter + sort ------------------------------------------------
  const visibleResults = useMemo(() => {
    let rows = results.slice();
    if (filter.source && filter.source !== 'all') {
      rows = rows.filter((r) => (r.source_category || 'other') === filter.source);
    }
    if (filter.tier && filter.tier !== 'all') {
      rows = rows.filter((r) => r.band === filter.tier);
    }
    const dir = filter.sort === 'score_asc' ? 1 : -1;
    rows.sort((a, b) => {
      const sa = a.score == null ? -1 : a.score;
      const sb = b.score == null ? -1 : b.score;
      if (sa !== sb) return (sa - sb) * dir;
      return (a.image_url || '') < (b.image_url || '') ? -1 : 1;
    });
    return rows;
  }, [results, filter]);

  // ---- which screen ----------------------------------------------------------
  const screen = search === null ? 'landing' : status === 'running' ? 'loading' : 'results';

  return (
    <>
      {error ? <div className="error-banner">{error}</div> : null}

      {screen === 'landing' && (
        <Landing
          file={file}
          previewUrl={previewUrl}
          onPick={handlePick}
          onSearch={runSearch}
        />
      )}

      {screen === 'loading' && (
        <Loading progress={progress} matches={results.length} previewUrl={previewUrl} />
      )}

      {screen === 'results' && (
        <Results
          search={search}
          results={results}
          visibleResults={visibleResults}
          shown={shown}
          onShowMore={() => setShown((n) => n + PAGE_SIZE)}
          filter={filter}
          onFilter={(f) => {
            setFilter(f);
            setShown(PAGE_SIZE);
          }}
          notes={notes}
          searchId={searchId}
          queryFaceSrc={queryFaceSrc}
          previewUrl={previewUrl}
          forensics={forensics}
          onNewSearch={reset}
        />
      )}
    </>
  );
}
