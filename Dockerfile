FROM python:3.12-slim

# Minimal system deps (curl for healthcheck)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better Docker cache utilization
COPY requirements.txt .

# Install Python dependencies (single layer for cache efficiency)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Create necessary directories with proper permissions
RUN mkdir -p /app/audio_files && \
    chmod 755 /app/audio_files 

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONSAFEPATH=1
    # ELEVENLABS_API_KEY must be provided at runtime (compose/env)

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/ || exit 1

# Expose port
EXPOSE 8001

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]