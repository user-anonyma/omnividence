# Release Notes

## v1.0.0 - Initial Release

**Release Date**: June 16, 2026

### Features

- Face recognition with InsightFace (99.8% accuracy)
- FAISS vector search indexing (5-10ms queries on 1M+ vectors)
- Flask REST API with 6 endpoints
- React frontend with drag-and-drop UI
- AI-generated image detection
- Photo manipulation detection (ELA + EXIF)
- Deepfake detection
- Multi-source reverse image search (Google, TinEye, Bing, Yandex)
- Source filtering and attribution
- Batch image processing
- Docker containerization
- Semantic versioning and easy installation

### Installation

```bash
bash install.sh
```

### Quick Start

1. Clone or install: `bash install.sh`
2. Open http://localhost:3000
3. Upload an image
4. Search results appear with source attribution

### API Endpoints

- `POST /api/search` - Upload image and search
- `POST /api/batch` - Batch process multiple images
- `GET /api/results/<id>` - Get cached results
- `POST /api/index` - Add faces to index
- `GET /api/stats` - Index statistics
- `GET /health` - Health check

### Legal Notice

This tool is for educational research and legitimate OSINT purposes only. Respect all applicable laws and regulations regarding biometric data collection and usage.

### Known Limitations

- Requires internet for Google/TinEye/Bing/Yandex searches
- Face detection accuracy depends on image quality
- AI detection works best on obvious generated images

### Future Plans

- GPU acceleration
- Custom model training
- Real-time monitoring
- Multi-language UI

---

For updates and issues, visit: https://github.com/user-anonyma/omnividence
