'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { SCORE_BANDS } from '@/lib/bands';
import ResultCard from '@/components/ResultCard';
import { apiGetSearch } from '@/lib/api';

// Deep-link to a cached search (read-only). Renders the same card grid + legend
// as the main results screen, in the new design.
export default function CachedSearchPage() {
  const params = useParams();
  const id = Array.isArray(params?.id) ? params.id[0] : params?.id;

  const [search, setSearch] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [shown, setShown] = useState(48);

  useEffect(() => {
    let cancelled = false;
    if (!id) return;
    apiGetSearch(id)
      .then((res) => !cancelled && (setSearch(res), setLoading(false)))
      .catch((err) => !cancelled && (setError(err?.message || 'Could not load this search.'), setLoading(false)));
    return () => {
      cancelled = true;
    };
  }, [id]);

  const results = useMemo(() => {
    const rows = Array.isArray(search?.results) ? search.results.slice() : [];
    rows.sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
    return rows;
  }, [search]);

  const certain = results.filter((r) => (r.score ?? 0) >= 90).length;

  return (
    <div className="results" style={{ gridTemplateColumns: '1fr' }}>
      <section className="results__right">
        <div className="legend">
          {SCORE_BANDS.map((b) => (
            <span className="legend__item" key={b.key}>
              <span className="legend__dot" style={{ background: b.color }} />
              {b.label}
              <span className="legend__range">{Math.max(b.min, 50)}–{b.max}</span>
            </span>
          ))}
        </div>

        {loading ? (
          <div className="notes" style={{ padding: '20px 0' }}>Loading search…</div>
        ) : error ? (
          <div className="error-banner">{error}</div>
        ) : (
          <>
            <div className="count">
              <span className="count__n">{results.length}</span>
              <span className="count__l">matches</span>
              {certain > 0 ? (
                <>
                  <span className="count__dot" />
                  <span className="count__certain">{certain} certain</span>
                </>
              ) : null}
            </div>
            <div
              className="card-grid"
              style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))' }}
            >
              {results.slice(0, shown).map((r, i) => (
                <ResultCard key={r.id ?? `${r.provider}:${r.image_url}`} result={r} delay={Math.min(i, 24) * 18} />
              ))}
            </div>
            {results.length > shown ? (
              <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 8 }}>
                <button type="button" className="btn-ghost" style={{ width: 'auto' }} onClick={() => setShown((n) => n + 48)}>
                  Show more
                </button>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
