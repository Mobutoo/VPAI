# ComfyUI Docker — ARM64 CPU-only (Raspberry Pi 5)
# Base: Python 3.12 slim (NOT Alpine — native C deps required)
# PyTorch CPU wheel for ARM64
# v0.17.1+ includes App Mode + App Builder (frontend >= 1.41.13)

ARG COMFYUI_VERSION=v0.17.1

# === Stage 1: Build dependencies ===
FROM python:3.12-slim-bookworm AS builder

ARG COMFYUI_VERSION

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Clone ComfyUI at pinned version (repo migrated to Comfy-Org)
RUN git clone --depth 1 --branch "${COMFYUI_VERSION}" \
    https://github.com/Comfy-Org/ComfyUI.git /build/comfyui

# Install PyTorch CPU (ARM64 native wheel) — must be installed BEFORE requirements.txt
RUN pip install --no-cache-dir --target=/build/deps \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# Install ComfyUI requirements (includes comfyui-frontend-package for App Mode)
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

# --force-fp32: required for ARM64 stability (no GPU, avoids fp16 fallback issues)
CMD ["python", "main.py", "--cpu", "--force-fp32", "--listen", "0.0.0.0", "--port", "8188"]
