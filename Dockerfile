# Dockerfile for LightOn Workflow Generator
# Multi-stage build for optimized image size

# Stage 1: Base image with Python 3.12
FROM python:3.12-slim AS base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Dependencies installation
FROM base AS dependencies

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 3: Final runtime image
FROM base AS runtime

# Copy installed dependencies from previous stage
COPY --from=dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Copy application code
COPY api/ /app/api/
COPY index.html /app/
COPY lighton-logo.png /app/

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
# 8000 for FastAPI backend (also serves frontend)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/appuser/.local/bin:$PATH"

# Default command: start FastAPI backend (serves both API and frontend)
CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "8000"]
