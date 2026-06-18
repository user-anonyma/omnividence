'use client';

import { SCORE_BANDS, NO_FACE_BAND } from '@/lib/bands';

// FilterSort
// Props: {
//   results: Result[];
//   value: { source: string|'all'; band: BandKey|'all'; sort: 'score_desc'|'score_asc' };
//   onChange(next): void;
// }
//
// Pure client-side filter/sort control over already-loaded results. The Source
// dropdown lets you narrow to Instagram / LinkedIn / etc. (or "Other websites").

const SOURCE_LABELS = {
  instagram: 'Instagram',
  linkedin: 'LinkedIn',
  facebook: 'Facebook',
  twitter: 'X / Twitter',
  tiktok: 'TikTok',
  other: 'Other websites',
};
// Show social categories first, then "other".
const SOURCE_ORDER = ['instagram', 'linkedin', 'facebook', 'twitter', 'tiktok', 'other'];

export default function FilterSort({ results, value, onChange }) {
  const categoriesPresent = new Set(
    (results || []).map((r) => r.source_category || 'other')
  );
  const sourceOptions = SOURCE_ORDER.filter((c) => categoriesPresent.has(c));

  const set = (patch) => onChange?.({ ...value, ...patch });

  return (
    <div className="omni-filtersort" role="group" aria-label="Filter and sort">
      <label className="omni-filtersort__field">
        <span>Source</span>
        <select
          value={value.source}
          onChange={(e) => set({ source: e.target.value })}
        >
          <option value="all">All sources</option>
          {sourceOptions.map((c) => (
            <option key={c} value={c}>
              {SOURCE_LABELS[c] || c}
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
  const { source, band, sort } = value || {};
  let out = Array.isArray(results) ? results.slice() : [];

  if (source && source !== 'all') {
    out = out.filter((r) => (r.source_category || 'other') === source);
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
