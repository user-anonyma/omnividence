'use client';

import { bandForScore, bandByKey, NO_FACE_BAND } from '@/lib/bands';

// ScoreBadge — a circular match-score badge (FaceCheck-style), coloured by tier.
// Props: { score: number|null; band?: BandKey; label?: string }
//
// Color + fallback label come from lib/bands.js (mirror of backend ranking.py).
// Shows the numeric score in a coloured circle; the tier label is the title/tooltip.

export default function ScoreBadge({ score, band, label }) {
  const hasScore = typeof score === 'number' && !Number.isNaN(score);
  const resolved = band ? bandByKey(band) : bandForScore(hasScore ? score : null);
  const isNoFace = resolved.key === 'no_face' || !hasScore;
  const tierLabel = label || resolved.label;

  return (
    <span
      className={`omni-badge omni-badge--${resolved.key}`}
      style={{ '--band-color': resolved.color }}
      title={isNoFace ? NO_FACE_BAND.label : `${score} · ${tierLabel}`}
      aria-label={isNoFace ? NO_FACE_BAND.label : `Score ${score}, ${tierLabel}`}
    >
      {isNoFace ? '–' : score}
    </span>
  );
}
