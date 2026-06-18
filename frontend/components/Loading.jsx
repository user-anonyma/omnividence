'use client';

// Loading screen — the scanning query face, ANALYZING FACE, a 0–100 progress
// bar, live match count, and pipeline steps that light up as progress climbs.
const STEPS = [
  { label: 'Detecting face', at: 12 },
  { label: 'Generating 512-d embedding', at: 28 },
  { label: 'Querying public image sources', at: 55 },
  { label: 'Ranking by face similarity', at: 90 },
];

export default function Loading({ progress, matches, previewUrl }) {
  const p = Math.max(0, Math.min(100, progress || 0));

  const stepState = (i) => {
    const start = i === 0 ? 0 : STEPS[i - 1].at;
    const end = STEPS[i].at;
    if (p >= end) return 'done';
    if (p >= start) return 'active';
    return '';
  };
  const icon = (s) => (s === 'done' ? '✓' : s === 'active' ? '▸' : '·');

  return (
    <div className="loading">
      <div className="loading__inner">
        <div className="scanface">
          {previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={previewUrl} alt="Analyzing face" />
          ) : (
            <>
              <div className="scanface__head" />
              <div className="scanface__body" />
            </>
          )}
          <div className="scanface__line" />
          <div className="scanface__c scanface__c--tl" />
          <div className="scanface__c scanface__c--tr" />
          <div className="scanface__c scanface__c--bl" />
          <div className="scanface__c scanface__c--br" />
        </div>

        <div className="loading__label">ANALYZING FACE</div>
        <div className="loading__pct">
          {p}
          <span>%</span>
        </div>

        <div className="loading__track">
          <div className="loading__bar" style={{ width: `${Math.max(3, p)}%` }} />
        </div>
        <div className="loading__found">{matches} matches found</div>

        <div className="loading__steps">
          {STEPS.map((s, i) => {
            const st = stepState(i);
            return (
              <div key={s.label} className={`loading__step${st ? ` loading__step--${st}` : ''}`}>
                <span className="loading__step-icon">{icon(st)}</span>
                {s.label}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
