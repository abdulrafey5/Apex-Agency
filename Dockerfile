# Multi-stage build for Apex-Agency Inception App
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY app/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.12-slim

# Install runtime dependencies (including gosu for user switching)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/app/logs /app/storage /app/app/static /app/app/templates && \
    chown -R appuser:appuser /app

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/
COPY migrations/ ./migrations/

# Copy entrypoint script (runs as root to fix permissions, then switches to appuser)
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh && \
    chown root:root /docker-entrypoint.sh

# Set ownership
RUN chown -R appuser:appuser /app

# Expose port
EXPOSE 8000

# Set PYTHONPATH to match EC2 setup
ENV PYTHONPATH=/app/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Set entrypoint to fix permissions before running
ENTRYPOINT ["/docker-entrypoint.sh"]

# Run Gunicorn (matches EC2 systemd service)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "120", "--preload", "app.main:app"]