'use client';

import { SCORE_BANDS, NO_FACE_BAND } from '@/lib/bands';

// FilterSort
// Props: {
//   results: Result[];
//   value: { provider: string|'all'; band: BandKey|'all'; sort: 'score_desc'|'score_asc' };
//   onChange(next): void;
// }
//
// Pure client-side filter/sort control over already-loaded results. Mirrors the
// backend query-param semantics for GET /api/search/{id} (provider, band, sort).
// The provider dropdown is built from the providers actually present in the
// loaded results; the band dropdown from SCORE_BANDS (+ no_face).

const PROVIDER_LABELS = {
  google_lens: 'Google Lens',
  yandex: 'Yandex',
  bing: 'Bing',
};

export default function FilterSort({ results, value, onChange }) {
  const providersPresent = Array.from(
    new Set((results || []).map((r) => r.provider).filter(Boolean))
  ).sort();

  const set = (patch) => onChange?.({ ...value, ...patch });

  return (
    <div className="omni-filtersort" role="group" aria-label="Filter and sort">
      <label className="omni-filtersort__field">
        <span>Provider</span>
        <select
          value={value.provider}
          onChange={(e) => set({ provider: e.target.value })}
        >
          <option value="all">All providers</option>
          {providersPresent.map((p) => (
            <option key={p} value={p}>
              {PROVIDER_LABELS[p] || p}
            </option>
          ))}
        </select>
      </label>

      <label className="omni-filtersort__field">
        <span>Band</span>
        <select
          value={value.band}
          onChange={(e) => set({ band: e.target.value })}
        >
          <option value="all">All bands</option>
          {SCORE_BANDS.map((b) => (
            <option key={b.key} value={b.key}>
              {b.label}
            </option>
          ))}
          <option value={NO_FACE_BAND.key}>{NO_FACE_BAND.label}</option>
        </select>
      </label>

      <label className="omni-filtersort__field">
        <span>Sort</span>
        <select
          value={value.sort}
          onChange={(e) => set({ sort: e.target.value })}
        >
          <option value="score_desc">Score: high → low</option>
          <option value="score_asc">Score: low → high</option>
        </select>
      </label>
    </div>
  );
}

// applyFilterSort — pure helper the page can use to derive the visible list from
// the full loaded set, matching the backend's filter/sort semantics. Exported so
// page.tsx can keep all results in state and compute the displayed slice.
export function applyFilterSort(results, value) {
  const { provider, band, sort } = value || {};
  let out = Array.isArray(results) ? results.slice() : [];

  if (provider && provider !== 'all') {
    out = out.filter((r) => r.provider === provider);
  }
  if (band && band !== 'all') {
    out = out.filter((r) => r.band === band);
  }

  // Sort by score with nulls (no_face) always last regardless of direction.
  const asc = sort === 'score_asc';
  out.sort((a, b) => {
    const sa = typeof a.score === 'number' ? a.score : null;
    const sb = typeof b.score === 'number' ? b.score : null;
    if (sa === null && sb === null) {
      return tieBreak(a, b);
    }
    if (sa === null) return 1;
    if (sb === null) return -1;
    if (sa !== sb) return asc ? sa - sb : sb - sa;
    return tieBreak(a, b);
  });
  return out;
}

// Stable tie-break mirroring backend determinism: provider asc, then image_url asc.
function tieBreak(a, b) {
  const pa = a.provider || '';
  const pb = b.provider || '';
  if (pa !== pb) return pa < pb ? -1 : 1;
  const ua = a.image_url || '';
  const ub = b.image_url || '';
  if (ua === ub) return 0;
  return ua < ub ? -1 : 1;
}
