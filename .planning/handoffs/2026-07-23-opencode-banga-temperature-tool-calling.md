# Handoff — forcer temperature=0 pour le tool-calling OpenCode→Banga

## MISE À JOUR 2026-07-23 (session suivante) — implémenté, déployé, PARTIELLEMENT validé

**Implémenté et déployé sur Waza** (commit non fait, working tree) :
- `roles/opencode/files/plugins/banga-temperature.js` — plugin `chat.params` qui force
  `temperature=0` pour `providerID==="banga"` + `modelID` in `{coder, coder_longctx}`.
  Contourne un bug amont CONFIRMÉ : `agent.temperature` déclaratif n'est jamais inclus
  dans le body `/v1/chat/completions` pour un provider custom `@ai-sdk/openai-compatible`
  (github.com/anomalyco/opencode issues #25755 et #2785, ouverts, aucun fix officiel).
  Le hook `chat.params` mute juste avant `streamText`, indépendant de ce bug.
- `opencode.json.j2` : ajout `"temperature": true` (capability flag models.dev-style) sur
  `coder` et `coder_longctx` — nécessaire pour qu'opencode considère que le modèle
  supporte le paramètre.
- Déployé via `ansible-playbook playbooks/hosts/workstation.yml --tags opencode --diff`
  (lint OK, diff propre, service redémarré, healthcheck OK).
- Preuve indirecte que le forçage temperature=0 fonctionne : sortie texte **byte-identique**
  sur 4/4 essais indépendants (déterminisme = signature de temp 0 ; à temp 0.8 par défaut
  on aurait de la variabilité).

**BUG DÉCOUVERT ET MITIGÉ EN COURS DE VALIDATION (sans rapport avec la température)** :
`banga/coder` (14B, `limit.context: 12288`) part en **boucle infinie de compaction**
dès le premier message via l'API OpenCode réelle — cycle sans fin
assistant vide → `compaction` auto (`overflow: true`) → "exceeded provider's size limit
due to large media attachments" → répète toutes les ~5s, tourne côté serveur
**indépendamment de la connexion client** (curl fermé depuis longtemps, le compteur de
messages continuait de grimper). Stoppé via `POST /session/{id}/abort` + suppression de
session. Reproduit 1x, pas encore isolé plus finement, mais absent sur `coder_longctx`
(`limit.context: 49152`) et `general` (`32768`) testés dans les mêmes conditions →
hypothèse forte : `12288` est trop petit face au system prompt + schémas d'outils de
l'agent `build` par défaut d'OpenCode. **Ne pas relancer de test sur `banga/coder` sans
surveiller le compteur de messages de la session et un `abort` prêt à dégainer** — ça
tourne pour de vrai sur le GPU Banga, pas juste un client qui poll dans le vide.

**CONSTAT BLOQUANT — l'objectif réel du chantier n'est PAS atteint** : même avec
temperature=0 confirmé (déterminisme observé), `banga/coder_longctx` via le **pipeline
OpenCode complet** (agent `build`, vrais schémas d'outils OpenAI-style) répond **4/4 fois**
par un bloc de code texte `` ```bash\ndate +%s\n``` `` au lieu d'un vrai tool_call structuré
— aucun appel d'outil n'est émis. En comparaison, **`banga/general` (Gemma) réussit le
même test 1/1** : vrai tool_call `bash` avec sortie réelle (`1784832449`) puis réponse
correcte. Donc : le patch autoparser llama.cpp + temp=0 (validé "3/3" dans le handoff
`banga/.planning/handoffs/2026-07-23-llama-cpp-qwen-tool-calling.md`) a été validé sur un
harnais de test différent (probablement API completions brute avec un prompt custom
démontrant le format de tag) — **pas représentatif du format réel que le pipeline agent
OpenCode envoie** (schéma `tools` standard OpenAI, encodé via le template de chat Qwen).
Le patch autoparser ne suffit visiblement pas à couvrir ce chemin réel.

**Ceci ré-ouvre potentiellement le chantier tool-calling côté `banga`** (pas seulement
température) — décision à prendre avec l'opérateur : creuser le format exact envoyé par
OpenCode (tools JSON schema + template Qwen) vs ce que l'autoparser patché reconnaît, ou
accepter que Qwen2.5-Coder via OpenCode reste dégradé et reconsidérer le swap de modèle
écarté précédemment (Granite 4.1 8B). Ne PAS relancer la recherche comparative de modèles
sans en discuter — c'était une décision actée, mais la prémisse ("temp=0 suffit") vient
d'être invalidée empiriquement sur le pipeline réel.

Sessions de test toutes nettoyées (`DELETE /session/{id}`), aucune boucle active restante
au moment de la rédaction.

## MISE À JOUR 2 2026-07-23 (même session) — debug format tools, root cause complète

Fix température **commité** (`817e507`).

**Root cause de la boucle infinie + de l'écart avec le "3/3" banga, en 2 couches
distinctes maintenant élucidées** :

1. **Contexte trop petit — RÉSOLU côté VPAI** : le vrai system prompt qu'OpenCode envoie
   (agent `build`) pèse 38 743 caractères / ~15 443 tokens, dont **74% est du bruit sans
   rapport avec Banga** : `~/.claude/CLAUDE.md` global (8 879 car., doctrine de routage
   Claude-specifique) + catalogue complet des skills Claude Code (19 783 car., 51% à lui
   seul). `banga/coder` (14B, contexte serveur 12288) rejette donc la requête réelle
   d'entrée (`400 exceed_context_size_error`) — c'est ce qui causait la boucle infinie de
   compaction déjà notée dans la mise à jour précédente. **Fix déployé** (commit à suivre) :
   `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT=1` + `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` sur
   le service systemd + le shell interactif (`roles/opencode/templates/opencode.service.j2`,
   `roles/opencode/tasks/main.yml`). Vérifié empiriquement (CLI direct + proxy de capture
   locale) : system prompt tombe à 13 671 caractères, la requête rentre enfin dans les
   12288 tokens de `coder`. **Compromis assumé** (décision opérateur) : ces variables sont
   globales au process OpenCode, donc coupent aussi skills/CLAUDE.md pour un usage
   Claude Sonnet via LiteLLM dans le même OpenCode — accepté car Sonnet ne sera pas
   utilisé via OpenCode sur ce host.

2. **Format de tool-call non reconnu — PAS RÉSOLU, root cause différente de ce qui était
   cru** : une fois le problème de contexte réglé, `banga/coder` (14B) **retombe
   exactement dans le même échec que `coder_longctx` (7B)** : avec les **10 vrais outils
   OpenCode** (`bash`, `edit`, `glob`, `grep`, `read`, `skill`, `task`, `todowrite`,
   `webfetch`, `write` — descriptions verbeuses, ex. `bash` ~2000 caractères), le modèle
   émet de façon déterministe un bloc `` ```json\n{"name": "bash", "arguments": {...}}\n``` ``
   au lieu du tag `<tool_call>` que le patch attend — `finish_reason: "stop"`, jamais
   `"tool_calls"`. **Le "3/3 déterministe" du handoff banga ne tenait que pour un test à
   1 seul outil trivial (`list_files`)** — confirmé en reproduisant EXACTEMENT ce cas
   minimal (3/3 `tool_calls` structuré parfait sur `coder` 14B) puis en gonflant
   progressivement vers les 10 vrais outils (bascule déterministe vers le mauvais
   format, peu importe modèle 14B ou 7B, peu importe la taille du system prompt une fois
   les 10 outils présents). Donc : **le patch autoparser fonctionne, mais ne généralise
   pas à un agent de code réel avec un jeu d'outils complet** — ni `coder` ni
   `coder_longctx` n'est utilisable de façon fiable aujourd'hui pour du tool-calling réel
   via OpenCode. Confirmé aussi sur le service systemd réel (pas seulement CLI/proxy) :
   `banga/coder` boucle encore après le fix contexte (boucle différente — "anchored
   summary", pas `exceed_context_size_error` cette fois — signe que le modèle répond bien
   mais dans un format qu'OpenCode ne reconnaît pas comme final).

**Méthode de repro utile pour la suite (banga)** : proxy de capture local
(`http.server` + `urllib`, ~60 lignes, voir historique de session) intercalé entre
OpenCode et llama-swap via `provider.banga.options.baseURL` temporairement repointé vers
`127.0.0.1:<port>` — capture la requête EXACTE (tools réels, system prompt réel) sans
toucher à banga, puis rejeu direct en curl contre `100.64.0.32:8080` pour isoler
totalement le comportement serveur du client OpenCode. Permet de faire varier
indépendamment : nombre d'outils, taille du system prompt, modèle (`coder`/`coder_longctx`),
sans jamais passer par le pipeline OpenCode complet (donc sans risque de re-déclencher la
boucle infinie sur le service de prod).

**Prochaine étape (chantier banga, pas VPAI)** : étendre le patch autoparser pour
reconnaître aussi le format `` ```json\n{"name":...,"arguments":...}\n `` (4ᵉ variante,
après `<tool_call>`, `<tools>`, `<function-call>` déjà rencontrés) — ou explorer un
fallback côté client OpenCode (plugin qui parse ce pattern en texte libre et invoque
l'outil manuellement, si un hook de post-traitement de message existe). Décision
opérateur en attente sur lequel des deux chemins prendre.

**Chantier séparé capturé en seed** (pas ce chantier) : réécrire les skills/workflows
Claude Code (`~/.claude/skills/`) en une version allégée/dédiée destinée à OpenCode —
motivé par la découverte que le catalogue skills complet (19 783 car.) est injecté tel
quel et verbeux. Voir `.planning/seeds/2026-07-23-reecriture-skills-workflows-opencode.md`.

---


## Objectif

Faire en sorte que les requêtes OpenCode (Waza) vers les modèles Banga (`coder`,
`coder_longctx`, possiblement `general`) utilisent une température basse (idéalement 0)
quand des `tools` sont présents dans la requête — condition déjà validée empiriquement
comme réglant la fiabilité du tool-calling (3/3 à temp 0 vs 4/5 à temp par défaut 0.8).

## Décisions prises (ne pas re-discuter)

- **Le bug de tool-calling lui-même est déjà root-causé ET patché** — pas l'objet de ce
  chantier. Détail complet : `/home/mobuone/work/infra/banga/.planning/handoffs/2026-07-23-llama-cpp-qwen-tool-calling.md`
  (section "RÉSOLU", en tête de fichier). Patch = 3 points dans l'autoparser llama.cpp,
  commité dans `banga/roles/lxc-infer/files/llama-cpp-qwen-tool-call-alt-tag.patch`,
  appliqué via `llama-build.sh.j2`. Validé : `temperature: 0` → 3/3 tool_calls structurés
  déterministes ; `temperature` défaut (0.8) → 4/5, le modèle hallucine parfois un 3ᵉ tag
  (`<function-calls>`, `<response>`) hors de la liste finie d'alt-tags gérés par le patch.
- **Approche choisie : réglage température AVANT swap de modèle.** Une recherche
  comparative a été faite sur des alternatives (Qwen3-Coder-Next écarté — 80B MoE, ne
  rentre pas en VRAM sur ce rig car le full-offload GPU obligatoire (pas d'AVX CPU) impose
  que TOUS les experts MoE résident en VRAM, aucun bénéfice du MoE ici ; Granite 4.1 8B
  identifié comme meilleur candidat de repli si le réglage température échoue, mais jamais
  testé sur ce rig — voir conversation d'origine si besoin de reconstituer le comparatif
  complet, non écrit sur disque). **Ne pas relancer cette recherche comparative** sauf si
  le réglage température s'avère infaisable ou insuffisant.
- **Recherche initiale (session d'origine, incomplète)** : `https://opencode.ai/docs/config/`
  **ne documente PAS de champ `temperature`** dans le schéma `opencode.json` (vérifié via
  WebFetch, 2026-07-23). Ce n'est pas une impasse confirmée — juste que la doc publique
  n'en parle pas. À creuser plus loin (voir Prochaine étape).
- `opencode.json.j2` a déjà un provider `banga` direct fonctionnel (commit VPAI `7b22776`,
  déployé sur Waza) — modèles `general`/`coder`/`coder_longctx`, LAN direct (100.64.0.32:8080),
  aucune authentification requise côté llama-swap. C'est LA base à modifier, pas à
  reconstruire.

## Chemins / artefacts

- Config à modifier (probable) : `/home/mobuone/work/infra/VPAI/roles/opencode/templates/opencode.json.j2`
  — voir la structure actuelle du provider `banga` (bloc `models.coder`/`coder_longctx`/`general`,
  chacun avec `id`, `tool_call`, `attachment`, `limit.context`/`limit.output`).
- Doc publique déjà vérifiée insuffisante : `https://opencode.ai/docs/config/` (pas de champ
  `temperature` documenté). Schéma JSON formel jamais vérifié : `https://opencode.ai/config.json`
  — à fetch en premier.
- Source du projet OpenCode : incertitude sur l'org GitHub exacte — une recherche antérieure
  dans cette session a trouvé une issue sur `anomalyco/opencode` (pas `sst/opencode` comme
  attendu a priori) — vérifier laquelle est la bonne avant de chercher dans le code source.
- Alternative serveur-side à explorer (si le client OpenCode ne permet pas de fixer la
  température par modèle) : `llama-server`/`llama-swap` peuvent probablement imposer un
  `--temp` par défaut CÔTÉ SERVEUR pour un modèle donné, indépendamment de ce que le client
  envoie (à vérifier : `llama-server --help` a un flag `--temp` — reste à confirmer s'il agit
  comme un DÉFAUT que le client peut écraser, ou une VALEUR IMPOSÉE qui ignore le `temperature`
  envoyé par le client). Fichier à modifier si cette voie est retenue :
  `/home/mobuone/work/infra/banga/roles/lxc-infer/templates/llama-swap.yaml.j2` (bloc `cmd:`
  par modèle, même endroit où `--jinja` a été ajouté plus tôt dans la session d'origine).
  ⚠️ Si cette voie est choisie, ça affecte TOUS les appelants de Banga (pas seulement
  OpenCode) — LiteLLM (Sese) route aussi vers les mêmes endpoints (`banga-general`/
  `banga-coder`/`banga-coder-longctx` dans `VPAI/roles/litellm/templates/litellm_config.yaml.j2`)
  — vérifier que ça ne casse rien côté LiteLLM avant de déployer server-side.
- Méthode de validation déjà établie (à réutiliser, ne pas réinventer) : un prompt
  imprévisible type "Run the shell command `date +%s` and tell me exactly what number it
  prints" via l'API OpenCode réelle (`POST /session` puis `POST /session/{id}/message` avec
  `{"model":{"providerID":"banga","modelID":"<coder|coder_longctx|general>"},"parts":[...]}`
  sur `http://127.0.0.1:3456`), en vérifiant que la réponse contient le VRAI timestamp Unix
  courant (preuve d'exécution réelle d'outil) et non un texte hallucinatoire. Piège déjà
  rencontré dans la session d'origine : le premier appel à `coder` après un changement de
  config met du temps à charger en VRAM (~20-60s, TTL de déchargement 300s) — utiliser un
  `--max-time` généreux (90-150s) sur les tests curl, sinon on confond "encore en train de
  charger" avec "cassé".

## Prochaine étape

1. Fetch `https://opencode.ai/config.json` (schéma JSON formel) pour voir si un champ
   `temperature`/`options.temperature`/`variant` existe malgré l'absence dans la doc prose.
2. Si rien côté client OpenCode : vérifier `llama-server --help` (déjà disponible localement,
   `ssh -i ~/.ssh/id_ed25519 root@100.64.0.32` puis `pct exec 201 -- /opt/llama.cpp/build/bin/llama-server --help`)
   pour un flag de température par défaut serveur, et si un tel flag peut être surchargé
   par le client (vérifier avec un test réel : lancer avec `--temp 0` côté serveur, puis
   envoyer une requête EXPLICITEMENT avec `"temperature": 0.8` côté client, voir laquelle
   des deux valeurs gagne).
3. Implémenter la voie retenue (client `opencode.json.j2` de préférence si possible — plus
   ciblé, n'affecte pas les autres consommateurs de Banga).
4. Redéployer (Waza : `ansible-playbook playbooks/hosts/workstation.yml --tags opencode --diff`
   ou Banga : `ansible-playbook playbooks/site.yml --tags lxc-infer --diff` selon la voie),
   puis valider avec la méthode de preuve ci-dessus sur `coder` ET `coder_longctx` (les 2
   modèles concernés par le bug — `general`/Gemma était déjà fonctionnel sans ce réglage,
   revalider quand même par prudence qu'on ne régresse rien).

## Gates humains

- Si la voie serveur-side (`llama-swap.yaml.j2`) est retenue : confirmer avec l'opérateur
  avant déploiement, car ça affecte LiteLLM/Sese aussi, pas seulement OpenCode/Waza.
- Rebuild/redémarrage de service sur Banga (LXC 201) : ne pas lancer en pleine charge
  d'inférence (même consigne que pour le patch autoparser, cf CLAUDE.md du repo banga).
