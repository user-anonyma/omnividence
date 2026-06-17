# Omnividence

**A school tech-showcase prototype for face-similarity search — NOT an identity
or surveillance system.**

Upload a photo. Omnividence detects the largest visible face, embeds it with
InsightFace, sends the cropped face to reverse-image-search providers, downloads
the public image results, re-detects + embeds each result, and re-ranks them by
**face-embedding cosine similarity**. The output is a ranked grid of public
images with a **face similarity score (0–100)** — never a "match probability"
or "identity confidence."

> **Results are approximate visual similarity matches and do not confirm
> identity.** This sentence is rendered in the app's root layout and is visible
> on every page and every state.

---

## What it does (and does not) do

It **does**:

- Detect the single largest face in your upload and crop/normalize it.
- Embed faces to 512-d, L2-normalized vectors (InsightFace `buffalo_l`, CPU).
- Query reverse-image-search providers by driving their real public pages with a
  browser (Scrapling): **Yandex**, **Bing Visual Search**, **Google Lens** —
  returning only the public URLs those engines surface.
- Re-rank results locally by cosine similarity between your face and the face in
  each result, mapped to a 0–100 **face similarity score** with labeled bands.
- Persist each search to SQLite, cache thumbnails on disk, and support
  "load more" pagination per provider.

It **does not**, by design:

- Name people or make any identity claim. Results are public URLs only.
- Scrape private social media or build a private face index.
- Fabricate results. **If an engine throws a CAPTCHA/anti-bot wall, that provider
  returns `[]` plus a "blocked" note and is skipped; the others still return
  results. CAPTCHAs are never bypassed and results are never invented.**
- Label anything as a "match", "identity", or "probability" — only "similarity".

An **experimental forensics panel** (AI-generated / manipulation-ELA / deepfake
heuristics) is available behind a toggle. It is clearly labeled low-confidence,
not evidence, and is wrapped so it can never block or fail the search path.

---

## Stack

- **Frontend:** Next.js 14 (app router), JavaScript/JSX (typed via JSDoc),
  dev server on port 3000.
- **Backend:** FastAPI + Uvicorn, on `127.0.0.1:8000`.
- **Face detection / embedding:** InsightFace `buffalo_l` on CPU
  (`CPUExecutionProvider`), 512-d float32 L2-normalized embeddings.
- **Providers:** Scrapling browser automation of the public Yandex / Bing /
  Google Lens reverse-image pages (no API key).
- **Storage:** SQLite (WAL) + an on-disk thumbnail cache.
- **Deployment:** local install only. **There is no Docker** — no Dockerfile, no
  compose. A Python venv + npm is the whole setup.

---

## Pipeline (end to end)

```
upload (multipart image)
   │
   ▼
InsightFace buffalo_l ── detect LARGEST face ── crop + normalize ── 512-d L2-normalized embedding (the "query face")
   │                                                   │
   │                                                   └── cropped face JPEG  ──┐
   ▼                                                                            │
no face?  ── 422 no_face_detected                                               ▼
                                                         browser reverse-image-search (Scrapling)
                                                          (Yandex / Bing / Google Lens, no key)
                                                                                │
                                              public results (image_url, thumbnail_url, page_url, page_title, provider)
                                                                                │
                                                            download each thumbnail to on-disk cache
                                                                                │
                                              re-detect + embed the largest face in each result thumbnail
                                                                                │
                                          cosine similarity (dot product of normalized vectors) ── 0–100 score
                                                                                │
                                        dedup by image_url, rank desc (stable tie-break) ── persist to SQLite
                                                                                │
                                                              ▼  ranked grid in the UI
```

"Load more" continues each provider from its saved pagination cursor and
re-ranks the whole search after each new batch.

### Score bands (single source of truth)

Score = `round(((cosine + 1) / 2) * 100)`, clamped to `[0, 100]` (both vectors
are already L2-normalized, so cosine is a plain dot product).

| Band         | Range  | Label                          |
|--------------|--------|--------------------------------|
| `very_close` | 95–100 | Very close visual similarity   |
| `strong`     | 85–94  | Strong visual similarity       |
| `weak`       | 70–84  | Weak visual similarity         |
| `unrelated`  | 0–69   | Likely unrelated               |
| `no_face`    | (null) | No face detected (ranks last)  |

These are defined once in `backend/services/ranking.py` (`SCORE_BANDS`) and
mirrored verbatim in `frontend/lib/bands.js` so the backend and the UI badge
always agree.

---

## Quick start (local install)

Prerequisites: **Python 3.10+**, **Node.js 18+** (with npm).

```bash
git clone <your-fork-url> omnividence
cd omnividence
bash install.sh
```

`install.sh` creates the backend venv (`backend/.venv`) and installs
`backend/requirements.txt`, runs `npm install` in `frontend/`, and copies the
env examples (`.env` and `frontend/.env.local`) if they don't exist yet.

Then start the two processes in separate terminals:

```bash
# Terminal 1 — backend (FastAPI on :8000)
source backend/.venv/bin/activate
cd backend
python main.py
# On first run, InsightFace downloads the buffalo_l model pack into
# backend/data/models — this is a one-time download.

# Terminal 2 — frontend (Next.js on :3000)
cd frontend
npm run dev
```

Open **http://localhost:3000** and upload a face photo.

### Providers

No API key is needed — the providers drive the real public Yandex / Bing /
Google Lens pages with Scrapling's browser. **Yandex** is the most reliable for
faces (it surfaces the same person well); **Bing** adds visually-similar volume;
**Google Lens** is the most bot-hostile and is often CAPTCHA-walled. If an engine
is blocked it's skipped and reported honestly; the others still return results.
`GET /health` lists which providers can run. CAPTCHAs are never bypassed.

---

## Configuration

Backend env vars (all optional). See `.env.example`:

| Variable                     | Default                           | Purpose                                                            |
|------------------------------|-----------------------------------|-------------------------------------------------------------------|
| `OMNI_DATA_DIR`              | `./backend/data`                  | Base data dir (DB, thumbs, models). Created on startup.            |
| `OMNI_DB_PATH`               | `${OMNI_DATA_DIR}/omnividence.db` | SQLite file path.                                                 |
| `OMNI_THUMB_CACHE_DIR`       | `${OMNI_DATA_DIR}/thumbs`         | Thumbnail cache dir (`<sha256(image_url)>.jpg`).                   |
| `OMNI_INSIGHTFACE_ROOT`      | `${OMNI_DATA_DIR}/models`         | InsightFace model cache (buffalo_l downloads here once).           |
| `OMNI_MAX_RESULTS_PER_PAGE`  | `20`                              | Max results per provider per page before ranking.                 |
| `OMNI_THUMB_TIMEOUT_SEC`     | `10`                              | Per-thumbnail download timeout (seconds).                         |
| `OMNI_CORS_ORIGINS`          | `http://localhost:3000`           | Comma-separated allowed CORS origins.                             |

Frontend env (`frontend/.env.local`, see `frontend/.env.local.example`):

| Variable              | Default                  | Purpose                                                          |
|-----------------------|--------------------------|------------------------------------------------------------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000`  | Base URL of the FastAPI backend. Must be `NEXT_PUBLIC_*` to be readable in the browser. |

---

## API surface

All search request/response JSON is owned by `backend/api/routes/search.py`.

| Method | Path                                        | Purpose                                                             |
|--------|---------------------------------------------|---------------------------------------------------------------------|
| POST   | `/api/search`                               | Upload image (`image`, optional `providers`), run the full pipeline, return ranked results. |
| GET    | `/api/search/{search_id}/more`              | Fetch + rank the next page from each non-exhausted provider.        |
| GET    | `/api/search/{search_id}`                   | Return all cached results (optional `provider`/`band`/`sort` query). |
| GET    | `/api/search/{search_id}/thumb/{result_id}` | Serve a cached result thumbnail JPEG (or redirect to its URL).      |
| GET    | `/api/search/{search_id}/query-face`        | Serve the saved cropped query-face JPEG.                            |
| POST   | `/api/forensics`                            | **Experimental**, wrapped, never on the search path.               |
| GET    | `/health`                                   | `{status, version, model_loaded, providers_configured}`.           |

Notable response cases (honest by design):

- **No face in upload:** `422 {"error":"no_face_detected", ...}`.
- **A provider CAPTCHA-walled:** `200`; that provider contributes `results: []`
  with a `note` of "blocked", and the others still return results.
- **Bad/oversized upload:** `400 {"error":"invalid_image", ...}`.

---

## Project layout

```
omnividence/
├── README.md            # this file
├── SPEC.md              # authoritative product spec
├── HANDOFF.md           # engineering handoff / architecture notes
├── install.sh           # local installer (backend venv + frontend npm)
├── VERSION              # semver (2.0.0)
├── .env.example         # backend env template
├── backend/             # FastAPI app, providers, services, tests
│   ├── main.py          # app entry: CORS, startup init, routes, /health
│   ├── config.py        # OMNI_* env, paths
│   ├── requirements.txt
│   ├── api/routes/      # search.py (orchestrator), forensics.py (experimental)
│   ├── providers/       # base.py ABC + _browser.py (Scrapling) + yandex / bing / google_lens
│   ├── services/        # face.py, ranking.py, cache.py, detection.py (forensics heuristics)
│   └── data/            # gitignored: omnividence.db, thumbs/, models/
└── frontend/            # Next.js 14 app router (JS/JSX, JSDoc-typed)
    ├── app/             # layout (Disclaimer always-visible), page, search/[id]
    ├── components/      # Uploader, ResultsGrid, ResultCard, ScoreBadge, ...
    └── lib/             # api.js, bands.js (mirror), types.js
```

---

## Tests

A formal `backend/tests/` suite is not shipped in this build. The pure logic is
quick to exercise by hand from an activated venv, e.g.:

```bash
source backend/.venv/bin/activate
cd backend
python -c "from services import ranking as r; \
print(r.to_score(1.0), r.to_score(0.0), r.to_score(-1.0)); \
print([b['key'] for b in [r.band_for(100), r.band_for(90), r.band_for(75), r.band_for(10), r.band_for(None)]])"
# Provider gating with no key returns [] + an honest note, never fabricated:
python -c "from providers import get_providers; \
print([p.search('x.jpg') for p in get_providers('')])"
```

The first prints `100 50 0` and the band keys
`['very_close','strong','weak','unrelated','no_face']`; the second prints three
pages each with empty `results` and a `"provider not configured"` note.

---

## Safety & honesty (enforced in code and UI)

1. **Never fabricate results.** No key ⇒ empty results + a "not configured" note;
   the pipeline still runs and reports it.
2. **No identity claims.** No names, ever — only public URLs returned by
   providers.
3. **The label is always "face similarity score"** — never "match probability"
   or "identity confidence". The words *match / identity / probability* do not
   appear next to a score.
4. **The disclaimer is always visible**, rendered in the root layout on every
   page and state.
5. **Local install is the only supported path.** No Docker.
6. **The forensics panel is optional and experimental**, behind a toggle, and
   wrapped so it can never block or fail the search.

---

## Version

Omnividence **2.0.0** — provider-driven reverse-image-search + local
face-embedding re-rank. (1.x was a local-FAISS-index OSINT framing and has been
fully replaced; see `HANDOFF.md`.) Versioning is semantic (Major.Minor.Patch);
the current version lives in `VERSION` and is reported by `/health` and
`/version`.
