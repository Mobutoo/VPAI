# OpenCut — Next.js video editor (ARM64)
# Multi-stage: build with Bun, run with Node.js standalone output
#
# FFmpeg processing runs client-side (WASM in browser).
# Server is a lightweight Next.js app serving the editor UI.

ARG OPENCUT_VERSION=v0.1.0

# === Stage 1: Install dependencies + build ===
FROM node:22-slim AS builder

ARG OPENCUT_VERSION

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    python3 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Bun (required by OpenCut's package.json)
RUN npm install -g bun@1.2.18

WORKDIR /build

# Clone OpenCut at pinned version
RUN git clone --depth 1 --branch "${OPENCUT_VERSION}" \
    https://github.com/OpenCut-app/OpenCut.git /build/opencut

WORKDIR /build/opencut

# Install all workspace dependencies
RUN bun install --frozen-lockfile || bun install

# Build the Next.js web app (standalone output for minimal runtime)
WORKDIR /build/opencut/apps/web
ENV NEXT_TELEMETRY_DISABLED=1
# Provide dummy env vars for build time (Next.js needs them at build)
ENV DATABASE_URL="postgresql://dummy:dummy@localhost:5432/dummy"
ENV BETTER_AUTH_SECRET="build-time-placeholder"
ENV UPSTASH_REDIS_REST_URL="http://localhost:8079"
ENV UPSTASH_REDIS_REST_TOKEN="build-time-placeholder"
ENV NEXT_PUBLIC_SITE_URL="http://localhost:3000"
RUN bun run build

# === Stage 2: Runtime ===
FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 opencut && \
    useradd -u 1000 -g opencut -m -s /bin/bash opencut

WORKDIR /app

# Copy Next.js standalone output
COPY --from=builder /build/opencut/apps/web/.next/standalone ./
COPY --from=builder /build/opencut/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /build/opencut/apps/web/public ./apps/web/public

# Copy migrations for db setup
COPY --from=builder /build/opencut/apps/web/migrations ./apps/web/migrations
COPY --from=builder /build/opencut/apps/web/drizzle.config.ts ./apps/web/drizzle.config.ts

RUN chown -R 1000:1000 /app

USER 1000:1000

EXPOSE 3000

ENV NODE_ENV=production
ENV HOSTNAME="0.0.0.0"
ENV PORT=3000

CMD ["node", "apps/web/server.js"]
