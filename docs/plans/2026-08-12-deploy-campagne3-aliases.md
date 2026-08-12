# Plan de déploiement — alias campagne 3 (rangs hauts) + correction gen 4→gen 5

Statut : PRÉPARÉ, NON DÉPLOYÉ. Branche `chantier/campagne3-aliases`
(VPAI), commit(s) listés en fin de document. Le deploy lui-même est un
geste opérateur (ack high-risk requis, comme au gate technique B4.3 du
2026-08-11).

Sources : `docs/research/2026-08-12-b4-candidats-rangs-hauts.md` (couples
pinnés §3, campagne §5), `docs/ops/gates-journal.md` entrées 2026-08-12
« gate campagne 3 rangs hauts » et « gate TECHNIQUE B4.3 » (protocole de
preuve repris ci-dessous), `docs/specs/2026-08-11-b4-design-escalade-modeles-implement.md`
§7.1 (`opus-cached`).

## 0. Point de décision opérateur — AVANT tout deploy

**`claude-opus` change de modèle sous-jacent** (openrouter/anthropic/claude-opus-4
→ claude-opus-5, prix $15/$75 → $5/$25, gain ≈3×) **ET devient pinné ZDR
(google-vertex) + `allow_fallbacks:false`**. Consommateur identifié :
`roles/openclaw/defaults/main.yml` l.193, profil `premium.reasoning` (profil
par défaut d'OpenClaw = `eco`, donc `claude-opus` n'est PAS sur le chemin
critique tant que personne ne bascule le profil sur `premium`) — impact
réel faible mais réel si un opérateur ou un futur run bascule ce profil.

**Résidu non corrigé, à trancher explicitement** : la map `fallbacks:`
LiteLLM route toujours `claude-opus` → `claude-sonnet` → `gpt-codex` en cas
d'échec — ni l'un ni l'autre n'est pinné ZDR. Une panne du provider
`google-vertex` romprait silencieusement la garantie ZDR pour ce rang (pas
un problème aujourd'hui : `claude-opus` n'est pas sur un chemin
tenant-data, seulement OpenClaw dev-agent). Options pour le gate opérateur :
(a) laisser tel quel (ce plan, défaut) ; (b) retirer `claude-opus` de la map
`fallbacks:` pour cohérence stricte avec la discipline fail-closed
(hard-fail au lieu de fallback silencieux non-ZDR) — changement de
comportement additionnel, NON fait ici faute de mandat explicite.

**`claude-sonnet-cached` NON touché** (choix sûr par défaut). Consommateurs
identifiés : `scripts/rotate-smoke-key.sh`, `scripts/probe-prompt-cache.sh`
(repo optimus) — alias resté sur `openrouter/anthropic/claude-sonnet-4`,
non pinné ZDR, comportement inchangé. **Alternative disponible mais NON
appliquée** : migrer `claude-sonnet-cached` en place vers
`openrouter/anthropic/claude-sonnet-5` pinné ZDR — décision produit
(perf/coût vs continuité de comportement du harnais smoke), à trancher par
l'opérateur si souhaité. En l'état, un nouvel alias séparé
`claude-sonnet-5-cached` a été créé (voir §1) pour qui veut le nouveau
comportement sans toucher au premier.

## 1. Diff des alias (branche `chantier/campagne3-aliases`)

Fichier modifié : `roles/litellm/templates/litellm_config.yaml.j2`.

| Alias | Avant | Après | Statut |
|---|---|---|---|
| `claude-opus` | `openrouter/anthropic/claude-opus-4`, non pinné | `openrouter/anthropic/claude-opus-5`, pinné ZDR `google-vertex`, `allow_fallbacks:false` | CORRIGÉ en place |
| `claude-sonnet-cached` | `openrouter/anthropic/claude-sonnet-4`, non pinné | *(inchangé)* | INTACT (décision §0) |
| `claude-sonnet-5-cached` | n'existe pas | `openrouter/anthropic/claude-sonnet-5`, pinné ZDR `google-vertex`, caching, `allow_fallbacks:false` | NOUVEAU (migration sûre optionnelle) |
| `opus-cached` | n'existe pas | `openrouter/anthropic/claude-opus-5`, pinné ZDR `google-vertex`, caching, `allow_fallbacks:false` | NOUVEAU (rang 4 ladder B4.2 §7.1) |
| `glm-52` | n'existe pas | `openrouter/z-ai/glm-5.2`, pinné ZDR `digitalocean` | NOUVEAU (rang 3 recommandé) |
| `deepseek-v4-pro` | n'existe pas | `openrouter/deepseek/deepseek-v4-pro`, pinné ZDR `novita` | NOUVEAU (rang 3, repositionné H2) |
| `kimi-k3` | n'existe pas | `openrouter/moonshotai/kimi-k3`, pinné ZDR `digitalocean` (jamais DeepInfra — pas de `tools`) | NOUVEAU (rang 5) |
| `claude-sonnet-5-zdr` | n'existe pas | `openrouter/anthropic/claude-sonnet-5`, pinné ZDR `google-vertex` | NOUVEAU (bras de contrôle campagne 3) |

Tous les alias `campagne3` + `opus-cached`/`claude-sonnet-5-cached` : même
mécanique fail-closed que `eco-1`/`eco-2` — `provider.data_collection:
"deny"`, `provider.zdr: true`, `provider.allow_fallbacks: false`,
`provider.order` verrouillé à UN fournisseur, `cache_control_injection_points`
posé, **aucune entrée** dans la map `litellm_settings.fallbacks` (attestation
modèle forte, pas de fallback silencieux vers un endpoint non vérifié).

**Finding de revue intégré** : le slug provider OpenRouter pour Anthropic
via Google Cloud n'est **PAS** `"google"` (comme écrit au doc source
`docs/research/2026-08-12-b4-candidats-rangs-hauts.md` §115) mais
**`"google-vertex"`** — vérifié live contre `GET /api/v1/providers`
(2026-08-12 : entrée `{"slug": "google-vertex", "name": "Google"}`, aucune
entrée `slug=="google"` correspondant à Anthropic-via-cloud) et confirmé
par le `tag` des endpoints ZDR eux-mêmes (`google-vertex/global`,
`google-vertex/europe`, `google-vertex/us` — jamais `google/...`). Un
`provider.order: ["google"]` littéral n'aurait matché AUCUN fournisseur
réel et — combiné à `allow_fallbacks:false` — aurait fait échouer tous les
appels (fail-closed, pas fail-open, mais aurait cassé la campagne au
premier appel). Corrigé dans tous les blocs concernés.

Prix relevés live le 2026-08-12 contre `GET /api/v1/endpoints/zdr`
(722 endpoints) — **pas recopiés du dossier de recherche** :

| Alias | prompt $/M | completion $/M | cache_read $/M | contexte | tools |
|---|---|---|---|---|---|
| glm-52 (DigitalOcean) | 0.63 | 1.98 | 0.0945 | 262 144 | oui |
| deepseek-v4-pro (Novita) | 1.168 | 2.336 | 0.09855 | 1 048 576 | oui |
| kimi-k3 (DigitalOcean) | 2.85 | 14.25 | 0.285 | 1 048 576 | oui |
| claude-sonnet-5 (Google, région `global`/`us-east-1`) | 2.00 | 10.00 | 0.20 | 1 000 000 | oui |
| claude-opus-5 (Google/Bedrock, région `global`/`us-east-1`) | 5.00 | 25.00 | 0.50 | 1 000 000 | oui |

**Résidu de précision assumé** : `provider.order` pin le *fournisseur*
(slug), pas la *région*. Les endpoints Anthropic-via-`google-vertex` ont
un prix qui varie par région (`global`/`us-east-1` = base ci-dessus,
`europe` = ×1,1 sur claude-sonnet-5, claude-opus-5 identique
global/us-east-1 mais europe à $5,5/$27,5). `model_info` ci-dessus utilise
le prix de la région la moins chère (comportement observé par défaut sur
les runs précédents, non garanti contractuellement par OpenRouter) — le
coût réel facturé peut être jusqu'à ~10 % supérieur si le routage atterrit
sur `europe`. Même limite structurelle que `deepseek/deepseek-v4-flash-0731`
existant (`novita/fp8` vs autres quantizations) — non bloquant, à
surveiller sur le relevé `/key/info` post-run comme pour les autres tiers.

## 2. Vault / secrets

**Aucune clé nouvelle requise.** Tous les alias ci-dessus utilisent
`OPENROUTER_API_KEY` (déjà déployée, mappée à `openrouter_factory_api_key`
dans `inventory/group_vars/all/main.yml` l.168). Aucun secret touché sur
cette branche — le fichier `litellm.env.j2` n'a **pas** été modifié.

**Néanmoins, le rappel REX du mandat s'applique quand même** : la task
Ansible « Deploy LiteLLM config » (template `litellm_config.yaml.j2`) va
changer → `notify: Restart litellm stack` se déclenche → le handler
`roles/litellm/handlers/main.yml` utilise déjà `recreate: always` (fixé
suite au REX force-recreate documenté en l.12-13 du handler et
`TROUBLESHOOTING.md` §11.18) — **aucune action manuelle supplémentaire
requise pour le force-recreate**, il est déjà câblé par défaut sur CE
rôle. Vérifier simplement que le run Ansible ne passe pas
`--skip-tags handlers` ou équivalent.

## 3. Séquence de deploy exacte (geste opérateur)

```bash
source /home/mobuone/work/infra/VPAI/.venv/bin/activate
cd /home/mobuone/work/infra/VPAI
git checkout chantier/campagne3-aliases
ansible-playbook playbooks/stacks/site.yml \
  --tags litellm \
  --diff \
  --check          # 1. dry-run d'abord, lire le diff en entier (--diff)
# si le diff est conforme (SEUL litellm_config.yaml doit changer, PAS
# litellm.env — vérifier explicitement, no-op vault attendu comme au
# gate B4.3) :
ansible-playbook playbooks/stacks/site.yml \
  --tags litellm \
  --diff
# ack high-risk opérateur ici (recreate: always va redémarrer le conteneur
# litellm — attendre l'incident transitoire connu, ~2 min de 502 pendant
# les migrations, cf. gate B4.3 2026-08-11)
```

Puis merge `chantier/campagne3-aliases` → `main` (après le protocole de
preuve §4 rendu vert), push origin + gitea.

## 4. Protocole de preuve post-deploy (calqué sur gate TECHNIQUE B4.3)

À exécuter par l'opérateur ou en session déléguée immédiatement après le
deploy, résultat à journaliser dans `docs/ops/gates-journal.md` (nouvelle
ligne, même format que l'entrée B4.3 du 2026-08-11) :

**(a) Config effective (bind ro conteneur)** — inspecter le fichier monté
dans le conteneur `litellm` (pas seulement le rendu local) : chaque bloc
`glm-52`/`deepseek-v4-pro`/`kimi-k3`/`claude-sonnet-5-zdr`/
`claude-sonnet-5-cached`/`opus-cached`/`claude-opus` doit contenir
`data_collection: deny` + `zdr: true` + `allow_fallbacks: false` +
`order:` à UN seul fournisseur + `model_info` avec coûts non nuls. La map
`fallbacks:` ne doit contenir AUCUN des 6 NOUVEAUX alias comme clé.
`claude-opus` fait exception TANT QUE la décision §0 (option a, statu quo)
n'est pas tranchée vers (b) : sa présence dans `fallbacks:` est le résidu
documenté §0 — si l'opérateur tranche (b) au moment de l'ack, l'entrée est
retirée au même deploy et le contrôle redevient « aucun des 7 ».
```bash
docker exec <container_litellm> cat /app/config/litellm_config.yaml | \
  yq '.model_list[] | select(.model_name | test("glm-52|deepseek-v4-pro|kimi-k3|claude-sonnet-5-zdr|claude-sonnet-5-cached|opus-cached|claude-opus$"))'
```

**(b) Couples (modèle, fournisseur) toujours ZDR au moment du deploy** —
re-vérifier contre `GET https://openrouter.ai/api/v1/endpoints/zdr` (les
endpoints évoluent, comme au gate B4.3) :
```bash
curl -s https://openrouter.ai/api/v1/endpoints/zdr | \
  jq '.data[] | select(.model_id=="z-ai/glm-5.2" and .provider_name=="DigitalOcean")'
# répéter pour deepseek/deepseek-v4-pro+Novita, moonshotai/kimi-k3+DigitalOcean,
# anthropic/claude-sonnet-5+Google, anthropic/claude-opus-5+Google
```

**(c) Test de contournement client** — reproduire l'essai du gate B4.3 :
appeler un des nouveaux alias en forçant `provider: openai` (ou tout
provider hors liste) + `allow_fallbacks: true` + `data_collection: allow`
dans le corps de la requête client. Attendu : la politique proxy PRIME —
la réponse reste servie par le fournisseur épinglé (`order`), la tentative
de contournement est ignorée.

**(d) No-op vault** — la task Ansible « Deploy environment file » doit
rester `ok` (inchangé) sur ce déploiement précis (aucune clé nouvelle,
§2) : `changed=0` sur cette task précisément → vault == prod, confirmé.

**(e) Appels 1-token par alias, attestation fournisseur** — un appel
minimal par alias, vérifier le champ `provider`/`x-openrouter-provider`
(ou équivalent exposé par la réponse LiteLLM) pour chacun des 7 alias :
- `glm-52` → DigitalOcean
- `deepseek-v4-pro` → Novita
- `kimi-k3` → DigitalOcean
- `claude-sonnet-5-zdr` → Google (region indifférente, provider="Google"/`google-vertex`)
- `claude-sonnet-5-cached` → Google, + vérifier `usage.cached_tokens` sur 2
  appels identiques consécutifs (même exigence de preuve empirique que
  `claude-sonnet-cached` à l'origine — propagation `cache_control` via
  OpenRouter non garantie par la doc LiteLLM, cf. commentaire du bloc)
- `opus-cached` → Google/`google-vertex` EXCLUSIVEMENT (l'alias est
  verrouillé `order: ["google-vertex"]` — une attestation Amazon Bedrock
  = ÉCHEC du contrôle, le pinning ne tient pas)
- `claude-opus` → Google/`google-vertex` EXCLUSIVEMENT (même règle)

## 5. Reprise campagne 3 (post-deploy, hors périmètre de ce plan)

Une fois le protocole §4 vert, la campagne 3 telle que ratifiée au gate
(`docs/ops/gates-journal.md`, entrée 2026-08-12 midi « gate campagne 3
rangs hauts ») peut être lancée : GLM-5.2 (5×~31¢), DeepSeek V4 Pro
(5×~18¢), Kimi K3 (2×~102¢, jamais DeepInfra), bras de contrôle Sonnet 5
ZDR via `claude-sonnet-5-zdr` (3×~71¢) — total ~662¢, réserve dure 60¢,
clamp par tentative `min(plafond nominal, reliquat du bras, solde−60¢)`,
solde réel re-vérifié via `GET /key/info` (clé r6) avant CHAQUE tentative.

## 6. Manques identifiés

- Aucune clé vault manquante (§2).
- `ansible-playbook --syntax-check` du playbook complet n'a **pas** pu
  être exécuté dans cette session (gate outillage R0/qdrant indisponible
  au subagent — limitation d'environnement documentée, sans rapport avec
  le contenu du changement). Compensé par : `ansible-lint` profil
  `production` sur `roles/litellm` (0 failure/0 warning) + rendu Jinja2 du
  template avec valeurs factices + `yaml.safe_load` du résultat (valide,
  36 entrées `model_list`, aucun des 7 alias en doublon, aucun présent
  dans la map `fallbacks`). À faire tourner par l'opérateur avant le
  `--check` du §3 si souhaité, en filet supplémentaire.
- Décision §0 (retirer ou non `claude-opus` de la map `fallbacks:`) NON
  tranchée — posée explicitement à l'opérateur, pas de défaut appliqué
  au-delà du statu quo (option a).
