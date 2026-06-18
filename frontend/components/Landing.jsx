'use client';

import { useRef, useState } from 'react';

// Landing / upload screen. Drag-drop or click to pick a photo, then "Search by
// face" runs the search. Matches the design: logo, headline, reticle dropzone.
export default function Landing({ file, previewUrl, onPick, onSearch }) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);
  const [note, setNote] = useState('');

  const pick = (f) => {
    if (!f) return;
    if (!f.type || !f.type.startsWith('image/')) {
      setNote('Please choose an image file (JPG, PNG or WEBP).');
      return;
    }
    setNote('');
    onPick(f);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    pick(e.dataTransfer?.files?.[0]);
  };

  const search = (e) => {
    e?.stopPropagation();
    if (file) onSearch(file);
    else inputRef.current?.click();
  };

  return (
    <div className="landing">
      <div className="landing__inner">
        <div className="landing__logowrap">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="landing__logo" src="/logo.png" alt="Omnividence" />
          <span className="landing__led" aria-hidden="true" />
        </div>
        <h1 className="landing__h1">Find similar faces across public images by photo</h1>
        <p className="landing__sub">
          Upload one photo. Omnividence ranks visually similar faces 0–100 across public
          image sources.
        </p>

        <div
          className={`dropzone${dragOver ? ' dropzone--over' : ''}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click();
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            hidden
            onChange={(e) => pick(e.target.files?.[0])}
          />

          {previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img className="dropzone__preview" src={previewUrl} alt="Selected photo" />
          ) : (
            <div className="reticle" aria-hidden="true">
              <div className="reticle__lens">
                <div className="reticle__head" />
                <div className="reticle__body" />
              </div>
              <div className="reticle__c reticle__c--tl" />
              <div className="reticle__c reticle__c--tr" />
              <div className="reticle__c reticle__c--bl" />
              <div className="reticle__c reticle__c--br" />
            </div>
          )}

          <div className="dropzone__line">
            {file ? file.name : 'Drag & drop a photo here'}
          </div>
          <div className="dropzone__sub">JPG · PNG · WEBP — single clear face works best</div>
          <button type="button" className="btn-search" onClick={search}>
            {file ? 'Search by face' : 'Choose photo'}
          </button>
        </div>

        {note ? (
          <div className="landing__foot" style={{ color: 'var(--accent-soft)' }}>
            {note}
          </div>
        ) : (
          <div className="landing__foot">no images stored after search</div>
        )}
      </div>
    </div>
  );
}
