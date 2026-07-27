# Handoff — brancher chat.ewutelo.cloud vers lxc-chat (Banga) via le hub Caddy de Sese

## Objectif

Ajouter `chat.ewutelo.cloud` au hub Caddy existant (tourne sur Sese, `javisi_caddy`), qui doit
faire un **second saut** (reverse proxy) vers `lxc-chat` (Open WebUI) hébergé sur **Banga** —
contrairement à `llm`/`tala`/`mayi` qui pointent vers des services tournant directement sur Sese.
Garder EN PLUS l'accès LAN direct existant côté Banga (Caddy local auto-signé sur `lxc-chat`,
§6 du design `docs/superpowers/specs/2026-07-24-lxc-chat-design.md` du repo `banga`) — les deux
accès doivent coexister, pas remplacer l'un par l'autre (décision opérateur explicite).

## Décisions prises (ne pas rediscuter)

- **Repos concernés** : `VPAI` (Caddy central + subdomain vars) et `Seko-VPN` (DNS via Headscale
  `extra_records`). **PAS le repo `banga`** — celui-là gère seulement le Caddy local de `lxc-chat`,
  déjà écrit, ne pas y toucher pour ce chantier sauf pour lire des valeurs.
- **Mécanisme déjà en place, à répliquer, pas à réinventer** :
  - DNS : `Seko-VPN/inventory/group_vars/all/vars.yml:56-64`, variable `nodes_extra_records` — une
    liste de nœuds Headscale, chacun avec `tailscale_ip` + une liste `domains`. Le nœud `sese`
    (`tailscale_ip: 100.64.0.14`) porte déjà `javisi.ewutelo.cloud`, `tala.ewutelo.cloud`,
    `mayi.ewutelo.cloud`, `llm.ewutelo.cloud`, `qd.ewutelo.cloud`. **`chat.ewutelo.cloud` doit être
    ajouté à CETTE liste `domains` du nœud `sese`** (pas un nouveau nœud — le DNS pointe toujours
    vers Sese, c'est le Caddy de Sese qui refait un saut vers Banga en interne).
  - Reverse proxy + certificat réel : `VPAI/roles/caddy/templates/Caddyfile.j2` — Caddy sur Sese
    obtient un certificat Let's Encrypt via **DNS-01 chez OVH** (`acme_dns ovh`, credentials déjà
    configurés en variables d'env Docker `OVH_APPLICATION_KEY`/`OVH_APPLICATION_SECRET`/
    `OVH_CONSUMER_KEY`/`OVH_ENDPOINT` — ne PAS en générer de nouveaux, ils existent déjà et
    fonctionnent pour `llm`/`tala`/`mayi`). Modèle à suivre : bloc "=== Grafana - dedicated
    subdomain (tala) ===" (~ligne 179 du fichier) — même structure pour un nouveau bloc `chat`.
  - Convention de variable : `VPAI/inventory/group_vars/all/main.yml:18-20` —
    `grafana_subdomain: "tala"`, `n8n_subdomain: "mayi"`, `litellm_subdomain: "llm"`. Ajouter une
    variable équivalente (ex. `lxc_chat_subdomain: "chat"`) suivant EXACTEMENT ce pattern.
- **La cible du reverse_proxy n'est PAS un autre service sur Sese, mais Banga (hôte différent)** —
  différence structurelle avec tous les blocs existants :
  - `lxc-chat` tourne dans un LXC sur Banga, **pas membre tailnet lui-même** (seul le host Proxmox
    `banga-node` est enrôlé Headscale, en subnet-router annonçant `192.168.1.0/24` — cf design
    banga §6). Pour que Sese atteigne `lxc-chat`, la route subnet de Banga doit être **acceptée
    côté Sese** dans Headscale (`headscale routes list`/`enable` — action d'admin Headscale, PAS
    automatisable depuis ce repo sans vérifier l'état actuel d'abord).
  - Le Caddy local de `lxc-chat` (port 443, cert **auto-signé** `tls internal`) doit être accepté
    par le Caddy de Sese comme upstream — directive Caddy standard pour ignorer la vérification
    d'un cert auto-signé sur un hop interne connu (`transport http { tls_insecure_skip_verify }`
    ou équivalent). Ne PAS tenter de faire confiance au cert via un mécanisme plus complexe — c'est
    un hop interne entre deux Caddy qu'on contrôle, l'auto-signé + skip-verify est le pattern
    standard et suffisant ici (le vrai cert public reste côté Sese, face aux clients).
  - **Port ciblé : uniquement `443` (Open WebUI)**. Le port `8443` de `lxc-chat` (API M2M
    whisper.cpp/ffmpeg-API, protégée par jeton bearer) n'a **aucune raison** de passer par ce
    domaine public-facing — ne pas l'exposer via `chat.ewutelo.cloud`.
- **L'IP LAN réelle de `lxc-chat` sur Banga N'EST PAS ENCORE FIGÉE** au moment de ce handoff — un
  déploiement est en cours en parallèle dans une session `/factor` séparée sur le repo `banga`
  (`factor-lxc-chat-finalize`), qui doit poser une réservation DHCP statique sur la Freebox pour la
  MAC `BC:24:11:3D:41:13` (même mécanisme que `lxc-infer` → `192.168.1.20`). **Ne pas deviner cette
  IP** — vérifier `banga:.planning/STATE.md` (chercher "lxc-chat"/"réservation"/"IP") ou demander
  directement à l'opérateur où en est cette réservation avant de finaliser le bloc `reverse_proxy`.
  Le reste du travail (variable subdomain, entrée DNS, structure du bloc Caddy, vérification de la
  route Headscale) peut avancer sans attendre cette IP précise.
- **Ne jamais casser `llm`/`tala`/`mayi` en prod** — Sese sert ces 3 domaines en live. Toute
  modification de `Caddyfile.j2` doit être validée (`caddy validate`) avant tout reload, et les 3
  domaines existants re-testés après le changement (pas juste le nouveau).
- **Secrets** : aucun nouveau secret attendu (les credentials OVH DNS-01 existent déjà et sont
  partagés par tous les domaines de ce Caddy) — si un besoin de secret apparaît quand même,
  `ansible-vault` doctrine habituelle, jamais improvisé.

## Chemins / artefacts

- `Seko-VPN/inventory/group_vars/all/vars.yml:56-64` (`nodes_extra_records`, à éditer — ajouter
  `chat.ewutelo.cloud` à la liste `domains` du nœud `sese`)
- `Seko-VPN/roles/headscale/defaults/main.yml:12` (`nodes_extra_records: []`, valeur par défaut,
  ne pas toucher — c'est la surcharge `group_vars` qui compte)
- `Seko-VPN/roles/headscale/templates/config.yaml.j2:42,71-72` (templating `extra_records`, pour
  comprendre comment la liste est rendue, ne devrait pas nécessiter de modif)
- `Seko-VPN/roles/headscale/files/policy.hujson.draft` (référence existante des nœuds/domaines,
  vérifier si un doc similaire liste aussi les domaines — cohérence à maintenir)
- `VPAI/inventory/group_vars/all/main.yml:18-20` (`grafana_subdomain`/`n8n_subdomain`/
  `litellm_subdomain`, ajouter l'équivalent pour chat)
- `VPAI/roles/caddy/templates/Caddyfile.j2` (~ligne 179 "Grafana - dedicated subdomain (tala)" =
  modèle à copier pour le bloc `chat`, ~ligne 40-48 = bloc `acme_dns ovh` déjà en place)
- `VPAI/roles/caddy/molecule/default/converge.yml` (tests molecule existants pour ce rôle —
  `n8n_subdomain`/`litellm_subdomain`/`grafana_subdomain` y sont stubés, ajouter l'équivalent si un
  nouveau test molecule est pertinent, sinon au moins vérifier que les tests existants passent
  encore après le changement)
- Référence côté Banga (lecture seule, ne pas modifier depuis cette session) :
  `banga/docs/superpowers/specs/2026-07-24-lxc-chat-design.md` (§6 sécurité/accès),
  `banga/roles/lxc-chat/defaults/main.yml` (`lxc_chat_caddy_openwebui_port: 443`,
  `lxc_chat_caddy_api_port: 8443`, MAC `BC:24:11:3D:41:13`),
  `banga/.planning/STATE.md` (état du déploiement en cours, IP éventuellement déjà connue)
- **Avant de commencer** : lire les `CLAUDE.md`/LOI propres à `VPAI` et `Seko-VPN` (conventions,
  process de revue éventuel — ne pas supposer que la doctrine du repo `banga` s'applique telle
  quelle ici, ce sont des repos différents avec potentiellement leurs propres règles).

## Prochaine étape

1. Lire `VPAI/CLAUDE.md` et `Seko-VPN/CLAUDE.md` (conventions du repo, process de revue).
2. Vérifier l'état actuel de la route Headscale Banga→Sese : la route subnet `192.168.1.0/24`
   annoncée par `banga-node` est-elle déjà acceptée côté Sese ? (`headscale routes list` ou
   équivalent — commande exacte à retrouver dans `Seko-VPN/roles/headscale/`). Si non acceptée,
   c'est un préalable bloquant avant tout test de connectivité réel.
3. Vérifier l'état du déploiement `lxc-chat`/réservation IP côté `banga` (`.planning/STATE.md` ou
   directement demander à l'opérateur) — sans IP stable, le bloc `reverse_proxy` ne peut pas être
   finalisé (peut être préparé avec un placeholder documenté en attendant).
4. Ajouter `chat.ewutelo.cloud` à `nodes_extra_records` (Seko-VPN) et déployer ce rôle sur Seko
   (ou la procédure habituelle de ce repo pour appliquer un changement Headscale).
5. Ajouter la variable `lxc_chat_subdomain` (ou nom cohérent) + le nouveau bloc Caddy dans
   `Caddyfile.j2` (VPAI), `reverse_proxy` vers l'IP LAN de `lxc-chat` sur Banga, port 443, avec
   skip-verify sur le cert auto-signé upstream. `caddy validate` avant tout déploiement réel.
6. Déployer, puis tester : `chat.ewutelo.cloud` répond avec un certificat public valide (pas
   d'avertissement navigateur), ET `llm`/`tala`/`mayi` répondent toujours normalement (non-
   régression explicite, pas supposée).
7. Rapporter à l'opérateur : l'URL finale fonctionnelle, et confirmer que l'accès LAN direct
   (`https://<IP-banga>`) fonctionne toujours en parallèle.

## Gates humains

- **Toute modification touchant le Caddy de production de Sese** (qui sert `llm`/`tala`/`mayi`
  en live) : tester avant déploiement (`caddy validate` minimum), non-régression des 3 domaines
  existants vérifiée après coup, pas juste supposée.
- **Acceptation de la route Headscale Banga→Sese** (si pas déjà faite) : action d'admin réseau,
  confirmer avec l'opérateur avant de l'activer si ce n'est pas déjà en place.
- **IP LAN finale de `lxc-chat`** : ne pas deviner — vérifier l'état réel côté `banga` ou demander.
- **Coordination avec la session `/factor` Banga en cours** (`factor-lxc-chat-finalize`) : ne pas
  dupliquer son travail (elle gère le déploiement `lxc-chat` + la réservation IP côté Freebox),
  ce handoff ne couvre QUE le branchement du nom de domaine/reverse-proxy côté Sese.
