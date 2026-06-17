'use client';

import { bandForScore, bandByKey, NO_FACE_BAND } from '@/lib/bands';

// ScoreBadge
// Props: { score: number|null; band?: BandKey; label?: string }
//
// Color + fallback label come from lib/bands.js (mirror of backend ranking.py).
// The backend supplies `band` (key) and `label` (band_label); when present we use
// them, otherwise we derive from the numeric score. The text ALWAYS reads
// "similarity" — never "match", "identity", or "probability".
//
// Display:
//   numeric score -> "91 · Strong visual similarity"
//   null score    -> "No face detected"

export default function ScoreBadge({ score, band, label }) {
  const hasScore = typeof score === 'number' && !Number.isNaN(score);

  // Resolve the band: prefer the backend-provided key, else derive from score.
  let resolved;
  if (band) {
    resolved = bandByKey(band);
  } else {
    resolved = bandForScore(hasScore ? score : null);
  }

  const isNoFace = resolved.key === 'no_face' || !hasScore;
  const text = isNoFace
    ? label || NO_FACE_BAND.label
    : `${score} · ${label || resolved.label}`;

  const style = {
    '--band-color': resolved.color,
  };

  return (
    <span
      className={`omni-badge omni-badge--${resolved.key}${
        isNoFace ? ' omni-badge--no-face' : ''
      }`}
      style={style}
      title={text}
    >
      {!isNoFace && <span className="omni-badge__num">{score}</span>}
      <span className="omni-badge__label">
        {isNoFace ? text : label || resolved.label}
      </span>
    </span>
  );
}
