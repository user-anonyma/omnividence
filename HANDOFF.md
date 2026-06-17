# Omnividence — Engineering Handoff & Fix Brief

Hand this whole file to Claude Code in the omnividence repo. It explains what the
program is supposed to be, how each piece works, what is most likely broken, the
datasets required, and a prioritized plan to get it actually functioning. Read it
top to bottom before touching code.

---

## 1. What the program is

Omnividence is a **face-recognition reverse image search / OSINT tool**. You give
it a photo. It answers: *"where else does this face appear?"* It does that in two
ways at once:

1. **Local search** — against a FAISS vector index built from face datasets you
   have indexed (your own collected images, public datasets, etc.).
2. **External reverse image search** — by querying public engines (Google Images,
   TinEye, Bing, Yandex) with the uploaded image and scraping/aggregating results.

On top of search it runs **image forensics**: AI-generated-image detection,
photo-manipulation detection (Error Level Analysis + EXIF), and a basic deepfake
check.

It is NOT, and cannot cheaply become, a Clearview/PimEyes clone. Those work because
they scraped billions of faces off the open web into a private index. Read section 6
on this — it is the single biggest reason the tool "doesn't really work": there is
no large index behind it, so there is nothing to match against.

---

## 2. Architecture — how it's supposed to work

```
omnividence/
├── app.py                 # Flask backend, REST API (6 endpoints)
├── face_engine.py         # face detection + 512-d embeddings (InsightFace)
├── faiss_index.py         # FAISS vector search + SQLite metadata
├── detection.py           # AI / manipulation / deepfake detection
├── requirements.txt
├── install.sh             # local installer (Python venv + npm)
└── osint-react-frontend/  # React 18 UI (drag-drop upload, results grid)
```

> **Deployment: local install only. There is no Docker in this project** — do not
> add a Dockerfile or docker-compose. Setup is a Python venv for the backend and
> npm for the frontend (see `install.sh` and section 8).

**Pipeline, end to end:**

1. **Detect + embed** (`face_engine.py`). InsightFace uses an SCRFD/RetinaFace
   detector to find faces, crops + aligns each, then ArcFace (R100) produces a
   **512-dimensional embedding** per face. Embeddings must be **L2-normalized** so
   that cosine similarity = inner product.
2. **Index + search** (`faiss_index.py`). Embeddings go into a FAISS index. Search
   is nearest-neighbor by inner product (cosine on normalized vectors). A SQLite DB
   stores per-vector metadata: image path, source URL, identity/label, bbox,
   provenance. A search returns the top-k closest faces with similarity scores.
3. **API** (`app.py`). Flask exposes:
   - `POST /api/search` — upload image, return face matches
   - `POST /api/batch` — batch process many images
   - `GET  /api/results/<id>` — fetch cached results
   - `POST /api/index` — add faces to the index
   - `GET  /api/stats` — index statistics
   - `GET  /health` — health check
4. **External reverse search**. For each uploaded image, query Google/TinEye/Bing/
   Yandex and aggregate the hits with source attribution. **See section 5 — this is
   almost certainly faked or stubbed in the current code.**
5. **Forensics** (`detection.py`). AI-gen detection (frequency-domain heuristics),
   manipulation (ELA + EXIF inconsistency), deepfake (facial-landmark consistency).
6. **Frontend**. React app on :3000 talks to Flask on :5000. Drag-drop upload,
   results grid with similarity scores, source filtering.

**Stack:** Python 3.10+ / Flask, InsightFace (ArcFace R100) on onnxruntime, FAISS,
SQLite, React 18. Local install only (Python venv + npm) — no Docker.

---

## 3. The features (what the UI/API should deliver)

- Face detection + 512-d embedding extraction from any uploaded image
- Multi-face handling (an image with several people returns matches per face)
- Local FAISS similarity search with ranked results + similarity scores
- External reverse image search aggregation (Google/TinEye/Bing/Yandex)
- Source attribution + clickable links per result
- Source/type filtering (Instagram, LinkedIn, public records, etc.)
- AI-generated image detection with confidence
- Manipulation detection (ELA + EXIF)
- Deepfake detection (landmark consistency)
- Batch processing of many images
- REST API for programmatic use
- One-command local install (`install.sh`: Python venv + npm)

---

## 4. Datasets needed (this is mandatory, not optional)

The local search is useless until the index has faces in it. You must build the
index from real data. Options, roughly in order of ease:

- **LFW** (Labeled Faces in the Wild) — ~13k images, 5.7k people. Great smoke-test
  set: small, labeled, standard benchmark.
- **CelebA / CelebA-HQ** — ~200k celebrity images / 30k high-res. Good for scale +
  identity labels.
- **VGGFace2** — ~3.3M images, 9k identities. This is the one for a serious index.
- **Your own collected set** — for real OSINT use you index images you've gathered
  with known identities. Each row needs: image, identity label, source URL.

Indexing flow: run every dataset image through `face_engine.py` to get embeddings,
write them to FAISS + the SQLite metadata table via `POST /api/index` (or a bulk
loader script — build one, see task list). Without this step, every search returns
empty and the app looks "broken" even when the code is fine.

**Legal/ethical:** biometric search on real people is regulated (GDPR/BIPA, etc.).
Keep it to public datasets, consented images, and authorized investigations. Put
this constraint in the README and don't index scraped private data.

---

## 5. Why it's "not really working" — most likely root causes

Check these in order. In projects like this, the failure is almost always #1–#4,
not the model code.

1. **The index is empty.** No dataset was ever indexed, so `/api/search` returns
   nothing. Fix: build a bulk indexer + index LFW as a smoke test. Confirm
   `/api/stats` shows a non-zero vector count.
2. **External engines are stubbed/mocked.** Google/TinEye/Bing/Yandex have **no
   free face-search APIs**. The current code very likely returns hardcoded/fake
   "results" or silently fails. Either (a) integrate a real provider (SerpAPI,
   a paid TinEye API key, Bing Image Search API) and gate it behind an API key, or
   (b) cut the feature honestly and label local-only. Do not ship fake results.
3. **InsightFace model not downloaded / onnxruntime broken.** First run must pull
   the model pack (e.g. `buffalo_l`). If onnxruntime isn't installed for the right
   platform (CPU vs GPU/CUDA), face detection throws or returns zero faces. Verify
   a single known image produces a 512-d vector before anything else.
4. **Embeddings not normalized → wrong similarity.** If vectors aren't L2-normalized
   and the FAISS index uses inner product, scores are garbage. Normalize on both
   index and query side. Confirm same-person similarity ≈ high (>0.5), different
   people low.
5. **FAISS index type mismatch.** IVF/PQ indexes must be **trained** before adding
   vectors and need enough vectors to be meaningful. For a first working version
   use a flat index (`IndexFlatIP`) — exact, no training, correct by construction.
   Optimize to IVF+PQ only once it works and the dataset is large.
6. **Frontend ↔ backend mismatch.** React on :3000, Flask on :5000 — check the API
   base URL the frontend uses and CORS on the Flask side. A "nothing happens on
   upload" symptom is usually this, not the model.
7. **detection.py is heuristic and unreliable.** Frequency-based AI detection and
   landmark-based deepfake detection are weak and will produce confident-but-wrong
   output. Treat as low-confidence/experimental, label clearly, or replace with a
   real trained classifier later. Don't let it block the core search path.
8. **Model cache / index not persisted.** The InsightFace model pack and the FAISS
   index + SQLite DB must live in stable on-disk paths so they survive restarts and
   aren't re-downloaded / rebuilt every run. Use fixed local paths, not temp dirs.

---

## 6. The honesty section — set expectations correctly

The "search the whole internet for this face" capability (Clearview/PimEyes) is not
something this codebase can do as written, because:

- There is **no public API** that does face search across the open web for free.
- Replicating it means **scraping and indexing billions of face images** — massive
  storage, compute, and serious legal exposure.

What this tool **can** realistically be, done well:

- A solid **local face search** over datasets you control (this is genuinely useful
  and is the part to get rock-solid first).
- **Reverse *image* search** (not face search) via paid/keyed providers, which finds
  exact/near-duplicate images, not "the same person in a different photo."
- A clean API + UI around both.

Build the local search until it's excellent. Add external search only with a real,
keyed provider, clearly labeled. Cut or flag the forensic heuristics.

---

## 7. Prioritized fix plan (do these in order)

1. **Get one image to embed.** Load InsightFace, run a single test photo, assert you
   get N faces and a 512-d normalized vector. Fix model download / onnxruntime here.
2. **Stand up a flat index.** Use `IndexFlatIP` + SQLite metadata. Add the test
   vector, search it against itself, confirm similarity ≈ 1.0.
3. **Write a bulk indexer script.** Point it at a dataset folder, embed every face,
   populate FAISS + SQLite. Index **LFW** as the smoke test. Confirm `/api/stats`
   shows the right count.
4. **Wire `/api/search` to the real index.** Upload an image of someone in the
   dataset, confirm they come back as the top match with a sane score. This is the
   core loop working.
5. **Fix the frontend↔backend connection.** Upload from the UI, see real results.
   Resolve API base URL + CORS.
6. **Decide on external search.** Either integrate one real keyed provider behind an
   env var and label it, or remove the fake multi-engine results entirely.
7. **Quarantine the forensics.** Mark AI/manipulation/deepfake detection as
   experimental/low-confidence so it doesn't mislead. Improve later.
8. **Persist state on disk.** Put the model cache + FAISS index + SQLite DB at fixed
   local paths so they survive restarts. No Docker — local install only.
9. **Write a real README** reflecting what it actually does, with the dataset setup
   step front and center.

Definition of done for "it works": index LFW, upload a photo of someone in LFW, get
them back as the top match in the UI with a similarity score. Everything else is
enhancement on top of that.

---

## 8. Environment / setup notes

- Python 3.10+, create a venv, `pip install -r requirements.txt`.
- InsightFace needs onnxruntime (CPU) or onnxruntime-gpu (CUDA). Pick one and make
  requirements.txt match the target machine.
- First run downloads the model pack — needs internet once, then cache it.
- Frontend: `cd osint-react-frontend && npm install && npm start` (:3000).
- Backend: `python app.py` (:5000). Make the frontend's API base URL configurable.
- Keep any external-search API keys in env vars, never hardcoded.
```
