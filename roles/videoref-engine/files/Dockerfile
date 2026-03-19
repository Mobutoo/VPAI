FROM python:3.12-slim-bookworm

# System deps: ffmpeg (keyframes, LUT, export), wget (healthcheck), git (whisper.cpp)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg wget git build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
RUN pip install --no-cache-dir \
    aiohttp watchfiles Pillow numpy \
    kokoro>=0.9 soundfile

# whisper.cpp — build from source for ARM64 native performance
RUN git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git /opt/whisper.cpp && \
    cd /opt/whisper.cpp && \
    make -j$(nproc) && \
    ln -s /opt/whisper.cpp/main /usr/local/bin/whisper-cpp

# Download whisper base model (500MB — good quality/speed tradeoff on RPi5)
RUN mkdir -p /opt/whisper.cpp/models && \
    wget -q -O /opt/whisper.cpp/models/ggml-base.bin \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin

# Download Kokoro TTS model (82M params — lightweight, fast on CPU)
RUN python -c "import kokoro; kokoro.KPipeline(lang_code='a')" 2>/dev/null || true

# LUT presets for color grading
COPY luts/ /app/luts/

COPY app.py /app/app.py

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=10s --retries=5 --start-period=60s \
    CMD wget -qO- http://127.0.0.1:8082/health || exit 1

CMD ["python", "app.py"]
