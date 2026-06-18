# Omnividence — Exact Stack & Architecture

A school demo for **face-similarity search**: upload a face photo, it finds many
visually-similar/identical faces across public images and ranks them by a 0–100
face-similarity score. Not an identity/surveillance tool; every result carries a
"does not confirm identity" disclaimer.

The design pattern is **broad engine recall + local re-ranking**: use a
reverse-image engine to fetch lots of candidate images, then re-score each one
locally with a face-recognition model. (This is the same pattern FaceCheck/PimEyes
use; we just use a free engine for recall instead of a private face index.)

---

## 1. Tech stack (exact)

| Layer | Tech |
|---|---|
| Frontend | **Next.js 14** (app router), JavaScript/JSX, dev server on port 3000 |
| Backend | **FastAPI** + **Uvicorn**, bound to 127.0.0.1:8000 |
| Face detection + embeddings | **InsightFace** `buffalo_s` model pack (SCRFD-500M detector + MobileFaceNet recognizer), run on CPU via **onnxruntime**. 512-dim L2-normalized embeddings. det_size 320; only the `detection` + `recognition` sub-models are loaded |
| Reverse-image scraping | **Scrapling** (`DynamicFetcher`) driving a headless Chromium (patchright/Playwright under the hood). No API keys |
| Image / thumbnail handling | Pillow, OpenCV (cv2), httpx (thumbnail downloads) |
| Storage | **SQLite** (search rows, results, provider cursors, thumbnail cache index) + on-disk thumbnail cache folder |
| Hosting (demo) | `cloudflared` quick tunnel → the Next.js dev server; Next.js `rewrites` proxy `/api` + `/health` to the FastAPI backend so it's one same-origin URL (no CORS) |

No paid APIs, no API keys. Local install only (Python venv + npm), no Docker.

---

## 2. The end-to-end flow

```
Browser (Next.js)
  │  POST /api/search   (multipart: the uploaded image)
  ▼
FastAPI  ── InsightFace: detect the LARGEST face → crop → 512-d embedding ("query face")
  │        ── create a search row in SQLite (status='running'), return search_id IMMEDIATELY
  │        ── spawn a background worker thread (the scraping is slow; we don't hold the request)
  │
  │  (background worker)
  │   for each selected provider (default: Yandex only), run concurrently (max 2 at once):
  │     1. Scrapling opens the engine in headless Chromium, uploads the cropped face
  │     2. Yandex → navigate to the "similar images" grid (cbir_page=similar), scroll to lazy-load,
  │        scrape up to ~45 candidate image URLs + source links
  │     3. for each candidate: download the thumbnail → InsightFace embed it →
  │        cosine similarity vs the query face → 0–100 score
  │     4. DROP anything with no face or score < 50; store the rest in SQLite; re-rank
  │     5. update progress (0→100) as each provider finishes
  │
Browser polls  GET /api/search/{id}  every 2.5s
  ▼
  receives {status, progress, results[]} → renders the grid + progress bar,
  results streaming in as they're found, sorted by score (highest first)
```

---

## 3. Why each big decision (the non-obvious parts)

- **Yandex "similar images" grid is the recall engine.** The key unlock: Yandex's
  default reverse-image page only shows ~3 "exact copy" links, but the
  `&cbir_page=similar` view returns a grid of 100s of visually/face-similar images.
  We scrape that grid (`.ImagesContentImage-Image` tiles). Bing and Google Lens are
  optional secondary engines (whole-image matchers, noisier) — Yandex is the default.
- **Local re-ranking with InsightFace/ArcFace.** Engines return candidates by image
  similarity, not identity. We re-embed every candidate face and score cosine
  similarity to the query face, so the final ranking is by actual face similarity,
  and non-faces / unrelated people are filtered out (score < 50 dropped).
- **`buffalo_s` not `buffalo_l`.** The demo box is a no-AVX Intel Celeron (2 cores);
  the heavy model took ~4s per face. `buffalo_s` (lightweight detector + MobileFace)
  is ~11x faster (~0.25s), which is what makes embedding dozens of thumbnails per
  search feasible.
- **Streaming + background worker.** A full search takes ~50s (real browser
  scraping). Holding one HTTP request open that long times out behind proxies/tunnels
  (caused 500s). So POST returns instantly with a `search_id`; a daemon thread does
  the work and writes results incrementally; the frontend polls and shows a progress
  bar. No long-held request, no timeout.
- **Scoring.** Both embeddings are L2-normalized, so cosine = dot product in [-1,1].
  `score = round((cos+1)/2 * 100)`, clamped to [0,100]. Tiers: 90–100 Certain,
  83–89 Confident, 70–82 Uncertain, 50–69 Weak.

---

## 4. Project layout

```
omnividence/
├── backend/                      # FastAPI
│   ├── main.py                   # app, CORS, /health, startup (init DB + model)
│   ├── config.py                 # env config, paths, MIN_SCORE
│   ├── api/routes/
│   │   ├── search.py             # POST /api/search, GET /api/search/{id}(/more),
│   │   │                         #   thumb + query-face routes; the streaming worker
│   │   └── forensics.py          # optional experimental AI/manipulation/deepfake panel
│   ├── providers/
│   │   ├── base.py               # Provider interface + result shape
│   │   ├── _browser.py           # Scrapling helper (run a page action, block detection)
│   │   ├── yandex.py             # cbir_page=similar grid scraper (the main engine)
│   │   ├── bing.py, google_lens.py
│   │   └── __init__.py           # provider registry
│   ├── services/
│   │   ├── face.py               # InsightFace: detect largest face, crop, embed
│   │   ├── ranking.py            # cosine → 0–100, score bands, rank+dedup
│   │   └── cache.py              # ALL SQLite + thumbnail-disk I/O
│   └── requirements.txt
└── frontend/                     # Next.js
    ├── app/page.jsx              # two-column layout: input image left, results grid right
    ├── app/layout.jsx            # imports CSS, always-visible disclaimer
    ├── components/               # Uploader, ResultsGrid, ResultCard, ScoreBadge,
    │                             #   MatchLegend, FilterSort, LoadMore, DetectionPanel
    ├── lib/api.js                # calls /api/* (same-origin)
    ├── lib/bands.js              # score-tier mirror of backend ranking.py
    └── next.config.js            # rewrites /api + /health → backend (same-origin proxy)
```

## 5. API (the 3 that matter)

- `POST /api/search` (multipart `image`, optional `providers` CSV) → `{search_id,
  query_face, status:"running", progress, results:[]}` immediately.
- `GET /api/search/{id}` → `{status, progress, results[], note}`; poll until
  `status:"done"`. Each result: `{image_url, thumb_url, page_url, provider, score,
  band, band_label, rank}`.
- `POST /api/forensics` (optional, experimental) → AI-gen / manipulation / deepfake
  heuristics for the toggle panel.

## 6. Honest limits

- A search is ~50s on the weak demo CPU (the model + real browser scraping), not the
  code — normal hardware is far faster.
- Source labels show "yandex.com" because images come through Yandex's image viewer,
  not always the origin site.
- True biometric identity engines (FaceCheck/PimEyes) need a private scraped face
  index or a paid API; this uses free reverse-image recall + local face re-ranking,
  which is the best no-cost approximation.
