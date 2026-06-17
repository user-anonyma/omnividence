'use client';

import { useState } from 'react';
import ScoreBadge from '@/components/ScoreBadge';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

// ResultCard — FaceCheck-style tile: the matched face fills the card, with a
// source chip (favicon + domain) top-left and a circular score badge top-right.
// Clicking opens the public source page. NO names, NO identity wording.
//
// Result shape: { thumb_url, thumbnail_url, page_url, page_title, provider,
//                 score, band, band_label, rank }

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

export default function ResultCard({ result }) {
  const cachedSrc = result.thumb_url ? `${API_BASE}${result.thumb_url}` : null;
  const [src, setSrc] = useState(cachedSrc || result.thumbnail_url || null);
  const [failed, setFailed] = useState(!cachedSrc && !result.thumbnail_url);

  const handleImgError = () => {
    if (src !== result.thumbnail_url && result.thumbnail_url) {
      setSrc(result.thumbnail_url);
    } else {
      setFailed(true);
    }
  };

  const host = result.page_url ? hostOf(result.page_url) : null;
  const favicon = host
    ? `https://www.google.com/s2/favicons?domain=${host}&sz=32`
    : null;

  const inner = (
    <>
      <div className="card2__img">
        {failed || !src ? (
          <div className="card2__noimg" aria-hidden="true">
            no preview
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt="Public image with a visually similar face"
            loading="lazy"
            onError={handleImgError}
          />
        )}
      </div>

      <div className="card2__source">
        {favicon && (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="card2__favicon" src={favicon} alt="" aria-hidden="true" />
        )}
        <span className="card2__host">{host || result.provider}</span>
      </div>

      <ScoreBadge
        score={result.score ?? null}
        band={result.band}
        label={result.band_label}
      />
    </>
  );

  if (result.page_url) {
    return (
      <a
        className="card2"
        href={result.page_url}
        target="_blank"
        rel="noopener noreferrer"
        title={result.page_title || 'Open source page'}
      >
        {inner}
      </a>
    );
  }
  return <div className="card2">{inner}</div>;
}
