# GrapeJS HTML Visual Editor — wizy
# Stage 1: Install GrapeJS + Express (pinned, fetched at build time)
FROM node:22.14-alpine AS deps
WORKDIR /app
RUN npm init -y && \
    npm install \
      grapesjs@0.21.13 \
      express@4.19.2 \
      multer@2.1.1 \
      mammoth@1.12.0 && \
    npm cache clean --force

# Stage 2: Node runtime (serves static files + API + SSE)
FROM node:22.14-alpine
LABEL org.opencontainers.image.title="GrapeJS HTML Editor — wizy API" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.source="https://github.com/Mobutoo/vpai"

WORKDIR /app

# Dependencies
COPY --from=deps /app/node_modules ./node_modules

# API server
COPY server.js ./server.js

# Static files: editor + GrapeJS assets
RUN mkdir -p public/assets/grapesjs
COPY --from=deps /app/node_modules/grapesjs/dist ./public/assets/grapesjs
COPY index.html ./public/index.html

EXPOSE 80
CMD ["node", "server.js"]
