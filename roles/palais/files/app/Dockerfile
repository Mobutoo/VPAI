# Stage 1: Builder
FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
# DATABASE_URL required by SvelteKit SSR analysis at build time (lazy postgres pool, no actual connection)
ARG DATABASE_URL=postgresql://build:build@localhost:5432/build
ENV DATABASE_URL=$DATABASE_URL
RUN npm run build
RUN npm prune --omit=dev

# Stage 2: Runtime
FROM node:22-alpine

RUN apk add --no-cache dumb-init

WORKDIR /app

COPY --from=builder /app/build ./build
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
COPY --from=builder /app/drizzle ./drizzle

RUN addgroup -g 1000 palais && adduser -u 1000 -G palais -s /bin/sh -D palais
RUN mkdir -p /data/deliverables /data/avatars && chown -R palais:palais /data

USER palais

EXPOSE 3300

ENV PORT=3300
ENV HOST=0.0.0.0

ENTRYPOINT ["dumb-init", "--"]
CMD ["node", "build"]
