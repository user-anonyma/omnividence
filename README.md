# Omnividence

**Omnividence** is a production-ready face recognition reverse image search OSINT tool. Upload an image, extract faces, search across multiple sources (local index + Google + TinEye + Bing + Yandex), detect AI-generated images, identify photo manipulation, and get ranked results with source attribution.

## Features

- **Face Recognition**: InsightFace ArcFace R100 (99.8% accuracy) face detection and 512-dim embeddings
- **Reverse Image Search**: Local FAISS vector search + Google Images + TinEye + Bing + Yandex aggregation
- **AI Detection**: Detects AI-generated images with confidence scoring
- **Manipulation Detection**: Error Level Analysis (ELA) + EXIF inconsistency detection for Photoshop/manipulation
- **Deepfake Detection**: Basic facial landmark consistency checking
- **Multi-Source Results**: Aggregated results from multiple search engines with source attribution and similarity scores
- **Source Filtering**: Filter results by website/source type (Instagram, LinkedIn, Twitter, public records, etc.)
- **Batch Processing**: Process 100+ images concurrently
- **API Access**: RESTful API for programmatic searches

## Use Cases

- OSINT investigations and background checks
- Educational research on face recognition technology
- Digital footprint analysis
- Fraud detection and identity verification
- Research and development

## Quick Start

Local install only. Run the one-shot installer:

```bash
git clone https://github.com/user-anonyma/omnividence.git
cd omnividence
bash install.sh
```

Then start the two processes (in separate terminals):

```bash
# Backend (terminal 1)
source venv/bin/activate
python app.py            # Runs on http://localhost:5000

# Frontend (terminal 2)
cd osint-react-frontend
npm start                # Runs on http://localhost:3000
```

Then open http://localhost:3000 in your browser.

### Manual setup (if you skip install.sh)

```bash
# Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py  # Runs on localhost:5000

# Frontend (in another terminal)
cd osint-react-frontend
npm install
npm start  # Runs on localhost:3000
```

## Architecture

### Core Components

1. **Face Engine** (`face_engine.py`)
   - InsightFace ArcFace R100 model
   - Detects and extracts faces from images
   - Generates 512-dimensional embeddings

2. **FAISS Indexing** (`faiss_index.py`)
   - Vector similarity search (5-10ms queries on 1M+ vectors)
   - SQLite metadata storage
   - Support for IVF+PQ, IVF+Flat, HNSW index types

3. **Flask API** (`app.py`)
   - 6 REST endpoints for image search, batch processing, results retrieval
   - Integrates with Google, TinEye, Bing, Yandex reverse search APIs
   - Request validation and error handling

4. **React Frontend**
   - Drag-and-drop image upload
   - Results grid with similarity scoring
   - Source attribution and clickable links
   - Filter and sort controls

5. **Detection Models** (`detection.py`)
   - AI-generated image detection (frequency domain analysis)
   - Photo manipulation detection (ELA + EXIF)
   - Deepfake detection (facial landmark consistency)

## API Endpoints

- `POST /api/search` - Upload image, get face matches
- `POST /api/batch` - Batch process multiple images
- `GET /api/results/<id>` - Retrieve cached search results
- `POST /api/index` - Add new faces to index
- `GET /api/stats` - Index statistics
- `GET /health` - Health check

## Data Sources

The tool can search against:

- **Local Index**: Your own face embeddings (CelebA-HQ, custom datasets)
- **Public Datasets**: Mugshots, court records, public figures
- **Search Engines**: Google Images, TinEye, Bing, Yandex
- **User Contributions**: Faces uploaded with consent

## Legal & Ethical

**Important**: This tool is for educational research and legitimate OSINT purposes only.

## Technical Stack

- **Backend**: Python 3.10+ / Flask
- **Face Recognition**: InsightFace (ArcFace R100)
- **Vector Search**: FAISS (IVF+PQ)
- **Database**: SQLite
- **Frontend**: React 18
- **Deployment**: Local install (Python venv + npm)

## Development

### Project Structure

```
omnividence/
├── app.py                 # Flask backend
├── face_engine.py         # Face detection & embeddings
├── faiss_index.py        # Vector search
├── detection.py          # AI/manipulation detection
├── requirements.txt      # Python dependencies
├── install.sh            # Local installer (venv + npm)
├── osint-react-frontend/ # React UI
└── README.md            # This file
```

### Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit changes (`git commit -am 'Add feature'`)
4. Push to branch (`git push origin feature/your-feature`)
5. Open a Pull Request

## Performance

- Face detection: ~100ms per image (GPU: ~20ms)
- Vector search: 5-10ms for 1M vectors
- Multi-source aggregation: 2-5s (depends on API response times)
- Batch processing: 100+ images in parallel

## Known Limitations

- Requires internet for Google/TinEye/Bing/Yandex searches
- Face detection accuracy degrades with poor image quality
- Vector search quality depends on index size and diversity
- AI detection works best on obvious deepfakes/generated images

## Future Roadmap

- [ ] GPU acceleration for face detection
- [ ] Custom model training pipeline
- [ ] Webhook integration for automated scans
- [ ] Advanced filtering (age, gender, quality thresholds)
- [ ] Real-time monitoring for new matches
- [ ] Multi-language UI support

## License

MIT License - See LICENSE file for details

## Disclaimer

This tool is provided for educational research and legitimate OSINT purposes. Users are responsible for complying with all applicable laws and regulations. The authors assume no liability for misuse or legal violations.

## Contact & Support

For issues, feature requests, or research collaboration:
- GitHub Issues: https://github.com/user-anonyma/omnividence/issues
- Research Inquiries: [your contact info]

---

**Built with InsightFace, FAISS, Flask, and React** | Developed for OSINT research and education
