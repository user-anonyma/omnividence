'use client';

import { useRef, useState, useEffect } from 'react';
import { apiSearch, queryFaceUrl } from '@/lib/api';

// Uploader
// Props: { onResult(res): void; onError(msg): void; onFile(file): void;
//          onStart(): void; busy: boolean }
//
// Drag-drop + file input (accept image/*). Calls apiSearch(file, providers).
// Surfaces the chosen File to the parent via onFile (the experimental
// DetectionPanel consumes it) and signals search start via onStart (loading
// state). Shows the chosen image preview and the cropped query face from the
// response. Surfaces no_face_detected / invalid_image / blocked notes plainly —
// never invents identity language.

const ALL_PROVIDERS = [
  { id: 'yandex', label: 'Yandex (best for faces)' },
  { id: 'bing', label: 'Bing (slower, wider net)' },
  { id: 'google_lens', label: 'Google Lens (often blocked)' },
];
// Yandex is the only engine that does real face matching and it's one browser,
// so it's fast and clean on modest hardware. The others are opt-in.
const DEFAULT_PROVIDERS = ['yandex'];

export default function Uploader({ onResult, onError, onFile, onStart, busy }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [providers, setProviders] = useState(DEFAULT_PROVIDERS);
  const [queryFaceSrc, setQueryFaceSrc] = useState(null);
  const [localNote, setLocalNote] = useState(null);

  // Revoke object URLs to avoid leaks.
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const pickFile = (f) => {
    if (!f) return;
    if (!f.type || !f.type.startsWith('image/')) {
      setLocalNote('Please choose an image file (jpg, png, or webp).');
      return;
    }
    setLocalNote(null);
    setQueryFaceSrc(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(f));
    setFile(f);
    onFile?.(f); // surface the File so the DetectionPanel can analyze it
  };

  const toggleProvider = (id) => {
    setProviders((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
    );
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    if (busy) return;
    const f = e.dataTransfer?.files?.[0];
    pickFile(f);
  };

  const submit = async () => {
    if (!file || busy) return;
    setLocalNote(null);
    onStart?.(); // signal the parent to enter the loading state
    try {
      const chosen = providers.length ? providers : undefined;
      const res = await apiSearch(file, chosen);

      // Honest handling of the no-face case (backend returns 422 with
      // query_face.detected=false; the api client may surface that as a thrown
      // error or as a structured payload — handle both).
      if (res?.query_face && res.query_face.detected === false) {
        setQueryFaceSrc(null);
        onError?.('No face was detected in the uploaded image.');
        return;
      }

      if (res?.search_id && res?.query_face?.detected) {
        setQueryFaceSrc(queryFaceUrl(res.search_id));
      }
      onResult?.(res);
    } catch (err) {
      const msg =
        err?.message ||
        'The image could not be processed. Please try a different image.';
      onError?.(msg);
    }
  };

  return (
    <section className="omni-uploader">
      <div
        className={`omni-dropzone${dragOver ? ' omni-dropzone--over' : ''}${
          busy ? ' omni-dropzone--busy' : ''
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => !busy && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !busy) {
            inputRef.current?.click();
          }
        }}
        aria-disabled={busy}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          hidden
          disabled={busy}
          onChange={(e) => pickFile(e.target.files?.[0])}
        />

        {previewUrl ? (
          <div className="omni-uploader__previews">
            <figure className="omni-uploader__fig">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={previewUrl} alt="Selected upload preview" />
              <figcaption>Uploaded image</figcaption>
            </figure>
            {queryFaceSrc && (
              <figure className="omni-uploader__fig">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={queryFaceSrc} alt="Detected query face crop" />
                <figcaption>Detected face (query)</figcaption>
              </figure>
            )}
          </div>
        ) : (
          <div className="omni-dropzone__hint">
            <span className="omni-dropzone__icon" aria-hidden="true">
              ⬆
            </span>
            <p>
              <strong>Drag &amp; drop</strong> an image here, or click to choose
            </p>
            <p className="omni-dropzone__sub">JPG, PNG or WEBP</p>
          </div>
        )}
      </div>

      <fieldset className="omni-providers" disabled={busy}>
        <legend>Search providers</legend>
        {ALL_PROVIDERS.map((p) => (
          <label key={p.id} className="omni-providers__opt">
            <input
              type="checkbox"
              checked={providers.includes(p.id)}
              onChange={() => toggleProvider(p.id)}
            />
            {p.label}
          </label>
        ))}
      </fieldset>

      {localNote && <p className="omni-uploader__note">{localNote}</p>}

      <button
        type="button"
        className="omni-btn omni-btn--primary"
        onClick={submit}
        disabled={!file || busy}
      >
        {busy ? 'Searching…' : 'Search by face similarity'}
      </button>
    </section>
  );
}
