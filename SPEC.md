# Omnividence — Product Spec (authoritative)

Build a **school tech-showcase prototype for face-similarity search**, NOT a
surveillance or identification system.

## Goal

A demo web app where a user uploads an image, the app detects/crops the visible
face, sends the cropped image to reverse-image-search providers, collects visually
similar public image results, then **locally re-ranks them using face-embedding
similarity**. The app displays a **"face similarity score," not "identity
confidence."**

## Safety / product constraints (HARD — enforce in code and UI)

- This is for a controlled school demo.
- Do NOT scrape private social media.
- Do NOT identify people by name.
- Do NOT claim matches prove identity.
- Only show **public image result URLs** returned by supported search providers.
- Label scores as **visual similarity only**.
- UI disclaimer, always visible: **"Results are approximate visual similarity
  matches and do not confirm identity."**

## Stack

- **Frontend:** Next.js
- **Backend:** FastAPI
- **Face detection/embeddings:** InsightFace (RetinaFace/SCRFD detect + ArcFace
  embed). 512-d, float32, L2-normalized embeddings.
- **Search providers:**
  - Yandex reverse image / image search
  - Bing Visual Search
  - Google Lens (via SerpApi or similar provider)
  - NOTE: In practice all three are reached cleanly via **SerpApi** (one key →
    Google Lens + Yandex + Bing engines). Build providers behind a common
    interface, each gated on the provider key. With no key configured, a provider
    returns an empty list with a clear "not configured" note — never fabricate.
- **Storage/cache:** SQLite (demo).
- **Docker Compose:** OPTIONAL only. Local install (Python venv + npm) is the
  primary, documented path. Do not make Docker required.

## Core flow

1. User uploads an image.
2. Backend detects the **largest** face.
3. Crop / normalize the face.
4. Send cropped face image to the configured reverse-image-search APIs.
5. Collect returned image URLs, thumbnails, page titles, source links.
6. Download thumbnails / preview images.
7. Run local face detection on each result.
8. Generate embeddings for the query face and each result face.
9. Compute cosine similarity.
10. Convert similarity to a display score 0–100%.
11. Rank results by score.
12. Show top results with: thumbnail, source URL, provider, similarity score,
    "open source page" link.
13. "Load more" button fetches the next page from providers and re-ranks.

## API routes

- `POST /api/search` — accepts uploaded image; returns `search_id` + first ranked
  results.
- `GET /api/search/{search_id}/more` — loads more results from providers, re-ranks,
  returns next results.
- `GET /api/search/{search_id}` — returns cached results.

## Similarity label

Use **"Face similarity score"**, not "match probability."

Score bands:
- 95–100: very close visual similarity
- 85–94: strong visual similarity
- 70–84: weak visual similarity
- below 70: likely unrelated

## Modularity (required file layout)

- `providers/yandex.py`
- `providers/bing.py`
- `providers/google_lens.py`
- `services/face.py`
- `services/ranking.py`
- `services/cache.py`
- `api/routes/search.py`

Build a working MVP first with **one provider** (Google Lens via SerpApi), then make
it trivial to add the others (shared `providers/base.py` interface).

## Plus — features already discussed (fold in, but keep them optional/secondary)

- Optional **image forensics** panel (AI-generated / manipulation / deepfake),
  clearly labeled **experimental / low-confidence**, behind a toggle, wrapped so it
  can never block the search path.
- Result **filtering** (by provider, by score band) and **sorting**.
- Batch handling is secondary; the single-image flow above is the priority.

## Definition of done

Upload a face photo → backend crops the largest face → (with a provider key set)
providers return public images → each is re-embedded and scored → results render in
the Next.js UI as a ranked grid with thumbnail, provider, source link, and a 0–100
face-similarity score, with the identity disclaimer always visible. Without a
provider key, the whole pipeline runs and clearly reports "no provider configured"
instead of faking results.
