# Remotion Render Server — ARM64 (Raspberry Pi 5)
# Based on official template: remotion-dev/template-render-server
# Uses system Chromium (ARM64 native) instead of Playwright Chrome download
# REX: npx remotion browser ensure fails on ARM64 (Playwright CDN 400)
#      Use apt chromium + REMOTION_CHROME_EXECUTABLE to bypass

FROM node:22-bookworm-slim

# Install system Chromium + dependencies (ARM64 native package)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    libnss3 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm-dev \
    libasound2 \
    libpangocairo-1.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxshmfence1 \
    libxkbcommon-dev \
    libxfixes3 \
    fonts-noto-color-emoji \
    fonts-liberation \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy package files first for layer caching
COPY package.json package-lock.json* ./

RUN npm ci

# Copy all source files
COPY . .

# Bundle the Remotion composition at build time
RUN npx remotion bundle remotion/index.ts
# Bundle output goes to "build/" by default
ENV REMOTION_SERVE_URL=build

# Use system Chromium (ARM64 native — bypasses Playwright CDN)
ENV CHROME_EXECUTABLE_PATH=/usr/bin/chromium
# Skip Remotion's automatic browser download
ENV PUPPETEER_SKIP_DOWNLOAD=true

# Create runtime dirs
RUN mkdir -p renders creative-assets && \
    chown -R 1000:1000 /app

ENV NODE_ENV=production
ENV PORT=3200

USER 1000:1000

EXPOSE 3200

CMD ["npx", "tsx", "server/index.ts"]
