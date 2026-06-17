# Omnividence — Engineering Handoff

Read this top to bottom before touching code. It describes what Omnividence
**is now** (v2.0.0), how the pieces fit, the exact shared interfaces every file
implements to, and the honesty/safety rules that are enforced in code and UI.

> v1.x was a different program: a local-FAISS-index "OSINT tool" that tried to be
> a Clearview/PimEyes clone. That framing is **gone**. v2 is a **school
> face-similarity search demo**: it sends a cropped face to reverse-image-search
> providers and **locally re-ranks** the public results by face-embedding
> similarity. There is no local face index and no identity claim anywhere.

---

## 1. What the program is

Omnividence is a **school tech-showcase prototype for face-similarity search**,
**NOT** a surveillance or identification system. You upload a photo. It:

1. Detects the **largest** visible face, crops + normalizes it, and embeds it to
   a 512-d L2-normalized vector (the "query face").
2. Sends the **cropped face JPEG** to reverse-image-search providers by driving
   their real public pages with Scrapling's browser (Yandex, Bing, Google Lens) —
   no API key.
3. Downloads each public result thumbnail, re-detects + embeds the largest face
   in it, and computes cosine similarity to the query face.
4. Maps cosine to a **0–100 face similarity score**, dedups by image URL, ranks,
   persists to SQLite, and renders a ranked grid.

The output label is always **"face similarity score"**, never "match
probability" or "identity confidence". The app **never names people** and only
shows **public URLs** the providers returned.

---

## 2. Architecture

```
omnividence/
├── backend/                         # FastAPI, local-only (127.0.0.1:8000)
│   ├── main.py                      # app: CORS, startup init_db()+init_model(), routes, /health
│   ├── config.py                    # OMNI_* + SERPAPI_KEY env vars, paths, dir creation
│   ├── requirements.txt
│   ├── api/routes/
│   │   ├── search.py                # ONLY place touching request/response JSON (orchestrator)
│   │   └── forensics.py             # experimental, wrapped, off the search path
│   ├── providers/
│   │   ├── base.py                  # Provider ABC + ProviderResult/ProviderPage TypedDicts
│   │   ├── _browser.py              # Scrapling DynamicFetcher helper (run_action, looks_blocked)
│   │   ├── __init__.py              # get_providers() registry
│   │   ├── yandex.py                # browser scrape of Yandex Images (most reliable)
│   │   ├── bing.py                  # browser scrape of Bing Visual Search
│   │   └── google_lens.py           # browser scrape of Google Lens (most bot-hostile)
│   ├── services/
│   │   ├── face.py                  # InsightFace buffalo_l: detect largest, crop, embed 512-d L2
│   │   ├── ranking.py               # SCORE_BANDS, cosine, to_score, band_for, rank_and_dedup
│   │   ├── cache.py                 # ALL SQLite + thumbnail disk I/O + cursor state
│   │   └── forensics.py             # experimental heuristics, wrapped
│   └── data/                        # gitignored: omnividence.db, thumbs/, models/ (buffalo_l)
└── frontend/                        # Next.js 14 app router, JS/JSX (:3000)
    ├── app/                         # layout (always-visible Disclaimer), page, search/[id]
    ├── components/                  # Uploader, ResultsGrid, ResultCard, ScoreBadge, Disclaimer, LoadMore, FilterSort, DetectionPanel
    └── lib/                         # api.js, bands.js (verbatim mirror of ranking.py), types.js
```

> **Deployment: local install only. There is NO Docker in this project** — do
> not add a Dockerfile or compose. Backend is a Python venv; frontend is npm.
> See `install.sh` and the README.

### Module ownership (do not cross these lines)

- `providers/base.py` — the `Provider` ABC and the normalized `ProviderResult` /
  `ProviderPage` dict shapes every provider yields. **No provider fabricates
  results.**
- `services/face.py` — detect (largest face) + crop/normalize + embed. Owns
  InsightFace.
- `services/ranking.py` — cosine → 0–100, the score bands, and rank+dedup. The
  **single source of truth** for bands.
- `services/cache.py` — **all** SQLite and thumbnail-disk I/O plus pagination
  cursor state. Nothing else touches the DB.
- `api/routes/search.py` — orchestrates the pipeline and is the **only** place
  that constructs request/response JSON.

---

## 3. Pipeline, end to end

`POST /api/search` (multipart `image`, optional `providers` CSV):

1. Validate upload (size ≤ ~10 MB, decodable image) → else
   `400 invalid_image`.
2. `face.detect_largest_face(bytes)` → if `None`, `422 no_face_detected`.
3. `face.crop_face_jpeg(...)` → the cropped-face JPEG (saved as
   `query_thumb_path`, also sent to providers).
4. `cache.create_search(embedding, bbox, det_score, query_thumb_path,
   providers_used, note)` → `search_id` (uuid4 hex).
5. For each selected provider: `provider.search(face_path, cursor=None)`. Un-
   configured providers return `[]` + a "not configured" note (no key path).
   Persist each provider's `next_cursor` / exhausted state via
   `cache.upsert_cursor(...)`.
6. For each `ProviderResult`: `cache.get_or_download_thumbnail(image_url,
   thumbnail_url)` → embed via `face.embed_face(thumb_path)` → if a face is
   found, `score = ranking.to_score(ranking.cosine(query, result))`; else
   `score=None`, band `no_face`.
7. `ranking.rank_and_dedup(rows)` → dedup by `image_url` (keep highest score),
   sort score desc then (provider asc, image_url asc), assign 1-based `rank`,
   set `band`.
8. `cache.store_results(...)` (INSERT OR IGNORE on `UNIQUE(search_id,image_url)`)
   then `cache.rerank_search(search_id)`.
9. Return the page; `cache.mark_returned(...)` the rows sent. `has_more` =
   `cache.any_more_available(search_id)`.

`GET /api/search/{id}/more`: reload cursors, call `provider.search(face_path,
cursor=saved_cursor)` for each non-exhausted provider, download+embed+score the
new batch, **re-rank the whole search**, and return **only** the newly-added
(previously unreturned) results.

**Determinism:** sort by score desc, then provider asc, then image_url asc.
Dedup keeps the highest-scoring row per `image_url`. `no_face` (score `None`)
ranks last.

---

## 4. Scoring (single source of truth)

Cosine is a **plain dot product** because both vectors are already
L2-normalized. Score:

```
score = round(((cosine + 1) / 2) * 100), clamped to [0, 100]
```

Bands live once in `backend/services/ranking.py` as `SCORE_BANDS` and are
mirrored **verbatim** in `frontend/lib/bands.js` so the backend and `ScoreBadge`
agree exactly:

| key          | range  | label                        |
|--------------|--------|------------------------------|
| `very_close` | 95–100 | Very close visual similarity |
| `strong`     | 85–94  | Strong visual similarity     |
| `weak`       | 70–84  | Weak visual similarity       |
| `unrelated`  | 0–69   | Likely unrelated             |
| `no_face`    | null   | No face detected (ranks last)|

If you change a band, change it in **both** files in the same commit. The words
*match / identity / probability* must never appear next to a score — only
*similarity*.

---

## 5. Storage (owned entirely by `services/cache.py`)

SQLite (WAL), tables created idempotently by `init_db()` at startup. ISO-8601
UTC timestamps.

- `searches` — one row per upload. `query_embedding` is 512 float32
  L2-normalized stored as `np.tobytes()` (2048 bytes). `query_face_bbox` is JSON
  `[x1,y1,x2,y2]` in original-upload pixel coords. `note` is a JSON array of
  human-readable strings.
- `results` — one row per public image hit. `UNIQUE(search_id, image_url)`
  enforces dedup. `score` is `0–100` or `NULL` (no face). `band` is one of the
  five keys. `returned` is `0` (buffered) / `1` (sent). `rank` is the global
  rank after the most recent re-rank.
- `provider_cursors` — per `(search_id, provider)` continuation state:
  `next_cursor` (opaque JSON string, `NULL` when exhausted), `page_index`,
  `exhausted`.
- `thumb_cache` — `image_url → thumb_path` with `status` `ok|failed`. Files at
  `<OMNI_THUMB_CACHE_DIR>/<sha256(image_url)>.jpg`.

`any_more_available()` is `True` if any provider is not exhausted **OR** any
`results` row has `returned=0`.

---

## 6. Providers & pagination

Every provider subclasses `Provider` (in `providers/base.py`) and implements
`search(image_path, cursor=None) -> ProviderPage`.

- **Availability-gating.** If `not self.is_configured()` (Scrapling's browser
  isn't importable) return `_unavailable_page()` — `{"results": [],
  "next_cursor": None, "note": "<name>: browser automation unavailable ..."}`.
- **On a CAPTCHA/anti-bot wall**, return `_blocked_page()` — `{"results": [],
  "next_cursor": None, "note": "<name>: blocked ..."}`. CAPTCHAs are never bypassed.
- **On any browser/parse error**, catch and return `_error_page(detail)` —
  never raise, never fabricate.
- On success, scrape up to 20 (`RESULT_LIMIT`) public hits from the results page
  via the provider's `_EXTRACT_JS`. One page per provider for the demo, so
  `next_cursor` is always `None` (no pagination / mass scraping).

`get_providers(api_key)` returns
`[GoogleLensProvider, YandexProvider, BingProvider]`. The route persists each
returned `next_cursor` into `provider_cursors.next_cursor` and, on `/more`, calls
each non-exhausted provider with its saved cursor, then updates the cursor (or
marks `exhausted=1` when `next_cursor` is `None`).

**This is the biggest architectural difference from v1:** there is no private
face index to match against. Recall is whatever the public reverse-image
engines surface; Omnividence's contribution is the **face-embedding re-rank** on
top of those public results. Coverage and recall are bounded by the providers,
and that is reported honestly (empty/not-configured notes).

---

## 7. Honesty / safety rules (HARD — enforced in code + UI)

1. **Never fabricate results.** A blocked/unavailable provider returns `[]` +
   an honest note ("blocked" / "browser automation unavailable"); the route still
   runs the full pipeline and
   reports the empty/not-configured state honestly.
2. **No identity claims, never name people** — only public URLs returned by
   providers.
3. **The label is always "face similarity score"**, never "match probability" /
   "identity confidence".
4. **The disclaimer** "Results are approximate visual similarity matches and do
   not confirm identity." is **ALWAYS visible**, rendered once in
   `app/layout.jsx` so it shows on every page and state.
5. **Local install is the primary (only) path** — Python venv + npm. No Docker,
   no Dockerfile.
6. **The forensics panel is OPTIONAL + EXPERIMENTAL**, behind a toggle, wrapped
   so it can NEVER block or fail the search path.

The forensics endpoint (`POST /api/forensics`) is wrapped in try/except: any
internal failure returns `200` with all checks `label="unavailable"` and a note,
never a 5xx. It is never invoked on the search path.

---

## 8. Local setup

Prereqs: Python 3.10+, Node 18+. Then:

```bash
bash install.sh          # backend venv + pip, frontend npm, copy env examples
```

Run (two terminals):

```bash
# backend
source backend/.venv/bin/activate && cd backend && python main.py   # :8000
# frontend
cd frontend && npm run dev                                          # :3000
```

`buffalo_l` downloads into `backend/data/models` on first run (one-time).
Providers need no key — run `scrapling install` once to fetch the browser. If an
engine is CAPTCHA-walled it's skipped and reported; the others still return
results. `GET /health` shows `{status, version, model_loaded, providers_configured}`.

---

## 9. Tests

`backend/tests/`:

- `test_ranking.py` — cosine→score mapping, band boundaries, dedup/rank
  determinism (stable tie-break).
- `test_providers_gating.py` — no-key path returns `[]` + note; never
  fabricates.
- `test_face.py` — smoke: detect + embed a sample face → 512-d L2-normalized
  vector.

```bash
source backend/.venv/bin/activate && cd backend && pytest
```

---

## 10. Versioning

Semantic Versioning (Major.Minor.Patch). Current: **2.0.0** (in `VERSION`,
reported by `/health` and `/version`). The 1.x → 2.0.0 bump reflects the full
re-architecture from a local-index OSINT tool to a provider-driven,
re-ranking face-similarity demo. After any change to the system, bump the
version and commit.
