'use client';

import { SCORE_BANDS } from '@/lib/bands';

// MatchLegend — the score-tier legend bar (FaceCheck-style): a row of coloured
// pills, each showing a score range + its match-confidence label.

export default function MatchLegend() {
  return (
    <div className="legend" role="list" aria-label="Match score tiers">
      {SCORE_BANDS.map((b) => {
        // Nothing below 50 is shown (the backend similarity floor), so the
        // lowest tier reads 50–69 rather than 0–69.
        const low = Math.max(b.min, 50);
        const range = `${low}–${b.max}`;
        return (
          <span className="legend__item" role="listitem" key={b.key}>
            <span className="legend__pill" style={{ background: b.color }}>
              {range}
            </span>
            <span className="legend__label">{b.label}</span>
          </span>
        );
      })}
    </div>
  );
}
