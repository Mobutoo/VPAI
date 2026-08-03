# Revue adversariale — Prisme CANARY-1b (client fetcher↔prisme) — 2026-08-03

> Reviewer : agent Opus. Périmètre : `fd47112..9c53f79` (3 commits). Verdict : **NO-GO** —
> 1 CRITICAL / 2 HIGH / 5 MED (M4 pré-existant) / 4 LOW. Non-régression disabled prouvée
> (unité byte-identique, additions python gardées par INSTAGRAM_ENABLED).

## CRITICAL
- **C1** py.j2:1633-1638+189-190 : `not_provisioned` → l'API répond **404** (dispatcher.ts:321-323)
  → HTTPError → `InstagramAuthorizationCheckFailed` → handle_failure → failed terminal à 5
  tentatives + **unlink du fichier job**. L'état PAR DÉFAUT avant activation détruit la file.
  Le heartbeat subit le même 404 → gate 5 jamais verte. Fix : brancher HTTPError.code==404 sur
  la branche « denied » non-consommante (state=not_provisioned) + corriger le commentaire +
  documenter la précondition d'ordonnancement.

## HIGH
- **H1** py.j2:213-215 : `checked_at` armé APRÈS l'appel → sur exception, chaque job de la passe
  refait un appel réseau (N jobs = N requêtes → sature le bucket 120/60s partagé heartbeat →
  429 → check_failed → auto-amplification). Fix : armer avant l'appel ou en finally.
- **H2** : InstagramAuthorizationCheckFailed routé sur handle_failure = budget PAR JOB consommé
  par la panne d'une dépendance PARTAGÉE → maintenance prisme 1 h = file entière failed +
  fichiers effacés ; attempts partagés vérification/acquisition. Fix : traiter comme
  `gate is None` (pending, 0 tentative) + compteur global d'échecs consécutifs →
  event `instagram_control_plane_unreachable` (observable, jamais destructeur).

## MEDIUM
- **M1** service.j2 : IPAddressAllow /32 = TOUT l'hôte Sese joignable (pas de granularité port :
  vhosts Caddy llm./mayi./…, sshd:804). URL des jobs bloquées applicativement (ALLOWED_DOMAINS
  vide → rejected avant réseau) mais les SOUS-REQUÊTES yt-dlp/gallery-dl (allowlist_scope=
  input_url_only) n'avaient QUE le filtre noyau A5 — désormais ouvert vers Sese. Fix : corriger
  le commentaire « trou étroit » + acter le risque dans A5 (ou unité dédiée control-plane).
- **M2** verify.yml : heartbeat asserté NULLE PART (stub muet, pas de log). Fix : stub journalise
  dans un jsonl + asserts (≥1 POST, status=ready, adapterVersion non vide, token invalide→401).
- **M3** : `degraded` jamais émis — heartbeat mesure la vivacité du process, pas la santé de
  l'adapter (cookies expirés = ready quand même). Dériver d'un compteur d'échecs OU documenter.
- **M4** (PRÉ-EXISTANT) roles/prisme/molecule converge : vault_prisme_fetcher_token absent →
  molecule prisme rouge dès fd47112. Fix 1 ligne dans converge.yml.
- **M5** : jobs pending sans TTL ni plafond (connecteur revoked = accumulation indéfinie) ;
  débit 1 job IG/20 s par passe (throttle) non documenté. Fix : TTL/métrique de profondeur ou doc.

## LOW
- L1 sentinelle checked_at=None au lieu de 0.0 (time.monotonic point de référence indéfini).
- L2 regex CIDR laxiste (999.999.999.999/32 passe) → ipaddr ou regex stricte.
- L3 print() du handler d'erreur heartbeat hors try → BrokenPipe tue le thread en silence.
- L4 commentaire getent « controller » ↔ s'exécute sur la cible.

## Sains (vérifiés) : zéro fuite token (EnvironmentFile, pas argv, pas dans jobs.error) ; arrêt
thread propre <TimeoutStopSec ; REX-62 OK (vault présent + asserts) ; LOI OK ; signalé hors
périmètre : roles/prisme/tasks:29-38 passe PRISME_LITELLM_KEY en argv docker exec (pré-existant).
