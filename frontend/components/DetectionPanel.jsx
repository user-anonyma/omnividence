'use client';

import { useState } from 'react';
import { apiForensics } from '@/lib/api';

// DetectionPanel — EXPERIMENTAL, OPTIONAL. Never on the search path.
// Props: { file: File|null; enabled: boolean; onToggle(b: boolean): void }
//
// Behind a toggle (default off, controlled by the parent). Calls apiForensics(file)
// ONLY when enabled AND a file exists. Every interaction is wrapped so any error
// renders a clean low-confidence fallback and NEVER affects the search UI.
//
// Forensics response shape (backend /api/forensics):
//   { experimental: true, confidence: 'low',
//     checks: { ai_generated:{score,label}, manipulation_ela:{score,label},
//               deepfake:{score,label} }, note }

const CHECK_LABELS = {
  ai_generated: 'AI-generated likelihood',
  manipulation_ela: 'Manipulation (ELA)',
  deepfake: 'Deepfake heuristic',
};

function ForensicsErrorFallback() {
  return (
    <div className="omni-forensics__rows">
      {Object.keys(CHECK_LABELS).map((k) => (
        <div className="omni-forensics__row" key={k}>
          <span className="omni-forensics__name">{CHECK_LABELS[k]}</span>
          <span className="omni-forensics__val omni-forensics__val--unavailable">
            unavailable
          </span>
        </div>
      ))}
    </div>
  );
}

export default function DetectionPanel({ file, enabled, onToggle }) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [errored, setErrored] = useState(false);

  const run = async () => {
    if (!file) return;
    setLoading(true);
    setErrored(false);
    setData(null);
    try {
      // apiForensics is itself wrapped server-side to never 5xx, but we still
      // guard the client call so a network failure can never disrupt the page.
      const res = await apiForensics(file);
      setData(res);
    } catch (_err) {
      setErrored(true);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = (e) => {
    const next = e.target.checked;
    onToggle?.(next);
    if (next && file) {
      run();
    }
  };

  // Defensive render: if anything about `data` is malformed, fall back rather
  // than throwing inside the render tree.
  let body = null;
  try {
    if (loading) {
      body = <p className="omni-forensics__status">Running heuristics…</p>;
    } else if (errored) {
      body = (
        <>
          <ForensicsErrorFallback />
          <p className="omni-forensics__note">
            Could not run the experimental checks. This does not affect your
            similarity search.
          </p>
        </>
      );
    } else if (data && data.checks) {
      const checks = data.checks;
      body = (
        <>
          <div className="omni-forensics__rows">
            {Object.keys(CHECK_LABELS).map((k) => {
              const c = checks[k] || {};
              return (
                <div className="omni-forensics__row" key={k}>
                  <span className="omni-forensics__name">
                    {CHECK_LABELS[k]}
                  </span>
                  <span className="omni-forensics__val">
                    {c.label || 'inconclusive'}
                    {typeof c.score === 'number' && (
                      <em className="omni-forensics__score">
                        {' '}
                        ({c.score.toFixed(2)})
                      </em>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
          {data.note && <p className="omni-forensics__note">{data.note}</p>}
        </>
      );
    } else if (!file) {
      body = (
        <p className="omni-forensics__status">
          Upload an image first to run experimental checks.
        </p>
      );
    } else {
      body = (
        <button
          type="button"
          className="omni-btn omni-btn--secondary"
          onClick={run}
        >
          Run experimental checks
        </button>
      );
    }
  } catch (_err) {
    body = <ForensicsErrorFallback />;
  }

  return (
    <section className="omni-forensics">
      <div className="omni-forensics__head">
        <label className="omni-forensics__toggle">
          <input
            type="checkbox"
            checked={enabled}
            onChange={handleToggle}
          />
          <span>Experimental forensics</span>
        </label>
      </div>

      <p className="omni-forensics__banner">
        Experimental / low confidence — not evidence. These heuristics are
        unreliable and do not confirm anything about the image or any person.
      </p>

      {enabled && <div className="omni-forensics__body">{body}</div>}
    </section>
  );
}
