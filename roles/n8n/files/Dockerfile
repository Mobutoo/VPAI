# n8n Enterprise-Unlocked
# Thin patch layer over official n8n image
# Unlocks all enterprise features (Projects, Insights, Variables, Log Streaming, etc.)
#
# Build:  docker build -t ghcr.io/mobutoo/n8n-enterprise:2.7.3 .
# Push:   docker push ghcr.io/mobutoo/n8n-enterprise:2.7.3

ARG N8N_VERSION=2.7.3
FROM n8nio/n8n:${N8N_VERSION}

USER root

# Apply license patches to compiled JS (idempotent sed)
COPY patch-enterprise.sh /tmp/patch-enterprise.sh
RUN chmod +x /tmp/patch-enterprise.sh \
    && /tmp/patch-enterprise.sh \
    && rm /tmp/patch-enterprise.sh

USER node
