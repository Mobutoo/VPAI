# Remotion Server — ARM64 (Raspberry Pi 5)
# Node.js 22 + Chrome Headless Shell ARM64
# Express API server for rendering video compositions

FROM node:22-bookworm-slim

# Chrome Headless Shell dependencies (ARM64)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxshmfence1 \
    fonts-noto-color-emoji \
    fonts-liberation \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy package files first (Docker layer cache)
COPY package.json package-lock.json* ./

RUN npm ci --production && \
    npx remotion browser ensure

# Copy application source
COPY src/ ./src/
COPY remotion.config.ts ./

# Create output directory
RUN mkdir -p /app/output /app/creative-assets && \
    chown -R 1000:1000 /app

USER 1000:1000

EXPOSE 3200

CMD ["node", "src/server.js"]
