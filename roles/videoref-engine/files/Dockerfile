FROM python:3.12-slim-bookworm

# System deps: ffmpeg, wget, cmake (whisper.cpp)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg wget git cmake build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (OCR = Claude Vision via LiteLLM, no local OCR lib needed)
RUN pip install --no-cache-dir \
    aiohttp watchfiles Pillow numpy \
    kokoro>=0.9 soundfile

# whisper.cpp — build from source (repo moved to ggml-org, binary is now whisper-cli)
RUN git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git /opt/whisper.cpp && \
    cd /opt/whisper.cpp && \
    cmake -B build && \
    cmake --build build -j$(nproc) && \
    cp build/bin/whisper-cli /usr/local/bin/whisper-cpp || \
    cp build/bin/main /usr/local/bin/whisper-cpp || true

# Download whisper base model (500MB — good quality/speed tradeoff on RPi5)
RUN mkdir -p /opt/whisper.cpp/models && \
    wget -q -O /opt/whisper.cpp/models/ggml-base.bin \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin

# LUT presets for color grading
COPY luts/ /app/luts/

COPY app.py /app/app.py

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=10s --retries=5 --start-period=120s \
    CMD wget -qO- http://127.0.0.1:8082/health || exit 1

CMD ["python", "app.py"]
