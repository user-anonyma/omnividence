'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import FilterSort from '@/components/FilterSort';
import ResultsGrid from '@/components/ResultsGrid';
import { apiGetSearch } from '@/lib/api';

// Deep-link to a cached search. Fetches via apiGetSearch(id) (no provider calls)
// and renders the same FilterSort + ResultsGrid as the home page. Read-only:
// it shows whatever was persisted for this search_id. No identity language.

const DEFAULT_FILTER = { provider: 'all', band: 'all', sort: 'score_desc' };

export default function CachedSearchPage() {
  const params = useParams();
  const id = Array.isArray(params?.id) ? params.id[0] : params?.id;

  const [search, setSearch] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState(DEFAULT_FILTER);

  useEffect(() => {
    let cancelled = false;
    if (!id) return;
    setLoading(true);
    setError('');
    apiGetSearch(id)
      .then((res) => {
        if (!cancelled) {
          setSearch(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.message || 'Could not load this search.');
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const results = search?.results || [];
  const notes = search?.note || [];
  const searchId = search?.search_id || id || '';

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
      const sa = a.score === null || a.score === undefined ? -1 : a.score;
      const sb = b.score === null || b.score === undefined ? -1 : b.score;
      if (sa !== sb) return (sa - sb) * dir;
      if (a.provider !== b.provider) return a.provider < b.provider ? -1 : 1;
      return a.image_url < b.image_url ? -1 : a.image_url > b.image_url ? 1 : 0;
    });
    return rows;
  }, [results, filter]);

  return (
    <main className="app-main">
      <header className="app-header">
        <h1>Omnividence</h1>
        <p className="subtitle">
          Cached search results. Face similarity over public images only; this is
          a school demo and does not confirm identity.
        </p>
      </header>

      {loading ? <p className="muted">Loading search…</p> : null}
      {error ? <div className="error-banner">{error}</div> : null}

      {!loading && !error && search ? (
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
        </>
      ) : null}
    </main>
  );
}
