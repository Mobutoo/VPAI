# Revue adversariale — Prisme CANARY-1 (adapter Instagram) — 2026-08-03

> Reviewer : agent Opus (revue adversariale). Périmètre : commits `8461b60..06f6099`
> (5 commits, roles/prisme-fetcher). Verdict : **NO-GO** — 1 CRITICAL / 7 HIGH / 8 MED / 4 LOW.
> Correctifs exigés avant re-revue : tous C/H, MED au jugé, LOW documentables.

## CRITICAL

### C1 — Le bloc de vérification Instagram de molecule ne peut pas s'exécuter (filtre Jinja inexistant)
`molecule/default/verify.yml:357-380`

`map('lookup', 'ansible.builtin.file')` : `lookup` est une fonction globale Jinja côté Ansible,
pas un filtre (et l'ordre des arguments serait inversé). La tâche part en erreur de templating →
les 5 assertions centrales (rejet handle, mismatch, range invalide, `state: blocked`,
`blocked:challenge_required`) n'ont jamais tourné vertes.

Fix : lire chaque manifeste par `ansible.builtin.slurp` en boucle sur
`instagram_manifests.files`, agréger `results | map(attribute='content') | map('b64decode') | join('\n')`,
puis assertion `is search(...)`.

## HIGH

### H1 — L'étape `idempotence` de molecule échoue par construction
`converge.yml:39` + `tasks/main.yml:328-353`

`converge.yml` surcharge `prisme_instagram_gallery_dl_bin` vers un stub déployé seulement dans
`verify.yml` (qui passe APRÈS `idempotence` dans la séquence molecule par défaut). La sonde
`--version` échoue à chaque converge → `pipx install --force` `changed_when: true` à chaque run
→ 2e run ≠ 0 changed.

Fix : dissocier — sonder/installer `{{ prisme_instagram_gallery_dl_pipx_bin_dir }}/gallery-dl`
(chemin réel invariant) ; `prisme_instagram_gallery_dl_bin` ne pilote que l'invocation worker.

### H2 — Première installation enabled=true : service démarré avant l'existence des cookies
`tasks/main.yml:113-120` vs `286-297`, `prisme-fetcher.service.j2:29`

L'unité contient `LoadCredential=` (obligatoire) mais le fichier source est déployé bien plus bas
→ `Failed to set up credentials` → `systemd_service state: started` fait échouer le play à la
première installation canary.

Fix : déplacer tout le bloc Instagram (répertoire + cookies + pipx) AVANT « Install hardened
service » / la tâche `systemd_service`.

### H3 — Contournement d'allowlist : pattern `.instagram.com` passe l'assert
`tasks/main.yml:233-234` vs `prisme-fetcher.py.j2:210-221`

L'assert compare des chaînes exactes (`'instagram.com' not in ...`) mais `domain_allowed()`
accepte les patterns à point initial : `['.instagram.com']` passe l'assert et rouvre
instagram.com/www/i.instagram.com aux adapters http/ytdlp génériques (sans handle, sans cookies,
sans rate-limit IG). Espaces parasites non traités.

Fix : asserter sur la sémantique résolue — pour chaque `p`, rejeter si
`p | trim | lower | regex_replace('^\\.', '')` ∈ `['instagram.com','www.instagram.com']` OU si
`'instagram.com'`/`'www.instagram.com'` se termine par `p | trim | lower` quand `p` commence par `.`.

### H4 — Allowlist de handles décorative sur `/p/`, `/reel/` ; contournable sur `/stories/<victime>/`
`prisme-fetcher.py.j2:307-333`

Pour `https://www.instagram.com/p/<shortcode>/` (cas d'usage cible), `url_handle` est `None` →
seule vérification = le champ `handle` AUTO-DÉCLARÉ du job ∈ allowlist ; le shortcode peut
appartenir à n'importe quel tiers. `stories/<victime>/123/` : la victime est en segment 2, jamais
comparée. Le manifeste écrit pourtant `allowlist_match: true`.

Fix : enforcement POST-acquisition — `fetch_instagram` extrait déjà `metadata["username"]` du
sidecar. Si un seul média a `username` ≠ handle autorisé (ou absent) : purge workdir, rien livré,
`state="rejected"`, `reason="username_not_allowlisted"`. Traiter aussi le 2e segment `stories/`.

### H5 — Crash entre succès gallery-dl et livraison = perte de données définitive silencieuse
`prisme-fetcher.py.j2:522` (`--download-archive`) + `714-724`

L'archive est écrite PENDANT le téléchargement, avant `deliver_instagram_bundle`. Crash entre les
deux (SIGKILL/OOM `MemoryMax=1G`/reboot) → relance : `files_info == []` → job `done`,
`skipped_already_acquired`, aucun bundle, plus jamais re-téléchargeable (état terminal + GC).

Fix : n'alimenter l'archive partagée qu'APRÈS livraison réussie (archive par job dans workdir,
fusionnée post-`replace()`), ou traiter `files_info == []` comme erreur sauf si un bundle
référencé par ce `job_id` existe déjà dans `outgoing/`.

### H6 — Archive partagée inter-jobs : bundle partiel livré et déclaré complet
`prisme-fetcher.py.j2:57, 522, 725-732`

Job B dont la plage recouvre des posts déjà acquis par job A reçoit le delta seulement →
`manifest["files"]` = sous-ensemble publié comme complet, rien ne signale l'incomplétude.

Fix : archive scopée par job (ou handle+range), et/ou comparer borne haute de `--range` au nombre
livré et poser `manifest["partial"]: true` sinon.

### H7 — Deadline rend tout job multi-média impossible et réarme le retry agressif
`prisme-fetcher.py.j2:527, 537` + defaults (rate 45s, range 1-20, http_timeout 30s)

`--sleep-request 45` × plage 1-20 ⇒ ≥ 855 s de sommeil ; deadline = 30×20 = 600 s → kill
`instagram_timeout` → `handle_failure` → retry backoff ×5 = re-frappe répétée d'Instagram
(violation « pas de retry agressif »).

Fix : `deadline = range_upper * (RATE_LIMIT + HTTP_TIMEOUT) * marge`, dérivé de la borne haute
réellement passée à `--range`.

## MEDIUM

### M1 — « même unité = un seul writer SQLite » : garantie non enforcée
`prisme-fetcher.service.j2:20-24` vs `prisme-fetcher.py.j2:127-161`
Aucun flock/busy_timeout/BEGIN IMMEDIATE ; verify.yml lance lui-même un `--once` en parallèle du
service. Fix : poser réellement le verrou (`fcntl.flock` sur `ROOT/.worker.lock` +
`busy_timeout=5000` + `BEGIN IMMEDIATE`), ou corriger le commentaire (convention non enforcée).

### M2 — `no_log: true` sur les asserts annule le fail-loud
`tasks/main.yml:228-245`, `247-273`
`no_log` censure `fail_msg` → fail-muet. `assert` ne rend pas les valeurs, seulement l'expression.
Fix : retirer `no_log` de l'assert prérequis ; pour Netscape, calculer les booléens en `set_fact`
`no_log: true` et asserter dessus sans `no_log`.

### M3 — Validation cookies : lignes `#HttpOnly_` ignorées, ni `sessionid` ni expiration vérifiés
`tasks/main.yml:251-264`
`reject('match','^\s*#')` élimine `#HttpOnly_.instagram.com …` or `sessionid` EST HttpOnly dans un
export navigateur. Fix : normaliser `#HttpOnly_` comme ligne de données ; asserter présence d'une
ligne champ 6 == `sessionid` avec champ 5 `0` ou > now (MED Codex « expiration »).

### M4 — Stub molecule ne valide aucun argv réel gallery-dl
Fix : assertion sur le binaire réel (`gallery-dl --help` contient chaque option utilisée) ou
exécution `--simulate` hors réseau.

### M5 — Marqueurs `"403"`/`"429"` en sous-chaînes courtes → blocked terminal sur transitoire
`defaults` markers + `prisme-fetcher.py.j2:349-354`
Un shortcode `C403xyz` déclenche `blocked:auth`. Fix : ancrer (`\b(401|403|429)\b` sur lignes
d'erreur, ou marqueurs longs `http error 429`, `429 too many requests`).

### M6 — Collision post-assainissement : média non traité écrasé
`prisme-fetcher.py.j2:586-596`
`["x!.jpg","x_.jpg"]` → `replace()` écrase le second média avant itération. Fix : initialiser
`seen_filenames` avec les noms originaux restants, ou cibles systématiques `{digest[:16]}_{name}`.

### M7 — Collision de digest bundle → manifeste d'un autre job en référence
`prisme-fetcher.py.j2:623-628, 729-732`
Fix : `manifests/<job_id>.json` par job, `jobs.manifest_path` pointe dessus (traçabilité audit).

### M8 — `allowlist_scope` absent du manifeste Instagram
Fix : `allowlist_scope: "input_url_only"` ; après H4 : `"verified_username"`.

## LOW

- **L1** sidecar résolu APRÈS renommage → metadata perdue si nom assaini (neutralise H4-fix) :
  résoudre depuis `media.name` AVANT `replace()`. `prisme-fetcher.py.j2:594-601`
- **L2** comparaison version par sous-chaîne (`1.30.2` ⊂ `1.30.20`) : comparer `stdout | trim`
  exact. `tasks/main.yml:351`
- **L3** désactivation incomplète : gallery-dl + archive restent après disable — décision
  explicite à documenter ou `state: absent` sur l'archive.
- **L4** `blocked` irréversible (job_id = sha256 du fichier, ligne terminale + GC) : documenter la
  procédure de reprise opérateur.

## Sains (vérifiés)

Netscape rejette JSON/vide/espaces ; stderr gallery-dl jamais dans erreurs/manifestes ; cookies
jamais en argv ; `$CREDENTIALS_DIRECTORY` seul chemin runtime, source 0400 root:root ; unité
valide quand disabled ; IPAddressDeny compatible IG (IP publiques) sans affaiblissement ; schéma
http/https vérifié pour les 3 adapters ; manifeste avant téléchargement ; sidecars non livrés ;
min_free/plafond disque appliqués + workdir purgé sur tous les chemins ; FQCN/changed_when OK ;
`blocked` terminal.

Non vérifiable localement : existence release gallery-dl 1.30.2 + noms exacts des options (→ M4).

---

# CYCLE 2 (2026-08-03, post-correctifs fd44c2e/488c3d8/22db5e6) — NO-GO

17/20 findings cycle 1 résolus (vérifiés) ; 3 partiels (H3→M-D, H6→M-A/H-B, M7→M-C).

## CRITICAL
- **C1-bis** `verify.yml:137,426,533` : les 3 `--once` Instagram tournent sans
  `$CREDENTIALS_DIRECTORY` → `instagram_cookies_unavailable` → retry_wait ; les scénarios
  blocked/carousel/impostor ne peuvent pas passer. Fix : `environment: CREDENTIALS_DIRECTORY:`
  + dépôt du credential 0400 owner prisme-fetcher, ou `systemd-run -p LoadCredential=…`.

## HIGH
- **H-A** `py.j2:926-949` : régression 488c3d8 — `manifest["state"]="done"` supprimé du chemin
  succès Instagram (http/ytdlp le posent toujours) → schémas source-bundle.v2 divergents +
  verify `state == "done"` échoue. Fix 1 ligne avant deliver.
- **H-B** `py.j2:895-923,853-854` : dédup cross-job (job B sur contenu déjà livré par A) →
  `files_info==[]` → `failed` terminal irrécupérable + GC → re-dépôt du même payload re-GC
  immédiat. Fix : discriminer — archive seedée non vide + résultat vide = `done` +
  `skipped_already_acquired` + `partial` ; `failed` réservé à archive seedée vide ET rien produit ;
  étendre la procédure L4 à cet état.
- **H-C** `py.j2:846,616-618` : `range` du payload non plafonné → deadline arbitraire
  (1-99999 ≈ 1,5e7 s) ; worker mono-thread + flock M1 = pipeline gelé, heartbeat compris.
  Fix : `prisme_instagram_range_max_upper` (rejet range_upper_too_large) + plafond dur
  `INSTAGRAM_MAX_JOB_SECONDS` + `touch_heartbeat` dans la boucle d'attente.

## MEDIUM
- **M-A** `py.j2:936` : `partial = len(files) < range_upper` ignore la borne basse → true quasi
  systématique (bruit). Fix : span = upper-lower+1 ; exposer `range_lower` + `partial_reason`.
- **M-B** `py.j2:944` : succès Instagram archivés sous `rejects/<job_id>/`. Fix : pas de snapshot
  sur succès, ou renommer `audit/`.
- **M-C** `py.j2:808` vs `:1078` : `jobs.manifest_path` = deux sémantiques selon adapter (aucun
  consommateur aujourd'hui — vérifié). Fix : `write_manifest_record` sur les 3 adapters.
- **M-D** `tasks/main.yml:128-138` : assert H3 limité à instagram.com/www — `m.instagram.com`
  passe. Fix : assert sur suffixe `instagram.com` générique.
- **M-E** `py.j2:150` : lock ouvrable root (debug) → PermissionError non rattrapée → crash-loop.
  Fix : open dans le try/except OSError + chown best-effort.
- **M-F** : `manifests/` + `rejects/` sans rétention/GC. Fix : purge par âge ou tmpfiles.
- **M-G** `py.j2:688` : clé sidecar `username` jamais confrontée à un gallery-dl réel (indice :
  gallery-dl expose `post_shortcode`, pas `shortcode`) ; rejet terminal potentiel de contenu
  légitime. Fix : fixture réelle en CANARY-5 ; repli owner.username ; distinguer
  `username_absent` (retriable borné) de `username_mismatch` (terminal).

## LOW
- **L-A** verify:294 : `--destination` n'existe pas (c'est `--directory`) — garde-fou M4 inopérant.
- **L-B** branche `prior["output_path"]` quasi morte (GC post-done) — assumer ou remplacer par H-B.
- **L-C** `mark_domain_fetch` avec `now` de début de passe → rate-limit inter-jobs neutralisé après
  un job long. Fix : `int(time.time())` au marquage.
- **L-D** assert trim vs worker sans trim (faux positif fail-loud, direction sûre). Aligner.

## Jugements des déviations
- H5 terminal : recevable sur « pas de retry déterministe », NON recevable pour le cas dédup (H-B).
- M7 Instagram-only : NON acceptable (M-C, fix ~4 lignes).
- L3 disable=secret seul : ACCEPTABLE (raisonnement vérifié, LoadCredential disparaît au restart).
- Résiduel crash deliver : conséquence réelle faible — `.part` exclu du transfert, écrasé au retry.

---

# CYCLE 3 (2026-08-03, post-correctifs 66790ad/03e4ff2/9aa1110) — NO-GO

14/14 findings cycle 2 traités (12 pleins, M-E→L3, M-G→R3). 2 HIGH NOUVEAUX (reproduits
empiriquement), 3 MED, 5 LOW.

## HIGH
- **R1** py.j2:963-1040 : `archive_seeded_nonempty = st_size > 0` est GLOBAL, pas scopé au job →
  dès la 1re livraison de la vie du canary, tout job qui n'acquiert RIEN devient
  `done`+`skipped_already_acquired` (perte silencieuse H5 par une autre porte) ; branche
  `instagram_empty_result_no_prior_delivery` = code mort en prod dès J+1 ; en plus st_size d'une
  base SQLite vide = 8192. Fix : compter les lignes de la table d'archive (pattern
  merge_instagram_archive) ET scoper au job — lire `.gallery-dl.stdout` (écrit :655, jamais relu)
  pour compter les skips archive de CETTE url (à confronter au binaire 1.30.2 réel) ; à défaut,
  `done` seulement si bundle des sha256 attendus existe.
- **R2** py.j2:673-703 : toute exception dans la boucle d'attente (dont le NOUVEAU
  touch_heartbeat = write SQLite/s, OperationalError atteignable) sort du `with Popen` sans
  terminate → gallery-dl ORPHELIN hors deadline/plafond taille/cgroup, workdir rmtree sous ses
  fd. Fix : try/finally terminate()+kill() sur toute sortie + try/except sqlite3.Error sur le
  heartbeat (et même traitement pour dir_size).

## MEDIUM
- **R3** py.j2:981-992 : `absent` testé avant `mismatched` → impostor confirmé masqué en
  retriable (5 re-téléchargements de contenu tiers). Fix : mismatched d'abord.
- **R4** : `5-3` accepté (span négatif → partial toujours False) + range_default non confronté à
  range_max_upper dans l'assert (fail-loud REX-62). Fix : rejet range_lower>range_upper +
  assert déploiement.
- **R5** verify.yml:340-393 : stub sans sémantique --download-archive → branches H-B jamais
  exercées (cause racine de R1 non détecté). Fix : reprendre le stub du reviewer + 3 scénarios
  (dedup, vide sans archive, sidecar sans username).

## LOW
- L1 MAX_JOB_SECONDS dérivé de la constante qu'il est censé borner (no-op) → var explicite.
- L2 purge_old_artifacts à chaque poll (2 s) → cadencer 1x/h.
- L3 crash-loop lock root : StartLimitIntervalSec/Burst absents + lock à créer par le rôle.
- L4 jobs.manifest_path orphelin post-purge + nom de var trompeur (purge aussi http/ytdlp).
- L5 contrat : `done` H-B sans files/delivered_count/output_path — à figer dans la doc
  source-bundle.v2 avant CANARY-5.

Artefacts banc reviewer : scratchpad stub.py (sémantique --download-archive), harness/worker.py,
worker_hbfail.py (repro R2).

---

# CYCLE 4 (2026-08-03, post-correctifs cycle 3, diff 9aa1110..HEAD) — GO AVEC RÉSERVES

R1 (preuve job-scopée `prior_delivery`) et R2 (finally terminate/kill) TIENNENT — vérifiés au banc
contre le template réel (24 checks PASS, sondes cycle 4). 0 CRITICAL / 0 HIGH / 3 MED / 6 LOW.

## MEDIUM (M1+M2 avant CANARY-5, M3 à trancher avec binaire réel)
- **M1** defaults:206-218 : la procédure de reprise documentée est cassée par R1 (archive dédup
  par média, pas par URL ; DELETE de la ligne done détruit la preuve prior_delivery). Fix : doc —
  reprise = purger AUSSI l'entrée de gallery-dl-archive.sqlite3 (service arrêté) + avertir que la
  ligne jobs done est load-bearing.
- **M2** tasks:186-215 : l'assert ne rejette pas `range_default: "10-5"` alors que le worker
  rejette lower>upper → tous les jobs sans range explicites rejetés au runtime. Fix 2 lignes :
  `_range_default_lower` + condition lower<=upper.
- **M3** py.j2:1177-1195 : prior_delivery scopé URL, pas plage → done+archive_overlap peut
  affirmer « déjà acquis » pour une plage jamais livrée. Mislabel certain ; nocivité dépend du
  code de sortie gallery-dl sur média nul → check CANARY-5 (avec post_shortcode/username fixture).

## LOW
- L1 : prédicat prior_delivery sans `adapter='instagram'` (une ligne http done même URL suffit).
- L2 : dir_size `except OSError: pass` → total partiel → plafond taille contournable ; fail-closed.
- L3 : contrat L5 non assertable via _all_manifests_joined (slurper le seul manifeste
  archive_overlap et asserter l'ABSENCE de files/delivered_count).
- L4 : finally — proc.wait(10) post-kill peut lever TimeoutExpired et masquer la cause.
- L5 : StartLimitBurst = mort permanente sans détecteur (aucun consommateur heartbeat, alerting
  cible l'app Sese pas le fetcher waza) → OnFailure= ou runbook reset-failed (CANARY-5).
- L6 : filtre sqlite\_% escape dans row_count mais pas merge — aligner.
Nits : push = 22 commits (toute la chaîne) à assumer ; docs/reviews/ à committer ; commentaire
tasks:59 « ci-dessus » erroné.
