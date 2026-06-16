# OSINT Face Search - Multi-stage Dockerfile
# Builds a containerized Flask API with InsightFace and FAISS for face recognition

# ============================================================================
# Stage 1: Builder - Compile dependencies and prepare environment
# ============================================================================
FROM python:3.10-slim as builder

# Set working directory
WORKDIR /build

# Install system dependencies required for compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    cmake \
    git \
    wget \
    ca-certificates \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements_api.txt .

# Create wheels for faster installation in final stage
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements_api.txt

# ============================================================================
# Stage 2: Runtime - Minimal final image
# ============================================================================
FROM python:3.10-slim

# Set labels and metadata
LABEL maintainer="OSINT Face Search Team"
LABEL description="OSINT Face Recognition API with InsightFace and FAISS"
LABEL version="1.0.0"

# Set environment variables
ENV FLASK_APP=app.py \
    FLASK_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create app user for security (non-root)
RUN groupadd -r osint && useradd -r -g osint osint

# Set working directory
WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libssl3 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder stage
COPY --from=builder /build/wheels /wheels

# Install Python dependencies from wheels
RUN pip install --no-cache /wheels/* && rm -rf /wheels

# Copy application code
COPY --chown=osint:osint app.py .
COPY --chown=osint:osint face_engine.py .
COPY --chown=osint:osint faiss_index.py .
COPY --chown=osint:osint api_config.py .
COPY --chown=osint:osint api_utils.py .
COPY --chown=osint:osint detection.py .

# Create necessary directories with proper permissions
RUN mkdir -p /app/data /app/logs /tmp/osint_uploads /tmp/osint_cache /tmp/osint_index \
    && chown -R osint:osint /app /tmp/osint_* \
    && chmod 755 /app /app/data /app/logs

# Switch to non-root user
USER osint

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Expose port
EXPOSE 5000

# Run the application with gunicorn
CMD ["gunicorn", \
     "--bind=0.0.0.0:5000", \
     "--workers=4", \
     "--worker-class=gevent", \
     "--worker-connections=1000", \
     "--timeout=120", \
     "--access-logfile=-", \
     "--error-logfile=-", \
     "--log-level=info", \
     "app:app"]
