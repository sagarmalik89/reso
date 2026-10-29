# ============================================================
# Printer Agent - Multi-Stage Docker Build
# ============================================================
# Stage 1: Builder — installs dependencies into a clean venv
# Stage 2: Runtime — minimal production image
# ============================================================

# ── Stage 1: Build ──────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# System packages needed for pywin32 alternatives & PDF support
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (better layer caching)
COPY requirements.txt .

# Install dependencies into a virtualenv inside /build/venv
RUN python -m venv /build/venv \
    && /build/venv/bin/pip install --upgrade pip \
    && /build/venv/bin/pip install --no-cache-dir \
        watchdog \
        schedule \
        python-docx \
        colorama \
        tabulate \
        click \
        fastapi \
        "uvicorn[standard]" \
        python-multipart \
        jinja2 \
        "qrcode[pil]" \
        pillow \
        pypdf \
        requests \
        aiofiles


# ── Stage 2: Runtime ────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN addgroup --system printagent \
    && adduser --system --ingroup printagent --no-create-home printagent

WORKDIR /app

# Copy virtualenv from builder
COPY --from=builder /build/venv /venv

# Copy application source
COPY main.py .
COPY requirements.txt .
COPY printer_agent/ ./printer_agent/

# Create required runtime directories
RUN mkdir -p uploads logs watch_folder processed failed \
    && chown -R printagent:printagent /app

# Activate venv by adjusting PATH
ENV PATH="/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8000

# Expose web portal port
EXPOSE 8000

# Health check — polls /login (no auth required)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/login', timeout=8)" || exit 1

USER printagent

# Start the web server
CMD ["python", "main.py", "web", "--host", "0.0.0.0", "--port", "8000"]
