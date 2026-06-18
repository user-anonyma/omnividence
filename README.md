<img width="2172" height="724" alt="omnividence" src="https://github.com/user-attachments/assets/b8864c1a-0c03-44a2-a14f-f78c32c23538" />

A reverse face search OSINT tool.

Upload a photo containing a face. Omnividence finds the largest face in the image, searches public reverse image
engines for where similar faces appear online, and ranks the results by how
closely each face matches the inputed face. Shown as a **visual face similarity score**
(0–100), highest first.


## How it works

1. You upload an image.
2. InsightFace detects and crops the largest face, then turns it into a numeric
   face embedding.
3. The cropped face is sent to public reverse-image search engines — **Yandex**,
   **Bing**, and **Google Lens** — driven by a real browser (Scrapling). No API
   keys.
4. Each public result image is re-checked for a face and scored against yours by
   cosine similarity, mapped to 0–100.
5. Results are de-duplicated and shown ranked from best match down.

Score bands: **95–100** very close · **85–94** strong · **70–84** weak ·
**below 70** likely unrelated.

## Features

- Face-similarity search with results sorted high→low score.
- Three providers (Yandex is the most reliable for faces; Google Lens is often
  blocked by anti-bot and is skipped honestly when it is).
- Filter by provider and score band, and sort ascending/descending.
- **Load more** to pull additional results.
- An **experimental forensics panel** (AI-generated / manipulation / deepfake
  heuristics) behind a toggle — clearly labeled low-confidence, not evidence.

## What it will not do

- Name people or claim identity — it only shows public image URLs and a
  similarity score.
- Scrape private social media, or solve/bypass CAPTCHAs.
- Invent results. A blocked or failed provider returns nothing and says so.

## Run it (local only, no Docker)

Requires **Python 3.10+** and **Node.js 18+**.

```bash
git clone https://github.com/user-anonyma/omnividence.git
cd omnividence
bash install.sh
```

Then start the two servers in separate terminals:

```bash
# Terminal 1 — backend (http://localhost:8000)
source backend/.venv/bin/activate && cd backend && python main.py

# Terminal 2 — frontend (http://localhost:3000)
cd frontend && npm run dev
```

Open **http://localhost:3000** and upload a face photo. (On first run InsightFace
downloads its model once.)

## Stack

Next.js (frontend) · FastAPI (backend) · InsightFace `buffalo_l` (face detection
+ embeddings) · Scrapling (browser automation) · SQLite (cache).

See `HANDOFF.md` for the architecture and `SPEC.md` for the product spec.
