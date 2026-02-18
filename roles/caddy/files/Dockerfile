# Caddy custom build — avec plugin DNS OVH pour challenge ACME DNS-01
# Permet de renouveler les certificats TLS sans ouvrir le port 80.
# Utilisé uniquement si caddy_vpn_only_mode=true (DNS challenge requis).
#
# Build : docker build -t caddy-ovh:${CADDY_VERSION} .
# REX : xcaddy compile un binaire Caddy avec le module dns.providers.ovh
#       embarqué directement — pas de dépendance runtime supplémentaire.

ARG CADDY_VERSION=2.10.2

FROM caddy:${CADDY_VERSION}-builder AS builder

RUN xcaddy build \
    --with github.com/caddy-dns/ovh

FROM caddy:${CADDY_VERSION}-alpine

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
