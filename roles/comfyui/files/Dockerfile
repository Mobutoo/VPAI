# ComfyUI Docker — ARM64 CPU-only (Raspberry Pi 5)
# Base: Python 3.12 slim (NOT Alpine — native C deps required)
# PyTorch CPU wheel for ARM64

ARG COMFYUI_VERSION=v0.3.27

# === Stage 1: Build dependencies ===
FROM python:3.12-slim-bookworm AS builder

ARG COMFYUI_VERSION

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Clone ComfyUI at pinned version
RUN git clone --depth 1 --branch "${COMFYUI_VERSION}" \
    https://github.com/comfyanonymous/ComfyUI.git /build/comfyui

# Install PyTorch CPU (ARM64 native wheel)
RUN pip install --no-cache-dir --target=/build/deps \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# Install ComfyUI requirements
RUN pip install --no-cache-dir --target=/build/deps \
    -r /build/comfyui/requirements.txt

# === Stage 2: Runtime ===
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 comfyui && \
    useradd -u 1000 -g comfyui -m -s /bin/bash comfyui

WORKDIR /app

# Copy ComfyUI source
COPY --from=builder /build/comfyui /app

# Copy Python dependencies
COPY --from=builder /build/deps /usr/local/lib/python3.12/site-packages

# Create volume mount points
RUN mkdir -p /app/models /app/output /app/input /app/custom_nodes && \
    chown -R 1000:1000 /app

USER 1000:1000

EXPOSE 8188

CMD ["python", "main.py", "--cpu", "--listen", "0.0.0.0", "--port", "8188"]
