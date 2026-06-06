# REX Session — Bulk mémoire sur pod GPU + optimisation bf16 (2026-06-06)

## Objectif

Terminer le **M3** du rebuild mémoire : ingérer en masse le corpus (7 sources git) dans Qdrant `memory_v2` (768d cosine, modèle `google/embeddinggemma-300m`) via un **pod RunPod jetable non-supervisé**, avec **parité stricte** worker Waza ↔ pod (mêmes `node_id`, ré-ingestion idempotente). Puis, sur demande utilisateur, **utiliser pleinement le matériel** sans sacrifier la qualité → solution pérenne et réutilisable.

État final : pipeline GPU prouvé bout-en-bout, corpus ≈ **23 672 chunks** ingérés, optimisation **git per-repo + encode batché + bf16** validée par mesure (1.64× sur fp32, dérive 0.99992).

---

## Erreurs rencontrées et résolutions

### 1. Estimation du corpus fausse (78 500 → 23 672) ❌ → corrigé
**Symptôme** : ETA calculées sur 78 500 chunks, irréalistes.
**Cause** : chiffre hérité d'une estimation jamais vérifiée. Le vrai corpus des 7 sources git ≈ 23 672 chunks (`memory_v2.points_count` après run complet).
**Leçon** : un dénominateur d'ETA est une donnée à mesurer, pas à supposer. Toute ETA citée doit pointer sa source.

### 2. Benchmark biaisé : 137 chunks/s mensonger ⚠️ → corrigé
**Symptôme** : `diag_bench` annonçait 137 chunks/s, démenti par la réalité (~0.5-1.5/s).
**Cause** : le bench encodait **512 strings identiques** → cache/padding triviaux, débit gonflé.
**Fix** : bench refait sur **vrais fichiers clonés, encodés par fichier** (mirror exact du bulk via `process_one`). Débit honnête.
**Leçon** : un microbench doit reproduire le chemin réel (mêmes textes, même découpage en batches). Pushback utilisateur fondateur : « il faut être sûr de ce que tu avances ».

### 3. Code commité mais JAMAIS poussé → pod cloné en version périmée ❌ → corrigé
**Symptôme** : pod tournait sur CPU (GPU 0%), sans le fail-fast attendu.
**Cause** : `git ls-remote` prouvait `origin/main = 988b219` alors que HEAD local = `a83a03b`. Le pod `git clone` **depuis GitHub** → il a cloné l'ancien code.
**Fix** : `git push origin main` (remote = `origin`, alias SSH `github-seko`, PAS `git push github-seko`).
**Leçon** : tout artefact exécuté par un pod/CI qui clone depuis GitHub exige un **push**, pas un commit local. Vérifier `git ls-remote origin` avant de lancer.

### 4. torch `cu13` (lock) silencieusement inutilisé sur driver 12.x ⚠️ → corrigé
**Symptôme** : `cuda.is_available()=False` → SentenceTransformer fallback CPU (GPU 0% compute, 3% mém, vu par télémétrie RunPod live).
**Cause** : `requirements.lock` pinne `torch==2.11.0` = build **cu13** (CUDA 13) → exige driver hôte CUDA ≥ 13. Hôtes RunPod souvent en driver 12.x.
**Fix** : bootstrap détecte la CUDA-max du driver via `nvidia-smi` (runtime) et réinstalle torch depuis l'index cuXY ≤ cmax. Vérifié sur download.pytorch.org : torch 2.11.0 existe sur cu126/cu128/cu130 (version préservée si driver ≥ 12.6), cu124 ≤ 2.6, cu121 ≤ 2.5, cu118 ≤ 2.7. **Le L4 obtenu était en driver 580.159.04 / CUDA 13.0 → cu13 du lock conservé** ; le fix reste la robustesse pour tout autre hôte.
**Leçon** : sur GPU loué, ne jamais supposer la version CUDA. La détecter + **fail-fast** (`EXPECT_CUDA=1` → assert `cuda.is_available()` + `dtype==fp32`) pour éviter un fallback CPU silencieux à 45× plus lent.

### 5. Mauvaise lecture de SA PROPRE mesure : git « 66% » → en réalité ~13% du total ❌ → corrigé
**Symptôme** : refonte engagée pour éliminer `git_commit_sha`, présenté comme 66% du temps.
**Cause** : les 66.6% étaient la part de git dans le temps **hors-encode** (57.8 ms/f), pas du total. Arithmétique sur la donnée GPU réelle (`diag_bench` : 437 ms/f total) : hors-encode ~13%, **encode ~87%**. Le vrai goulot = l'**encode**, pas git.
**Fix** : garder le fix git (utile : ×180 sur sa tranche, 11k subprocess en moins, ~10% du total) mais reconnaître que le levier « plein usage matériel » est l'**encode** (batch + bf16).
**Leçon** : toujours lire le **dénominateur** d'un pourcentage. Une optimisation « x180 » sur 13% du total ne sauve que ~10%.

### 6. `encode_batch=256` → OOM CUDA sur L4 24GB ❌ → corrigé
**Symptôme** : bench rc=1 (exception), GPU OK au warm-up.
**Cause** : 256 séquences × jusqu'à 2048 tokens en fp32 dépasse 24GB (activations). Le per-fichier (~13 chunks) ne saturait jamais.
**Fix** : `encode_batch=64` (¼ du footprint). En **bf16** (½ mémoire), 64 reste sûr et atteint 53 ch/s.
**Leçon** : la taille de batch est le levier débit sur GPU, mais bornée par la VRAM × longueur de séquence. Mesurer, ne pas pousser à l'aveugle.

### 7. Traceback perdue 2× par un `grep BENCH`-only ⚠️ → corrigé
**Symptôme** : `diag_bench` ne montrait que `rc=1 bench_line=[]`, pas la cause.
**Cause** : G7b faisait `python ... 2>&1 | grep BENCH` → la traceback (stderr) était filtrée.
**Fix** : capturer **toute** la sortie, extraire BENCH au succès, **dumper le tail (1200c) dans `diag_bench` à l'échec**.
**Leçon** : sur un pod sans logs API, l'observabilité d'erreur est vitale. Ne jamais grep-filtrer avant d'avoir capturé la trace.

### 8. bf16 écarté à tort puis réhabilité par mesure ✅
**Symptôme** : « bf16 inutile car l'encode n'est pas le goulot » — faux (cf erreur #5).
**Cause** : conclusion bâtie sur le mauvais split. L'encode EST le goulot → bf16 (tensor cores L4, 30→~240 TFLOP) est LE levier.
**Fix** : mesure de dérive fp32-vs-bf16 (autocast GPU, 398 chunks) → **min=0.99992 / mean=0.99997** (~0.73° pire cas, retrieval-équivalent). EmbeddingGemma = Gemma-dérivé = **bf16-natif** → bf16 aussi fidèle que fp32. Débit bf16 = 53.2 ch/s vs 32.4 fp32 (**1.64×**).
**Leçon** : le gate qualité est la **dérive mesurée** (min cosinus > 0.999), pas un dogme fp32. Pour un modèle bf16-natif, fp32 est un sur-échantillonnage.

### 9. ARM (Pi5) n'a pas de bf16 matériel → worker reste fp32 ✅
**Symptôme** : `model.to(bfloat16)` sur Waza → `UserWarning: mkldnn_matmul bf16 path needs a cpu with bf16 support` → fallback BLAS.
**Cause** : le CPU ARM Cortex-A76 n'a pas d'unité bf16 → PyTorch recalcule en fp32 (fallback) = **zéro gain** + spam warning à chaque matmul.
**Fix** : schéma **hybride** — pod (L4) = bf16 (autocast cuda) ; worker + search Waza = fp32. Mixage sûr (dérive croisée 0.00008). L'encodeur partagé reste **fp32-pur** ; bf16 est un flag `--bf16` côté pod uniquement (`torch.autocast`).
**Leçon** : tester la dépendance sur le matériel cible (R4) avant de l'imposer. bf16 « partout » n'a de sens que là où le HW le supporte.

### 10. Self-stop interne renvoie HTTP 403 → risque de pod facturé ⚠️ → mitigé
**Symptôme** : `[stop] HTTP 403` dans le trap du pod ; sans filet, le pod resterait RUNNING.
**Cause** : la requête stop depuis l'intérieur du pod a été refusée (la même clé stoppe pourtant depuis Waza ; cause exacte non creusée).
**Fix** : le watcher Waza **tue activement** le pod (`provision_pod.sh --stop`) en fin de boucle/échec/timeout, sans dépendre du self-stop.
**Leçon** : pour un pod « unattended », le chemin de kill ne doit jamais dépendre uniquement de l'auto-arrêt du pod. Filet externe obligatoire.

### 11. Pod mort en G3 (clone) sans diag, transitoire ⚠️
**Symptôme** : un pod EXITED entre `stage_g2` et `stage_g3`, aucun diag.
**Cause probable** : échec clone transitoire (réseau). Les `fail()` de clone n'écrivent pas de `report_diag`. Relaunch → passé sans souci.
**Leçon** : ajouter un `report_diag` aux gates clone serait un plus d'observabilité (amélioration future).

---

## Architecture finale (pérenne, réutilisable)

| Élément | Choix | Pourquoi |
|---|---|---|
| Modèle | `embeddinggemma-300m` 768d | qualité MTEB-multilingue, aucun équivalent rapide |
| `node_id` | `sha(ref_id:chunk_index:chunk_text)` — **texte seul** | parité worker/pod indépendante du dtype/HW ; ré-ingestion idempotente |
| Pod bulk (L4) | **bf16** autocast cuda, batch 64, git per-repo, encode batché cross-fichier | tensor cores → ~53 ch/s ; dérive 0.99992 |
| Worker + search Waza (ARM) | **fp32** | pas de bf16 HW ; incrémental, volume faible |
| Encodeur partagé | **fp32-pur** | bf16 reste un flag pod-side → worker intact, zéro risque parité |
| git_sha | `build_repo_git_shas` (1 traversée/repo) | ×180 vs subprocess/fichier, parité 300/300 |
| Observabilité pod | collections Qdrant `stage_*` / `diag_*` | RunPod n'expose pas de logs via API |
| Réseau | Headscale userspace + **pont socat** `qd→Sese:443` via proxy `:1055` | bypass split-DNS (qd = IP publique → Caddy vpn_only 403) |
| Anti-orphelin | trap self-stop + **watcher kill actif** | self-stop interne peut renvoyer 403 |

## Chiffres mesurés (preuves)

| Mesure | Valeur | Source |
|---|---|---|
| Débit CPU | 0.5 ch/s (Waza ARM) | bench réel |
| Split GPU per-fichier | 437 ms/f total, encode ~87% | `diag_bench` |
| git per-fichier | 38.5 ms/f (66.6% du hors-encode) | bench Waza 200 fichiers |
| git batch | ×180 (62s→0.35s, 1503 fichiers VPAI), parité 300/300 | test local |
| fp32 batch-64 | 32.4 ch/s (+42% vs 22.8 per-fichier) | `diag_bench` |
| **bf16** | **53.2 ch/s** (1.64×) | `diag_bench` |
| Dérive fp32↔bf16 | **min 0.99992 / mean 0.99997** (n=398) | autocast GPU |
| Driver L4 | 580.159.04 / CUDA 13.0 | `nvidia-smi` (diag_gpu) |

## Commits

`988b219` (OMP/bench) → `a83a03b` (GPU + fail-fast cuda/fp32 + bench honnête) → `33966d7` (torch driver-aware) → `a193bd7` (git per-repo + encode batché) → `68898f2` (split cpu/gpu + dérive bf16 + encode_batch 64) → `4aabd1f` (bulk bf16 hybride).

## Reste à faire (post-bulk bf16)

1. Vérifier compte final bf16 ≈ 23 672 (preuve d'écrasement idempotent complet).
2. **Teardown** : terminer pod, révoquer clé Headscale (éphémère) + PAT, `rm pod-ingest.env`, supprimer collections `stage_*`/`diag_*`/`probe_ok`/`ingest_done`.
3. **Rotation secrets exposés** : `HF_TOKEN`, `QDRANT_API_KEY`, `RUNPOD_API_KEY`.
4. **M4** : repointer `search_memory.py` + `qdrant-find` sur `memory_v2`, retirer `r0-rebuild.flag` + bloc hook `r0Rebuild`, purger `.bak`.
