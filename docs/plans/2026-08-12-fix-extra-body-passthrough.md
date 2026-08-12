# Plan de déploiement — fix extra_body passthrough (finding CRITIQUE (c) gate Optimus B4)

Statut initial de ce document (2026-08-12) : PRÉPARÉ, NON DÉPLOYÉ. La v1 du
fix (delete-only, commit `990d129`) a depuis été déployée en prod par
l'opérateur (branche fusionnée avec campagne3-aliases, commit `456fc34`).
**INCIDENT POST-DEPLOI 2026-08-13, corrigé dans ce document/cette branche
— voir §6 ci-dessous avant tout nouveau déploiement.**

Le deploy lui-même reste un geste opérateur (ack high-risk requis, même
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
git log --oneline -1 chantier/fix-extra-body-passthrough
# ÉPINGLAGE : vérifier que ce sha == celui annoncé dans la notification
# d'ack (source de vérité au moment du feu vert) — une branche est mutable,
# on déploie un SHA vérifié, pas un nom de branche.
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
trap 'unset LITELLM_MASTER_KEY' EXIT   # garantit l'unset même sur échec/exit 1
resp=$(curl -sS --fail-with-body -X POST https://llm.ewutelo.cloud/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-opus","max_tokens":1,"messages":[{"role":"user","content":"1"}]}') \
  || { echo "FAIL (d): HTTP en erreur"; exit 1; }
prov=$(echo "$resp" | jq -r '.provider // .model_extra.provider // empty')
[ "$prov" = "Google" ] || [ "$prov" = "google-vertex" ] \
  || { echo "FAIL (d): provider attesté='$prov' ≠ google-vertex"; exit 1; }
echo "PASS (d): provider=$prov"
```

**(e) No-op ailleurs** — la task `Deploy LiteLLM environment file` doit
rester inchangée (aucune clé nouvelle sur ce chantier) ; seules les tasks
`Deploy LiteLLM config`, `Deploy LiteLLM extra_body provider-pin guard
callback` et le recreate du service `litellm` (docker-stack) doivent
apparaître `changed`.

**Contrôles OBLIGATOIRES : (a), (b), (c), (d), (e) — TOUS.** Si N'IMPORTE
LEQUEL échoue — y compris (a) fichier non monté ou (b) callback non chargé
(un garde silencieusement inerte est PIRE qu'absent : fausse assurance) —
: rollback immédiat (§3), pas de tentative de fix en place sur la branche
prod. Cohérent avec le critère général §3 « protocole §4 rouge → rollback ».

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
- **(ajouté §6, post-incident)** Le pin serveur n'est réécrit QUE si le
  client envoie une clé `extra_body` (override ou non). Un appel
  strictement nominal (aucun `extra_body` client) reste protégé par le
  comportement natif du merge Router (`litellm_params` jamais concurrencé)
  — pas de résidu là. En revanche, `claude-opus` (seul alias pinné présent
  dans la map `fallbacks:`) reste vulnérable à un empoisonnement de son
  fallback (`claude-sonnet`) SI le client a envoyé un `extra_body` sur
  l'appel primaire ET que ce dernier échoue et bascule en fallback — le
  pin injecté pour `claude-opus` (google-vertex, `allow_fallbacks:false`)
  rides dans la tentative `claude-sonnet` via le même dict `kwargs`
  réutilisé. Non résolu dans ce correctif (périmètre restreint au finding
  gate + incident 2026-08-13, tous deux définis par la présence d'un
  `extra_body` client) ; option de fix future : retirer `claude-opus` de
  la map `fallbacks:` (déjà discuté comme option (b) au plan campagne 3,
  non tranchée) ou faire filtrer/nettoyer `extra_body` du côté
  fallback-retry lui-même (nécessiterait un hook différent, pas
  `pre_call_hook` qui ne revoit pas les tentatives de fallback).

## 6. Incident post-déploiement 2026-08-13 — correction (delete → enforce)

**Constat opérateur** (résumé) : garde active en prod, log de strip visible
(`stripped client-supplied provider override(s) ['extra_body.provider']`),
mais preuve empirique que le pin serveur est quand même cassé sur le
chemin overridé : appel `glm-52` AVEC `extra_body.provider` client →
fournisseur attesté **CoreWeave** (ni l'override `openai`, ni le pin
serveur `digitalocean`) ; appel `glm-52` NOMINAL (sans `extra_body`) →
`DigitalOcean` (pin OK) ; config effective vérifiée correcte
(`extra_body.provider.order=[digitalocean]`, `allow_fallbacks: false`).

**Cause racine confirmée dans le code du wheel PINNÉ `litellm==1.83.3`**
(téléchargé et inspecté directement, pas seulement lu en doc) —
`router.py::Router._acompletion()`, ~L2140-2148 :
```python
input_kwargs = {
    **litellm_params,   # SERVEUR (deployment litellm_params, config.yaml)
    "messages": messages,
    "caching": self.cache_responses,
    "client": model_client,
    **kwargs,            # CLIENT (request data) — spread EN DERNIER, GAGNE
}
```
Ce merge est **shallow au niveau des clés de premier niveau** de
`input_kwargs`. La v1 du guard (commit `990d129`) supprimait uniquement la
sous-clé `data["extra_body"]["provider"]`, laissant `data["extra_body"]`
présent **comme clé** (même vide `{}`). Dès qu'une requête client contient
une clé `extra_body` — avec OU SANS tentative d'override `provider`
explicite — cette clé écrase **intégralement**
`litellm_params["extra_body"]` (le pin serveur complet) à ce merge, AVANT
même que la logique de merge plus fine documentée dans
`litellm/utils.py::get_optional_params()` (le merge shallow
`{**server_extra_body, **client_extra_body}` sur lequel reposait
l'analyse initiale du finding gate) n'ait la moindre chance de s'exécuter
— ce merge plus fin ne voit jamais qu'**une seule** source `extra_body` à
ce stade, celle qui a déjà survécu au merge Router `_acompletion`
ci-dessus. Résultat : `extra_body` vide → OpenRouter reçoit zéro
préférence de fournisseur → routage libre (CoreWeave dans l'incident).

**Note historique demandée** : l'attestation Google observée juste après
le tout premier déploiement (avant même le fix v1) n'était **pas une
coïncidence de routage** — c'était un chemin différent. Ce test portait
sur un appel `claude-opus` **sans aucune clé `extra_body`** dans le corps
client. Le merge Router `{**litellm_params, **kwargs}` ne voit alors
aucune clé `extra_body` côté `kwargs` : `litellm_params["extra_body"]`
(serveur) n'est jamais concurrencé et survit intact — d'où l'attestation
correcte. Ce mécanisme (« absence de clé = pin protégé ») est réel mais
**fragile** : n'importe quel client envoyant un `extra_body` vide pour
toute autre raison légitime aurait rompu le pin quand même, sans même
tenter un override. C'est exactement le trou exploité par l'incident
2026-08-13.

**Correction** (`roles/litellm/files/guard_extra_body.py`, remplace le
comportement « delete » par « enforce conditionnel ») : au lieu de
supprimer `data["extra_body"]["provider"]`, le callback le **réécrit**
avec le pin serveur exact du modèle appelé, lu depuis
`litellm.proxy.proxy_server.llm_router` (le `Router` global du proxy,
peuplé au chargement de la config — même pattern de lazy-import que
`litellm/proxy/hooks/batch_rate_limiter.py`). `Router.get_model_list(
model_name=...)` retourne les deployments correspondant à l'alias avec
leur `litellm_params` intact (vérifié empiriquement avec
`litellm[proxy]==1.83.3` réellement installé : le dict `extra_body.
provider` survit tel quel à l'enregistrement du Router). Comportement par
cas :
- Client envoie un override explicite (`extra_body.provider` présent) →
  réécrit avec le pin serveur.
- Client envoie un `extra_body` SANS `provider` (le trou de l'incident,
  y compris vide `{}` ou avec un sous-champ légitime type `transforms`) →
  la sous-clé `provider` est **ajoutée** dans le MÊME dict que celui qui
  sera spread au merge Router, forçant le pin quel que soit le résultat du
  merge shallow top-level ; les autres sous-clés légitimes du client
  (`transforms`, etc.) sont préservées.
- **Aucun `extra_body` client du tout (nominal) → NON touché, délibérément
  (revu et corrigé après une 1re tentative qui injectait inconditionnellement).**
  Une 1re version de ce fix (abandonnée en cours de revue, jamais
  déployée) injectait le pin même sur les appels nominaux. Ceci a été
  identifié comme un **empoisonnement du filet de secours** : `data`
  (le dict post `pre_call_hook`) est le MÊME objet `kwargs` réutilisé tel
  quel par `Router.async_function_with_fallbacks_common_utils()` pour les
  tentatives de fallback (`input_kwargs = {..., **kwargs}`, vérifié dans le
  wheel pinné — seule la clé `"model"` change entre l'appel primaire et un
  fallback). Un pin `google-vertex` + `allow_fallbacks:false` injecté pour
  un appel nominal `claude-opus` aurait survécu jusqu'à la tentative de
  fallback `claude-sonnet` (`fallbacks: [claude-opus: [claude-sonnet,
  gpt-codex]]`, litellm_config.yaml.j2), un modèle SANS pin configuré —
  un fournisseur qui ne le sert probablement pas, avec fallback interdit
  → échec dur du filet de secours lui-même. Préserver le comportement
  « absence de clé côté client = pin serveur jamais concurrencé au merge
  Router » (correct par construction, y compris à travers un fallback,
  vérifié fonctionner — c'est l'observation historique claude-opus →
  Google) pour le cas STRICTEMENT nominal évite ce risque.
- Modèle sans pin serveur configuré (alias non pinné, ou lookup Router
  indisponible/ambigu — aucun cas actuel dans `litellm_config.yaml.j2` où
  un alias pinné a plus d'un deployment) → comportement conservateur
  inchangé : la tentative d'override client est simplement supprimée (deny
  by default, pas de valeur à reconstituer).

**Résidu assumé (non résolu, à documenter §5)** : si le client envoie une
cle `extra_body` (override ou non) ET que l'appel tombe en fallback, le
pin injecté pour le modèle PRIMAIRE ride quand même dans la tentative de
fallback (même mécanisme que ci-dessus, non résolu pour CE sous-cas —
seul `claude-opus` est concerné parmi les alias pinnés, seul présent dans
la map `fallbacks:`). Périmètre plus étroit que le risque initial
(déclenché seulement si le client envoie explicitement un `extra_body`),
mais réel.

**Preuve** : `_enforce_provider_pin()` testé (a) offline sans litellm
installé (repli conservateur "delete", fonction pure) ; (b) avec
`litellm[proxy]==1.83.3` réellement installé + un `Router` réel exposé
comme `litellm.proxy.proxy_server.llm_router`, sur les cas override
explicite, incident reproduit à l'identique (`extra_body` vide,
`extra_body` avec sous-clé légitime sans `provider`), nominal (confirmé
NON touché — pas de fabrication), modèle non pinné/inconnu — tous PASS ;
(c) **preuve empoisonnement-fallback** : simulation de la réutilisation
exacte du dict `kwargs` par le mécanisme de fallback (seule `"model"`
change) — confirmé qu'un appel nominal ne transporte plus aucune clé
`extra_body` vers un fallback (poisoning évité pour ce cas) ; (d) **preuve
la plus forte** : appel direct de `ProxyLogging.pre_call_hook()` (le vrai
point d'entrée `proxy_server.py`) PUIS reproduction EXACTE de la formule de
merge `router.py::_acompletion` (`{**litellm_params, "messages":…,
"caching":…, "client":…, **kwargs}`) sur les 3 cas (override, incident,
nominal) — le `extra_body` final qui atteindrait `litellm.acompletion()`
est strictement égal au pin serveur pour les 2 premiers, et au
`litellm_params` du déploiement réellement appelé (intact) pour le
nominal. Le même harnais, appliqué au comportement v1 (delete-only),
reproduit fidèlement l'incident (`extra_body: {}` final) — la preuve n'est
donc pas triviale (elle discrimine bien l'ancien comportement bogué du
nouveau).

`test-extra-body-guard.sh` mis à jour : les 4 vecteurs (A top-level, B
`extra_body.provider`, **C `extra_body` sans `provider` — le vecteur exact
de l'incident**, D nominal) exigent tous une **égalité stricte** entre le
fournisseur attesté et le pin serveur (c'était déjà le cas pour A/B — le
comparateur n'a jamais accepté « différent de l'attaquant » comme critère
suffisant ; C et D sont nouveaux et couvrent spécifiquement la classe de
bug de cet incident). Vérifié en mode mock (curl stubé) : PASS sur les 4
avec un guard corrigé, FAIL ciblé sur B et C (A et D restent PASS) avec un
mock reproduisant le comportement incident — signature qui correspond
exactement à l'observation opérateur.

**Redeploy** : SEUL le contenu de `guard_extra_body.py` change dans ce
correctif — le point de montage (`roles/docker-stack/templates/compose/
apps-core.yml.j2`) est inchangé depuis le déploiement précédent. La task
`Deploy LiteLLM extra_body provider-pin guard callback`
(`ansible.builtin.copy`, `roles/litellm/tasks/main.yml`) détecte le
changement de contenu et déclenche `notify: Restart litellm stack`, dont
le handler (`roles/litellm/handlers/main.yml`) applique
`community.docker.docker_compose_v2` avec `recreate: always` sur le
service `litellm` — un recreate relit le bind mount `ro` avec le nouveau
contenu du fichier hôte. **Un redeploy `--tags litellm` seul suffit** ;
`docker-stack` n'a PAS besoin d'être retaggé cette fois (contrairement au
tout premier déploiement du garde-fou, qui introduisait le mount lui-même).

**Non déployé par cette session** — NE PAS déployer sans nouvel ack
opérateur explicite et sans avoir rejoué le protocole §4 (vecteurs A-D du
script mis à jour, en particulier C qui est le vecteur exact de
l'incident) contre le proxy réel après redeploy.
