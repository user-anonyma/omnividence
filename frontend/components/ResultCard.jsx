'use client';

import { useState } from 'react';
import { bandByKey, bandForScore } from '@/lib/bands';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

// Per-category badge color + 2-letter mark (matches the design palette).
const CAT = {
  instagram: { color: '#c1397f', mark: 'Ig' },
  linkedin: { color: '#2f6fb0', mark: 'in' },
  facebook: { color: '#3b5a9a', mark: 'Fb' },
  twitter: { color: '#586271', mark: 'X' },
  tiktok: { color: '#c2335a', mark: 'Tk' },
};

function srcMeta(result) {
  const cat = result.source_category || 'other';
  if (CAT[cat]) return CAT[cat];
  const name = result.source_label || result.source_domain || result.provider || '?';
  const mark = name.replace(/^(www\.)?/, '').slice(0, 2);
  return { color: '#4a5160', mark: mark.charAt(0).toUpperCase() + mark.slice(1) };
}

export default function ResultCard({ result, delay = 0 }) {
  const cached = result.thumb_url ? `${API_BASE}${result.thumb_url}` : null;
  const [src, setSrc] = useState(cached || result.thumbnail_url || null);
  const [failed, setFailed] = useState(!cached && !result.thumbnail_url);

  const onErr = () => {
    if (src !== result.thumbnail_url && result.thumbnail_url) setSrc(result.thumbnail_url);
    else setFailed(true);
  };

  const band = result.band ? bandByKey(result.band) : bandForScore(result.score ?? null);
  const { color, mark } = srcMeta(result);
  const name = result.source_label || result.source_domain || result.provider || 'source';
  const hasScore = typeof result.score === 'number';

  const inner = (
    <>
      {failed || !src ? (
        <div className="card__noimg">no preview</div>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="card__img" src={src} alt="Visually similar face" loading="lazy" onError={onErr} />
      )}
      <div className="card__scrim" />
      <div className="card__source">
        <span className="card__src-badge" style={{ background: color }}>
          {mark}
        </span>
        <span className="card__src-name">{name}</span>
      </div>
      <div className="card__score" style={{ borderColor: band.color, color: band.color }}>
        {hasScore ? result.score : '–'}
      </div>
    </>
  );

  const style = { animationDelay: `${delay}ms` };

  if (result.page_url) {
    return (
      <a
        className="card"
        style={style}
        href={result.page_url}
        target="_blank"
        rel="noopener noreferrer"
        title={`${name} · ${hasScore ? result.score : ''}`}
      >
        {inner}
      </a>
    );
  }
  return (
    <div className="card" style={style}>
      {inner}
    </div>
  );
}
