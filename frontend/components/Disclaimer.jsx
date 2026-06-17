'use client';

// Disclaimer — the single MANDATED render site is app/layout.tsx, where this is
// shown in a sticky/fixed position so the sentence is ALWAYS visible on every
// page and in every state. The wording is fixed by the build contract and MUST
// NOT be altered (no "match" / "identity confidence" / "probability").
//
// Props: { variant?: 'bar' | 'inline' }  (default 'bar')

export const DISCLAIMER_TEXT =
  'Results are approximate visual similarity matches and do not confirm identity.';

export default function Disclaimer({ variant = 'bar' }) {
  return (
    <div className={`omni-disclaimer omni-disclaimer--${variant}`} role="note">
      <span className="omni-disclaimer__icon" aria-hidden="true">
        ⚠
      </span>
      <span className="omni-disclaimer__text">{DISCLAIMER_TEXT}</span>
    </div>
  );
}
