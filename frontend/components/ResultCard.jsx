'use client';

import { useState } from 'react';
import ScoreBadge from '@/components/ScoreBadge';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

// ResultCard
// Props: { result: Result; searchId: string }
//
// Result shape (from backend /api/search JSON):
//   { id?, image_url, thumbnail_url, thumb_url, page_url, page_title,
//     provider, score, band, band_label, rank }
//
// Renders: cached thumbnail (src = API_BASE + result.thumb_url, fallback to the
// provider's thumbnail_url), provider chip, ScoreBadge, page title, and an
// "Open source page" external link. NO names, NO identity wording — only the
// public URLs the provider returned.

const PROVIDER_LABELS = {
  google_lens: 'Google Lens',
  yandex: 'Yandex',
  bing: 'Bing',
};

export default function ResultCard({ result }) {
  // Primary src is the backend-cached thumbnail; on error fall back to the raw
  // provider thumbnail_url, then to a "no preview" placeholder state.
  const cachedSrc = result.thumb_url ? `${API_BASE}${result.thumb_url}` : null;
  const [src, setSrc] = useState(cachedSrc || result.thumbnail_url || null);
  const [failed, setFailed] = useState(!cachedSrc && !result.thumbnail_url);

  const handleImgError = () => {
    // If the cached thumb failed and a provider thumbnail exists, try that once.
    if (src !== result.thumbnail_url && result.thumbnail_url) {
      setSrc(result.thumbnail_url);
    } else {
      setFailed(true);
    }
  };

  const providerLabel = PROVIDER_LABELS[result.provider] || result.provider;

  return (
    <article className="omni-card">
      <div className="omni-card__thumb">
        {failed || !src ? (
          <div className="omni-card__thumb-fallback" aria-hidden="true">
            no preview
          </div>
        ) : (
          // Plain <img>: these are arbitrary external/cached URLs, not optimized
          // through next/image (see next.config.js).
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt="Public image result thumbnail (visual similarity candidate)"
            loading="lazy"
            onError={handleImgError}
          />
        )}
        {typeof result.rank === 'number' && (
          <span className="omni-card__rank">#{result.rank}</span>
        )}
      </div>

      <div className="omni-card__body">
        <div className="omni-card__topline">
          <span className="omni-card__provider">{providerLabel}</span>
          <ScoreBadge
            score={result.score ?? null}
            band={result.band}
            label={result.band_label}
          />
        </div>

        {result.page_title && (
          <p className="omni-card__title" title={result.page_title}>
            {result.page_title}
          </p>
        )}

        {result.page_url ? (
          <a
            className="omni-card__link"
            href={result.page_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open source page ↗
          </a>
        ) : (
          <span className="omni-card__link omni-card__link--disabled">
            No source page
          </span>
        )}
      </div>
    </article>
  );
}
