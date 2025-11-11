FROM python:3.9-slim

# Install system dependencies for TTS and audio processing
RUN apt-get update && apt-get install -y \
    # Required for pyttsx3 (offline TTS)
    espeak \
    libespeak1 \
    # Required for audio processing
    ffmpeg \
    # Useful for debugging
    curl \
    # Clean up to reduce image size
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better Docker cache utilization
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    # Install additional TTS providers
    pip install --no-cache-dir edge-tts pyttsx3 aiohttp

# Copy application code
COPY . /app

# Create necessary directories with proper permissions
RUN mkdir -p /app/audio_files /app/tts_cache && \
    chmod 755 /app/audio_files /app/tts_cache

# Set environment variables for production
ENV PYTHONUNBUFFERED=1
ENV TTS_PROVIDER=edge

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/ || exit 1

# Expose port
EXPOSE 8001

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]