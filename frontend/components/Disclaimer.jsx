'use client';

import { useState } from 'react';

// Disclaimer — the mandated honesty notice, shown by default on every page load
// (dismissible per the approved design). The wording must NOT change.
const TEXT =
  'Results are approximate visual similarity matches and do not confirm identity.';

export default function Disclaimer() {
  const [show, setShow] = useState(true);
  if (!show) return null;
  return (
    <div className="disclaimer" role="note">
      <div className="disclaimer__text">
        <span className="disclaimer__dot" aria-hidden="true" />
        {TEXT}
      </div>
      <button
        type="button"
        className="disclaimer__x"
        onClick={() => setShow(false)}
        aria-label="Dismiss disclaimer"
      >
        ×
      </button>
    </div>
  );
}
