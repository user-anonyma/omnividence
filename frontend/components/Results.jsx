'use client';

import { useState } from 'react';
import { SCORE_BANDS } from '@/lib/bands';
import ResultCard from '@/components/ResultCard';

// "Your search" image layouts and grid densities (mockup switchers).
const LAYOUTS = [
  { key: 'stacked', glyph: '▣', title: 'Stacked' },
  { key: 'inset', glyph: '◳', title: 'Inset' },
  { key: 'compact', glyph: '▢', title: 'Compact' },
];
const DENSITIES = [
  { key: 'dense', glyph: '▪▪▪', title: 'Dense', minmax: 116 },
  { key: 'comfortable', glyph: '▪▪', title: 'Comfortable', minmax: 150 },
  { key: 'spacious', glyph: '▪', title: 'Spacious', minmax: 200 },
];

const SOURCE_LABELS = {
  instagram: 'Instagram',
  linkedin: 'LinkedIn',
  facebook: 'Facebook',
  twitter: 'X / Twitter',
  tiktok: 'TikTok',
  other: 'Other websites',
};
const SOURCE_ORDER = ['instagram', 'linkedin', 'facebook', 'twitter', 'tiktok', 'other'];

const forensicColor = (level) => {
  switch ((level || '').toLowerCase()) {
    case 'clean':
      return '#46c46e';
    case 'suspicious':
      return '#ff5a4d';
    case 'uncertain':
      return '#ecc94b';
    default:
      return '#9aa0a8';
  }
};

export default function Results({
  search,
  results,
  visibleResults,
  shown,
  onShowMore,
  filter,
  onFilter,
  notes,
  queryFaceSrc,
  previewUrl,
  forensics,
  onNewSearch,
}) {
  const [layout, setLayout] = useState('inset');
  const [density, setDensity] = useState('comfortable');
  const minmax = (DENSITIES.find((d) => d.key === density) || DENSITIES[1]).minmax;

  const total = results.length;
  const certain = results.filter((r) => (r.score ?? 0) >= 90).length;
  const remaining = Math.max(0, visibleResults.length - shown);

  const categoriesPresent = new Set(results.map((r) => r.source_category || 'other'));
  const sourceOptions = SOURCE_ORDER.filter((c) => categoriesPresent.has(c));

  const qf = search?.query_face || {};
  const bbox = Array.isArray(qf.bbox) ? qf.bbox : null;
  const dim = bbox ? `${bbox[2] - bbox[0]}×${bbox[3] - bbox[1]}` : null;

  const fx = forensics && forensics.checks ? forensics.checks : null;
  const fxRow = (key, label) => {
    const c = fx ? fx[key] : null;
    return (
      <div className="forensics__row">
        <span className="forensics__k">{label}</span>
        <span className="forensics__v" style={{ color: c ? forensicColor(c.level) : 'var(--dim)' }}>
          {c ? (
            <>
              {c.label} <small>({typeof c.score === 'number' ? c.score.toFixed(2) : '–'})</small>
            </>
          ) : (
            'analyzing…'
          )}
        </span>
      </div>
    );
  };

  return (
    <div className="results">
      {/* LEFT */}
      <aside className="results__left">
        <div className="panel-head">
          <span className="panel-label">YOUR SEARCH</span>
          <div className="seg" role="group" aria-label="Image layout">
            {LAYOUTS.map((l) => (
              <button
                key={l.key}
                type="button"
                className={`seg__btn${layout === l.key ? ' seg__btn--on' : ''}`}
                title={l.title}
                aria-pressed={layout === l.key}
                onClick={() => setLayout(l.key)}
              >
                {l.glyph}
              </button>
            ))}
          </div>
        </div>

        <div className={`qsearch qsearch--${layout}`}>
          {previewUrl ? (
            <div className="qpic qpic__wrap qsearch__main">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className="qpic__img" src={previewUrl} alt="Uploaded photo" />
              <span className="qpic__tag">UPLOADED</span>
            </div>
          ) : null}

          {queryFaceSrc ? (
            <div className="qpic qpic--accent qpic__wrap qsearch__face">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className="qpic__img qpic__img--sq" src={queryFaceSrc} alt="Detected face" />
              <span className="qpic__tag qpic__tag--c">DETECTED FACE</span>
            </div>
          ) : null}
        </div>

        <div className="forensics">
          <div className="panel-label" style={{ marginBottom: 12 }}>
            FORENSICS
          </div>
          {fxRow('ai_generated', 'AI-generated')}
          <div className="forensics__div" />
          {fxRow('manipulation_ela', 'Manipulation')}
          <div className="forensics__div" />
          {fxRow('deepfake', 'Deepfake')}
        </div>

        <button type="button" className="btn-ghost" onClick={onNewSearch}>
          <span style={{ fontSize: 15, lineHeight: 1 }}>＋</span>New search
        </button>

        <div className="meta">
          {qf.detected ? '1 face detected' : 'face'}
          {dim ? ` · ${dim}` : ''}
          <br />
          embedding: 512-d · model buffalo_s
        </div>
      </aside>

      {/* RIGHT */}
      <section className="results__right">
        <div className="legend">
          {SCORE_BANDS.map((b) => (
            <span className="legend__item" key={b.key}>
              <span className="legend__dot" style={{ background: b.color }} />
              {b.label}
              <span className="legend__range">
                {Math.max(b.min, 50)}–{b.max}
              </span>
            </span>
          ))}
        </div>

        <div className="results__head">
          <div className="count">
            <span className="count__n">{total}</span>
            <span className="count__l">matches</span>
            {certain > 0 ? (
              <>
                <span className="count__dot" />
                <span className="count__certain">{certain} certain</span>
              </>
            ) : null}
          </div>

          <div className="filters">
            <div className="filter">
              <span className="filter__label">SOURCE</span>
              <select
                value={filter.source}
                onChange={(e) => onFilter({ ...filter, source: e.target.value })}
              >
                <option value="all">All</option>
                {sourceOptions.map((c) => (
                  <option key={c} value={c}>
                    {SOURCE_LABELS[c] || c}
                  </option>
                ))}
              </select>
            </div>
            <div className="filter">
              <span className="filter__label">TIER</span>
              <select
                value={filter.tier}
                onChange={(e) => onFilter({ ...filter, tier: e.target.value })}
              >
                <option value="all">All</option>
                {SCORE_BANDS.map((b) => (
                  <option key={b.key} value={b.key}>
                    {b.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="filter">
              <span className="filter__label">SORT</span>
              <select
                value={filter.sort}
                onChange={(e) => onFilter({ ...filter, sort: e.target.value })}
              >
                <option value="score_desc">Score: high → low</option>
                <option value="score_asc">Score: low → high</option>
              </select>
            </div>
            <div className="filter">
              <span className="filter__label">DENSITY</span>
              <div className="seg" role="group" aria-label="Grid density">
                {DENSITIES.map((d) => (
                  <button
                    key={d.key}
                    type="button"
                    className={`seg__btn${density === d.key ? ' seg__btn--on' : ''}`}
                    title={d.title}
                    aria-pressed={density === d.key}
                    onClick={() => setDensity(d.key)}
                  >
                    {d.glyph}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {notes && notes.length > 0 ? (
          <div className="notes">
            <ul>
              {notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {visibleResults.length === 0 ? (
          <div className="notes" style={{ padding: '20px 0' }}>
            No face matches found for this photo.
          </div>
        ) : (
          <div className="card-grid" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${minmax}px, 1fr))` }}>
            {visibleResults.slice(0, shown).map((r, i) => (
              <ResultCard
                key={r.id ?? `${r.provider}:${r.image_url}`}
                result={r}
                delay={Math.min(i, 24) * 22}
              />
            ))}
          </div>
        )}

        {remaining > 0 ? (
          <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 8 }}>
            <button type="button" className="btn-ghost" style={{ width: 'auto' }} onClick={onShowMore}>
              Show more
              <span className="mono" style={{ fontSize: 11, color: 'var(--muted)' }}>
                {remaining} left
              </span>
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
