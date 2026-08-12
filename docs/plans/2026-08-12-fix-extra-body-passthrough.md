# Plan de déploiement — fix extra_body passthrough (finding CRITIQUE (c) gate Optimus B4)

Statut : PRÉPARÉ, NON DÉPLOYÉ. Branche `chantier/fix-extra-body-passthrough`
(VPAI, base = `main` @ `fa66b19`). Commit(s) listés en fin de document.
Le deploy lui-même est un geste opérateur (ack high-risk requis, même
discipline que le gate technique B4.3 du 2026-08-11 et le deploy campagne 3
du 2026-08-12).

Source du finding : `docs/ops/gates-journal.md` ligne « 2026-08-12
après-midi » (gate TECHNIQUE §4 post-deploy campagne 3, arbitré en
autonomie, mandat) — extrait : « **(c) FAIL CRITIQUE** : le champ client
`extra_body.provider` ÉCRASE le pin serveur — démontré glm-52→Sail
Research et claude-opus→Anthropic direct (ABSENT de la liste ZDR) ; le
vecteur top-level testé au gate B4.3 est neutralisé par drop_params (faux
sentiment de sécurité) → faille PRÉ-EXISTANTE valant aussi pour
eco-1/eco-2. […] chantier fix extra_body gateway OUVERT priorité HAUTE
(bloquant avant toute exposition de clé à un client non-nôtre, notamment
C1 clés tenant) ».

## 1. Mécanisme retenu — aucun réglage LiteLLM natif ne bloque un sous-champ d'`extra_body`

Recherche menée contre la doc officielle LiteLLM (docs.litellm.ai/docs/
completion/input, docs.litellm.ai/docs/completion/drop_params) et vérifiée
sur le code source réel de la version PINNÉE production
(`inventory/group_vars/all/versions.yml: litellm_image: v1.83.3-stable`,
wheel `litellm==1.83.3` téléchargé et inspecté) :

- **`drop_params: true`** (déjà actif) ne filtre QUE les paramètres OpenAI
  standards non supportés par le modèle cible. Tout kwarg non-OpenAI (donc
  `extra_body` et tout son contenu, y compris `extra_body.provider`) est
  documenté comme « provider specific » et transmis tel quel. C'est ce qui
  neutralise le vecteur top-level `"provider": {...}` (rejeté comme param
  OpenAI non supporté) mais **ne touche pas** au vecteur
  `extra_body.provider` (déjà à l'intérieur d'un kwarg non-OpenAI, jamais
  inspecté par ce mécanisme).
- **`allowed_openai_params`** est un ÉLARGISSEUR d'allowlist (permet des
  params OpenAI normalement rejetés), pas un filtre. Il est de surcroît
  lui-même surchargeable par le client via son propre `extra_body` — c'est
  une extension de surface d'attaque, pas un garde-fou.
- Aucun autre réglage global (`litellm_settings`, `router_settings`,
  `general_settings`) ne filtre un sous-champ arbitraire d'un dict
  `extra_body` reçu du client.
- Cause racine du contournement, vérifiée dans le code : le merge
  `extra_body` serveur/client est un **merge shallow** au niveau de la clé
  complète `extra_body` (`litellm/utils.py::get_optional_params`, ~L4372 :
  `initial_extra_body = {**optional_params["extra_body"], **extra_body}`
  où `extra_body` de droite = kwargs client). Le dict `"provider"` fourni
  par le client REMPLACE intégralement celui du serveur (pas de deep-merge
  sur les clés imbriquées).

**Seul mécanisme natif exploitable** : un callback custom
`CustomLogger.async_pre_call_hook`, invoqué par
`ProxyLogging.pre_call_hook()` — vérifié sur `litellm==1.83.3` (le wheel
pinné) que :
1. `proxy/common_request_processing.py::common_processing_pre_call_logic()`
   appelle `self.data = await proxy_logging_obj.pre_call_hook(...)` **avant**
   toute sélection de deployment / merge des `litellm_params` serveur par
   le Router — sur TOUTES les routes qui passent par
   `base_process_llm_request()`, y compris `/v1/chat/completions` ET
   `/v1/messages` (format Anthropic natif, `proxy/anthropic_endpoints/
   endpoints.py::anthropic_response()` appelle le même
   `base_process_llm_request`).
2. `proxy/utils.py::ProxyLogging.pre_call_hook()` boucle sur
   `litellm.callbacks` et invoque `async_pre_call_hook` sur toute instance
   `CustomLogger` dont la classe surcharge cette méthode — exactement notre
   cas.
3. `proxy/types_utils/utils.py::get_instance_fn()` résout un identifiant
   `"module.instance"` déclaré sous `litellm_settings.callbacks` du
   config.yaml **relatif au répertoire du fichier config.yaml chargé**
   (`os.path.dirname(config_file_path)`) — donc le fichier callback doit
   être monté dans le MÊME répertoire conteneur que `/app/config.yaml`.

Ces trois points ont été vérifiés end-to-end sur un venv Python isolé avec
`litellm[proxy]==1.83.3` réellement installé (pas seulement lu dans le
source) :
- `ExtraBodyProviderGuard` hérite bien de `CustomLogger`, la condition de
  détection de `proxy/utils.py` (`"async_pre_call_hook" in vars(cls)` +
  `cls.async_pre_call_hook != CustomLogger.async_pre_call_hook`) est vraie.
- `get_instance_fn("guard_extra_body.proxy_handler_instance",
  config_file_path=".../config.yaml")` résout correctement l'instance
  depuis un fichier `guard_extra_body.py` posé à côté d'un `config.yaml`
  factice (mime le layout `/app/`).
- **Piège identifié en revue et corrigé** : `litellm_settings.callbacks`
  DOIT être une liste YAML (`- guard_extra_body.proxy_handler_instance`),
  jamais un scalaire nu. `initialize_callbacks_on_proxy()`
  (`proxy/common_utils/callback_utils.py`) a DEUX branches selon le type
  Python de `value` : `isinstance(value, list)` → additif
  (`litellm.callbacks.extend(imported_list)`) ; sinon → **assignation**
  (`litellm.callbacks = [get_instance_fn(...)]`), qui écraserait tout
  callback déjà enregistré par une clé `litellm_settings` précédente.
  Vérifié avec `litellm[proxy]==1.83.3` installé : un callback sentinelle
  pré-existant dans `litellm.callbacks` survit à l'appel avec notre config
  en liste (`.extend`, additif confirmé) — voir `roles/litellm/templates/
  litellm_config.yaml.j2` pour la forme retenue.
- **Preuve end-to-end la plus forte obtenue** : appel direct de
  `ProxyLogging.pre_call_hook()` (le VRAI point d'entrée invoqué par
  `proxy_server.py`, pas une simulation de son comportement) après
  enregistrement du callback via `initialize_callbacks_on_proxy()` — un
  payload contenant `extra_body.provider` malveillant ressort avec
  `extra_body: {}` (clé retirée), sans toucher au reste du payload.

## 2. Implémentation

- `roles/litellm/files/guard_extra_body.py` (nouveau) — callback
  `CustomLogger` custom. `_strip_forbidden_provider(data)` : fonction pure
  testable hors LiteLLM (import de `CustomLogger` en best-effort avec
  fallback `object`), retire `data["provider"]` (top-level, défense en
  profondeur vs `drop_params`) et `data["extra_body"]["provider"]`
  (le vecteur CRITIQUE), gère `extra_body` fourni en JSON string. Logging
  `logger.warning` à chaque strip (observabilité, sans exposer de secret).
- `roles/litellm/templates/litellm_config.yaml.j2` — ajout de
  `litellm_settings.callbacks` en **LISTE YAML** (`- guard_extra_body.proxy_handler_instance`,
  template l.517-518) — jamais en scalaire (cf. §1 : un scalaire fait
  écraser `litellm.callbacks` par `initialize_callbacks_on_proxy`).
- `roles/litellm/tasks/main.yml` — nouvelle tâche `ansible.builtin.copy`
  (fichier statique, PAS un template Jinja) déployant
  `guard_extra_body.py` vers `{{ litellm_config_dir }}/guard_extra_body.py`,
  `notify: Restart litellm stack`.
- `roles/docker-stack/templates/compose/apps-core.yml.j2` — nouveau bind
  mount `ro` du fichier callback vers `/app/guard_extra_body.py` (même
  répertoire que `/app/config.yaml`, requis par `get_instance_fn`).
- `roles/litellm/files/test-extra-body-guard.sh` — script de preuve
  post-deploy (§4).

**Dépendance de rôles pour le deploy** : le fix touche DEUX rôles
(`litellm` pour le config+callback, `docker-stack` pour le mount compose).
Un deploy scopé `--tags litellm` seul déposerait le fichier `.py` dans
`{{ litellm_config_dir }}` mais SANS le monter dans le conteneur → callback
jamais chargé, garde-fou silencieusement inopérant. **Le tag `docker-stack`
(ou l'absence de tags, run complet) est OBLIGATOIRE dans cette campagne.**

Validations exécutées (aucune n'a nécessité de proxy vivant) :
- `ansible-lint roles/litellm roles/docker-stack` → **0 failure(s), 0
  warning(s)**, profil `production`.
- Rendu Jinja + `yaml.safe_load()` de `litellm_config.yaml.j2` (contexte
  reconstruit depuis `roles/litellm/defaults/main.yml`) → YAML valide,
  `litellm_settings.callbacks` est une **liste** contenant
  `"guard_extra_body.proxy_handler_instance"`
  (`isinstance(cb, list) and "guard_extra_body.proxy_handler_instance" in cb`).
- Rendu Jinja + `yaml.safe_load()` du fragment `apps-core.yml.j2` (contexte
  reconstruit depuis `roles/docker-stack/molecule/default/converge.yml` +
  `inventory/group_vars/all/*.yml`) → YAML valide, volume
  `.../guard_extra_body.py:/app/guard_extra_body.py:ro` présent dans le
  service `litellm`.
- `bash -n` + `shellcheck` propres sur `test-extra-body-guard.sh` (0
  finding après correction d'un bug d'apostrophe dans un message
  `${VAR:?...}` — les apostrophes dans le mot d'un `${VAR:?word}` restent
  quote-significatives même à l'intérieur de guillemets doubles englobants,
  gotcha bash classique — et après revue, retrait d'un fallback jq
  (`._hidden_params.custom_llm_provider`) qui aurait pu produire un FAUX
  FAIL : ce champ porte le provider LiteLLM (`"openrouter"`), jamais le
  fournisseur upstream pinné (`"google-vertex"`) — une valeur non-vide
  mais fausse est pire qu'une absence, le script ne garde donc QUE
  `.provider`.
- Preuve offline du callback : `python3 -c "import guard_extra_body; ..."`
  SANS litellm installé (fonction pure) puis AVEC `litellm[proxy]==1.83.3`
  installé dans un venv isolé — les deux passent. Preuve la plus forte :
  appel direct de `ProxyLogging.pre_call_hook()` (le vrai point d'entrée
  proxy, après enregistrement du callback via
  `initialize_callbacks_on_proxy()` avec la config EXACTE du template en
  forme liste) sur un payload `extra_body.provider` malveillant — la clé
  ressort strippée. Script `test-extra-body-guard.sh` exercé en mode mock
  (curl stubé) sur ses 3 chemins : PASS (pin tenu), FAIL (contournement
  détecté), FAIL (attestation absente — pas un pass silencieux).

Molecule NON exécuté (binaire absent de l'environnement d'exécution,
sandbox offline) — à lancer par l'opérateur ou en CI avant merge si le
gate l'exige : `cd roles/litellm && molecule test` /
`cd roles/docker-stack && molecule test`.

## 3. Séquence de déploiement (geste opérateur)

Mêmes précautions que le deploy campagne 3 (`docs/plans/
2026-08-12-deploy-campagne3-aliases.md`) : override `prod_ip` obligatoire
(inventaire résout l'IP publique, hors VPN), ack opérateur explicite avant
tout `ansible-playbook` réel, rollback épinglé sur le commit courant de
`main`.

**Étape 1 — dry-run** :
```bash
git log --oneline -1 main   # noter le sha ÉPINGLÉ pour le rollback
git checkout chantier/fix-extra-body-passthrough
ansible-playbook playbooks/stacks/site.yml \
  -e prod_ip=100.64.0.14 \
  --diff \
  --check
# PAS de --tags litellm seul (cf. §2, dépendance docker-stack) — run
# complet ou --tags litellm,docker-stack si le playbook le permet.
```

**Étape 2 — ACK OPÉRATEUR EXPLICITE** : point d'arrêt obligatoire. Lire le
diff du dry-run en entier (attendu : config litellm + fichier callback +
compose apps-core, rien d'autre). L'étape 3 ne se lance qu'après cet ack
(`touch /tmp/claude-highrisk-ack` si le garde le demande) — jamais
enchaînée.

**Étape 3 — deploy réel** :
```bash
ansible-playbook playbooks/stacks/site.yml \
  -e prod_ip=100.64.0.14 \
  --diff
```

**Rollback** (critère : protocole §4 rouge, ou 502 persistant > 10 min, ou
tout alias existant qui cesse de répondre) :
```bash
git checkout <sha-main-épinglé-noté-ci-dessus>
ansible-playbook playbooks/stacks/site.yml -e prod_ip=100.64.0.14 --diff
# après stabilisation : git checkout chantier/fix-extra-body-passthrough (ou main)
```

## 4. Protocole de preuve post-deploy

À exécuter immédiatement après le deploy, résultat à journaliser dans
`docs/ops/gates-journal.md` (nouvelle ligne, même format que l'entrée
2026-08-12 après-midi) :

**(a) Fichier callback effectivement monté dans le conteneur** (pas
seulement rendu localement) :
```bash
docker exec <container_litellm> test -f /app/guard_extra_body.py && echo "MOUNT OK"
docker exec <container_litellm> ls -la /app/ | grep guard_extra_body
```

**(b) Callback enregistré au démarrage** — grep du log de boot du conteneur
pour confirmer que LiteLLM a bien résolu et chargé
`guard_extra_body.proxy_handler_instance` (pas d'exception d'import) :
```bash
docker logs <container_litellm> 2>&1 | grep -i "guard_extra_body\|Initialized Callbacks" | tail -20
```
Si le log ne confirme rien explicitement, envoyer une requête de contrôle
avec un vecteur `extra_body.provider` et vérifier la ligne
`logger.warning` émise par le callback (`guard_extra_body: stripped
client-supplied provider override(s) [...]`) dans les logs applicatifs —
c'est la preuve la plus directe que le callback tourne réellement.

**(c) Test de contournement, 2 vecteurs** — exécuter le script de preuve
pour CHAQUE alias pinné (au minimum `claude-opus`, `eco-1`, `eco-2` —
tous cités dans le finding) :
```bash
export LITELLM_MASTER_KEY="$(vault-read-litellm-master-key)"  # jamais en clair
./roles/litellm/files/test-extra-body-guard.sh \
  -b https://llm.ewutelo.cloud -m claude-opus -p google-vertex -a openai
./roles/litellm/files/test-extra-body-guard.sh \
  -b https://llm.ewutelo.cloud -m eco-1 -p <provider-pinné-eco-1> -a openai
./roles/litellm/files/test-extra-body-guard.sh \
  -b https://llm.ewutelo.cloud -m eco-2 -p <provider-pinné-eco-2> -a openai
# NE PAS unset ici — le test de régression (d) réutilise la clé ;
# `unset LITELLM_MASTER_KEY` se fait APRÈS (d), en fin de protocole.
```
Attendu : `RESULTAT: PASS` (exit 0) sur les 3 — les 2 vecteurs (top-level
ET `extra_body.provider`) échouent à faire dévier le fournisseur attesté
du pin serveur. Une absence d'attestation dans la réponse est un ÉCHEC de
preuve (le script traite ce cas comme FAIL, jamais comme un pass
silencieux) : dans ce cas, identifier manuellement le champ d'attestation
réellement exposé par la version déployée avant de conclure.

**(d) Régression — comportement nominal inchangé** : un appel SANS
override client sur `claude-opus` doit toujours résoudre `google-vertex`
(le fix ne doit pas casser le pin légitime pour un client honnête) :
```bash
curl -sS -X POST https://llm.ewutelo.cloud/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-opus","max_tokens":1,"messages":[{"role":"user","content":"1"}]}'
```

**(e) No-op ailleurs** — la task `Deploy LiteLLM environment file` doit
rester inchangée (aucune clé nouvelle sur ce chantier) ; seules les tasks
`Deploy LiteLLM config`, `Deploy LiteLLM extra_body provider-pin guard
callback` et le recreate du service `litellm` (docker-stack) doivent
apparaître `changed`.

Si (c) ou (d) échoue : rollback immédiat (§3), pas de tentative de fix en
place sur la branche prod.

## 5. Limites connues / résidu assumé

- Le garde-fou ne couvre QUE la clé `provider` (top-level et
  `extra_body`) — c'est le vecteur exact démontré au gate. D'autres clés
  `extra_body` (ex. `transforms`, `route`, `models`) restent passthrough
  intégral côté client, conformément au comportement documenté et voulu de
  LiteLLM pour ces usages OpenRouter légitimes (non couvertes par cette
  correction, hors périmètre instruit).
- Aucun test automatisé (molecule) exécuté dans cette session — offline,
  binaire absent. Recommandé avant merge définitif si la politique du
  dépôt l'exige pour ce type de changement.
- Le mécanisme dépend de la version de LiteLLM pinnée
  (`v1.83.3-stable`). Un bump de version doit être accompagné d'une
  re-vérification des 3 anchors du §1 (le comportement d'un callback custom
  n'est pas dans le contrat d'API stable documenté de LiteLLM — code
  interne, peut changer sans annonce dans un changelog public).
