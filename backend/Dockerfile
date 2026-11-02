# ==============================================================================
# Dockerfile for ESP32 Water Tank Monitoring Backend (Render Cloud Deployment)
# ==============================================================================

# Use official lightweight Python 3.11 base image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and ensure stdout/stderr are unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Set application directory inside container
WORKDIR /app

# Install curl for container health checks and clean up apt cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create a non-root service user for enhanced container security
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose default port (Render will dynamically map this via $PORT)
EXPOSE 8000

# Start Uvicorn bound to 0.0.0.0 and dynamically bind to Render's $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
