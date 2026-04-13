# GrapeJS HTML Visual Editor
# Stage 1: Install GrapeJS via npm (fetches pinned assets at build time)
FROM node:22.14-alpine AS deps
WORKDIR /app
RUN npm init -y && \
    npm install \
      grapesjs@0.21.13 && \
    npm cache clean --force

# Stage 2: Nginx static server (ARM64 + amd64 via buildx)
FROM nginx:1.27.4-alpine
LABEL org.opencontainers.image.title="GrapeJS HTML Editor" \
      org.opencontainers.image.version="0.21.13" \
      org.opencontainers.image.source="https://github.com/Mobutoo/vpai"

# GrapeJS assets (JS + CSS) from npm
COPY --from=deps /app/node_modules/grapesjs/dist /usr/share/nginx/html/assets/grapesjs

# Editor HTML (single-page app — no build step required)
COPY index.html /usr/share/nginx/html/index.html

EXPOSE 80
