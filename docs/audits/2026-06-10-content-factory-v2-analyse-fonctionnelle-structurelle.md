# Content Factory v2 — Analyse fonctionnelle et structurelle

**Date** : 2026-06-10
**Objet** : remise en cause brique par brique de Content Factory (milestone v2026.3, 83%) pour en faire une application autonome de création de contenu IA — du reel 30 s au film 90 min — dépassant Higgsfield en expérience utilisateur, en auto-hébergé.
**Méthode** : croisement de 5 investigations — (1) état réel CF + REX, (2) fantrad/PodPilot, (3) Higgsfield & UX concurrents, (4) forensique Kitsu/Plane/NocoDB + ingestion + providers, (5) état de l'art vérifié juin 2026 (sources web datées, verdicts CONFIRMÉ/INCERTAIN).

**Sources internes citées** :
- `docs/PRD-CONTENT-FACTORY.md`, `.planning/STATE.md`, `.planning/phases/05-09/`
- `docs/rex/REX-SESSION-2026-03-22.md` (pipeline E2E + Kitsu), `docs/rex/REX-MOP-PIPELINE-2026-04-13.md`
- `docs/audits/2026-06-10-audit-strategique-vpai.md`
- `~/work/saas/fantrad/docs/runpod/{REX,REFERENTIEL-ARCHITECTURE,REFERENTIEL-COUTS,PROCEDURES}.md`
- `~/work/saas/podpilot/docs/CONTRACT.md` + specs

---

## 1. Diagnostic structurel — six défauts de naissance

CF v1 a prouvé le concept (pipeline E2E brief→vidéo qui marche). Mais six défauts structurels empêchent d'en faire un produit :

| # | Défaut | Preuve | Conséquence |
|---|---|---|---|
| D1 | **État éclaté sur 4 systèmes** : NocoDB (vérité) + Kitsu (tracking) + Plane (calendrier) + n8n (exécution), reliés par 3 workflows de sync **best-effort sans aucune observabilité d'échec** | audit 2026-06-10 §C ; `event_handler.py.j2` (failures avalées silencieusement) ; IDs Kitsu hardcodés dans STATE.md | Une désync est invisible ; impossible de raisonner sur l'état d'un contenu |
| D2 | **Pas de concept de "génération"** : `scenes.asset_url` stocke UNE url. Ni seed, ni modèle, ni paramètres, ni coût, ni variantes, ni généalogie des takes | schéma NocoDB, PRD §tables | Tue la boucle d'itération (re-roll/compare/choisir) — précisément ce qui fait gagner Higgsfield |
| D3 | **Orchestration = glue événementielle**, pas workflow durable : webhooks n8n + polling 270-300 s, pas de resume, pas de retry sémantique, pas de généalogie de jobs | `cf-*.json`, REX MOP (sessions MCP fragiles, payload 400) | Plafonne à ~60 s de contenu ; un film = milliers de jobs GPU sur des jours, ingérable |
| D4 | **Compute figé** (RPi5) : SDXL 30-60 s/scène, Remotion 720p/2,5 min, étape 9 séquentielle = 20-30 min, stalls sous charge | REX 2026-03-22 ; rapport CF §5.1 | Latence d'itération incompatible avec une UX "instrument" |
| D5 | **Boucle ouverte** : pas de veille active (MeTube/VRef = téléchargement ad-hoc, pas d'analyse), pas de retour analytics post-publication | forensique enquête 2 ; PRD étape 2 = WebSearch OpenClaw | Le système ne s'améliore jamais ; chaque brief repart de zéro |
| D6 | **Kitsu subi plus qu'utilisé** : torsion du modèle (1 contenu = 1 shot, 14 task types, `for_entity` bugs, JWT 7 j), pour n'utiliser réellement que previews + comments + statuts | REX 2026-03-22 §Kitsu ; forensique enquête 1 (tableau features) | On paie le coût d'un tracker d'animation studio pour 3 fonctions reproductibles |

**Lecture d'ensemble** : CF v1 est une *chaîne éditoriale* (gates, discipline, calendrier) — c'est sa force, à garder. Ce qui manque est l'*instrument créatif* (itération rapide, takes, comparaison, coût marginal nul) et la *colonne vertébrale produit* (un seul modèle de données, un orchestrateur durable, un plan compute élastique). La nouveauté décisive depuis v1 n'est pas les APIs vidéo (Veo/Seedance déjà éprouvées — REX 2026-03-22) : c'est **PodPilot et ses retours factuels** (coût, latence, dispo, cold-start mesurés par job), qui transforment le choix de provider d'une config statique en décision apprise et auditée.

---

## 2. Décision de structure — repo autonome

CF devient une application à part entière, hors VPAI. VPAI ne garde qu'un rôle Ansible mince de déploiement.

```
~/work/saas/content-factory/          # wing saas — doctrine MANIFESTE-CREATION-PROJET.md
├─ apps/
│  ├─ api/                # FastAPI — modèle de domaine, REST + SSE, auth
│  ├─ studio/             # Web UI desktop (l'atelier)
│  └─ telegram/           # bot télécommande (remplace le skill OpenClaw à terme)
├─ services/
│  ├─ conductor/          # workflows Temporal (pipeline durable, gates humaines = signals)
│  ├─ worker-comfy/       # worker GPU éphémère RunPod (pattern fantrad), appelé par le hub ComfyUI Waza via PodPilot
│  ├─ worker-render/      # ffmpeg/OTIO conform + Remotion (segments motion design)
│  ├─ worker-audio/       # TTS / musique / lipsync
│  └─ scout/              # ingestion + analyse — évolution de VideoRef-Engine (whisper, scenedetect, VLM)
├─ packages/
│  ├─ domain/             # schéma Postgres + types partagés (LA source de vérité)
│  ├─ providers/          # adapters: comfy-local, comfy-runpod, fal, veo, seedance, elevenlabs…
│  └─ timeline/           # OTIO pivot (EDL)
├─ infra/                 # compose dev ; le rôle Ansible vit dans VPAI et tire ce repo
└─ docs/
```

Dépendances externes assumées : Postgres (vérité), Qdrant (mémoires marque/tendances), Temporal, PodPilot (control-plane GPU), Postiz (connecteurs publication), LiteLLM (LLM), n8n (périphérie uniquement). Kitsu et Plane **sortent du chemin critique** (cf. B1).

---

## 3. Remise en cause brique par brique

### B1 — Données & tracking de production (la question "coder son propre Kitsu")

**Options évaluées** (état de l'art vérifié juin 2026) :

| Option | Pour | Contre |
|---|---|---|
| Garder Kitsu | v1.0.0 vivant (plugins, budget, contact sheets), UI review mature | Modèle shot-centric figé ; aucun concept de génération/seed/coût ; tout le coût de sync D1/D6 reste |
| Adopter AYON (ynput) | Modèle Folder→Product→**Version→Representation** = le seul OSS qui mappe naturellement "génération→variante→fichier" ; GraphQL | Serveur lourd de plus ; Power Features (annotations, multi-view) **payantes même self-hosted** ; toujours pas de notion de job GPU/coût |
| **Tracker natif CF** ✅ | L'entité centrale du produit est le **Take** — aucun tracker existant ne la modélise ; le trou "Frame.io open source" n'existe pas (OpenRV = desktop, xStudio stagnant) donc la review web est à construire de toute façon ; suppression totale de la taxe de sync | On re-code review/annotations/permissions (coût assumé, périmètre réduit) |

**Décision proposée : tracker natif, modèle de données inspiré d'AYON, centré Take.**

```
Brand ─ Production (drop | film) ─ Sequence ─ Scene ─ Shot
                                                      └─ Take (n)   ← entité reine
Take = { model, provider, seed, params, prompt, lora_refs[],
         cost_eur, timing_ms{queue,load,infer}, parent_take_id,
         status, artifacts[] (Representation: 720p, 4K, proxy, audio stem) }
CastMember = { refs[], lora_id, voice_id, character_bible }
Script (versionné, beat sheet → scene cards → shot list)
Timeline (OTIO, première classe)
ReviewNote (frame-accurate, liée à Take)
CostLedger (agrégats par contenu/étape/provider — alimenté par PodPilot + Langfuse)
```

Kitsu : abandonné pour CF (les 3 fonctions utilisées — previews, comments, statuts — sont absorbées par Studio). **Plane : conservé** — c'est le PM principal de *tous* les projets (v1.3.1 en prod Sese, 6 conteneurs, vérifié 2026-06-10). CF ne le remplace pas, il **automatise sa mise à jour** : adapter dédié qui crée/maintient work items et cycles depuis les transitions Temporal (production créée, gate franchie, contenu publié). Plane reste l'agrégateur portefeuille ; le Postgres domaine (Take) reste la vérité du contenu — jamais l'inverse. NocoDB : remplacé par le Postgres du domaine.

### B2 — Orchestration (n8n → Temporal)

Pattern confirmé : **Temporal** est ce que Google utilise en prod pour Gemini/Veo (workflow workers CPU déterministes + activity workers GPU, retry/heartbeat/resume natifs, historique sur plusieurs jours). Exactement le besoin film 90 min.

- Le pipeline 14 étapes/4 gates devient **un workflow Temporal** ; les gates humaines = **signals** (envoyés par Telegram ou Studio) — la discipline éditoriale v1 est conservée, mais l'état devient inspectable et reprenable.
- Long-form : workflows hiérarchiques (film → scènes → shots → takes), `continue-as-new`, milliers d'activities GPU avec retry/resume.
- **n8n est relégué à la périphérie** : réponses sociales (ig-dm-reply), alertes, intégrations tierces. Plus jamais dans le chemin de rendu.
- Hébergement Temporal : pas sur Sese (8 GB saturé, 26 apps) — Hetzner prod-apps ou NAS cible (cf. architecture 3 tiers, audit 2026-05-29).

### B3 — Plan compute (PodPilot = le cerveau factuel)

Transposition directe des acquis fantrad :

| Acquis fantrad (mesuré) | Application CF |
|---|---|
| Volume réseau + image ~3 GB multi-arch (86;89;120) — jamais baker un gros modèle | Volumes : LTX-2 / Wan 2.2 / Flux + LoRAs cast (~15-25 GB → cold load ~20-30 s, parse-bound à ~850-900 MB/s) |
| FlashBoot ne restaure pas la VRAM ; cold = 56-284 s décomposé `{delay, load_wait, infer}` | Handler worker-comfy instrumenté à l'identique (`timing_ms`) → événements PodPilot `/v1/events` |
| Scale-to-zero + **trigger événementiel** bat le pre-warm sous ~1000 colds/j ($30-80/mois vs $518) | `/content` reçu → warm dummy pendant la rédaction LLM (30-60 s) → GPU chaud à l'étape génération |
| Resolver `(prix ASC, dispo DESC, dc)` + policies versionnées + failover | Policies `cf-image`, `cf-video-draft`, `cf-video-final`, `cf-train-lora` ; fallback tier fermé (Veo/Seedance éprouvés) |
| Pods éphémères `trap EXIT` (jamais d'orphelin facturé) | Jobs d'entraînement LoRA cast et bulk renders |
| Gate gratuit pré-deploy (`crane export` + ldd sur Pi) | CI worker-comfy |

**Innovation propre à CF** : étendre les retours factuels du coût/latence à la **qualité**. Chaque choix de take en review = un signal (take A préféré à B) → score Elo par `(provider, type_de_plan)` → pondère le resolver PodPilot. Le routage apprend le goût de l'utilisateur — ni Higgsfield ni personne ne fait ça (leur incitation est inverse : vendre des crédits d'itération).

**ComfyUI = plan de contrôle créatif, pas un simple worker** (correction post-vérification 2026-06-10). État réel sur Waza : ComfyUI v0.18.1 actif (`roles/comfyui/`, 4096M/3CPU) mais **CPU-only** (`--cpu --force-fp32`, PyTorch 2.7.1+cpu, vérifié via MCP), **zéro modèle local**, 7 custom nodes dont fal-API/Gemini — il orchestre déjà des APIs cloud aujourd'hui. Architecture cible : **ComfyUI Waza reste le hub** (authoring des workflows, file, presets, custom nodes) et dispatch les sous-graphes lourds vers :
1. les APIs cloud via les custom nodes existants (fal, Gemini/Veo, Seedance) — chemin actuel conservé ;
2. des **workers GPU RunPod éphémères demandés via PodPilot** — custom node "PodPilot Dispatch" (`resolve` → warm → execute → collect → terminate) ou ComfyUI-Distributed pointé sur des workers provisionnés par PodPilot. **Aucun pod permanent : le GPU n'existe que pendant la génération.**

Tiers résultants : Waza CPU = drafts/compositing léger gratuit ; RunPod via PodPilot = production open-weights ; APIs fermées = premium par plan.

### B4 — Ingestion & veille ("Scout") — brique aujourd'hui quasi inexistante

Existant (vérifié 2026-06-10) : MeTube 2026.03.21 (Waza:8081) + **VideoRef-Engine v0.2.0** (Waza:8082, 3072M/3CPU — service custom : extraction keyframes, optical flow, analyse couleur, OCR EasyOCR/Surya → **génère des workflows ComfyUI**, intégré Kitsu + Qdrant `videoref_styles` + LiteLLM + Gitea) + ig-dm/comment-reply (social). Correction de l'analyse initiale : **Scout n'est pas un greenfield, c'est l'évolution de VideoRef-Engine** — il lui manque la transcription (Whisper), la compréhension sémantique (VLM) et la sortie ContentDNA. La recherche de tendances (PRD étape 2) reste déléguée à WebSearch aujourd'hui.

Cible (stack mûre et confirmée juin 2026) :

```
Fetcher (abstraction)             Analyse                          Mémoire
├─ yt-dlp (maintenance PO-token,  ├─ faster-whisper large-v3-turbo ├─ Qdrant "trend-dna"
│  YouTube hostile : SABR)        ├─ PySceneDetect (cuts, pacing)  │  (hook, structure, pacing,
├─ instaloader (recherche only)   └─ Qwen3-VL 8B (self-host 24GB): │   sujets, CTA, embeddings)
└─ fallback payant (Apify ~$1.5/      hooks, cadrage, texte écran, └─ brand-voice (existant)
   1000 res) — prod Instagram         tonalité, "pourquoi ça marche"
```

- Sortie structurée : **ContentDNA** par référence (hook type, durée, cuts/s, arc, audio). Les briefs (étape 1-2) citent désormais des références factuelles analysées, plus du WebSearch vague.
- **Boucle fermée** : les analytics de NOS publications (IG insights, YouTube Analytics) sont ingérées au même format → le Director apprend ce qui marche pour *cette* audience, pas pour la moyenne d'Internet.
- Risque assumé : l'ingestion YouTube 2026 est fragile (SABR + PO tokens par vidéo) — d'où l'abstraction fetcher avec fallback managé payant, budgétée comme maintenance.

### B5 — Écriture & long-form ("Writer's Room")

La chaîne LLM v1 (5 appels, deepseek-v3 + gpt-4o-mini) suffit pour 30 s. Pour 90 min, le pattern validé par la recherche (MovieAgent, arXiv 2503.07314 ; FilmAgent 2501.12909) est **hiérarchique avec banque de personnages** :

1. Logline → beat sheet → scene cards → shot list (chaque niveau versionné, gates humaines aux niveaux hauts uniquement)
2. **Character bible** persistante (CastMember) : traits, voix, refs visuelles — injectée dans chaque génération de scène
3. **Continuity ledger** : refs canoniques par entité (character sheets, plaques décor, props) ; toute génération de shot reçoit les refs de continuité via VACE/Phantom
4. **QC continuité par VLM** : Qwen3-VL compare les shots adjacents (costume, décor, éclairage, raccords) et lève des alertes — un *script supervisor* automatique. Personne ne vend ça en produit.

Réalisme : aucun produit au monde ne fait du 90 min auto (plafond public ~16 min, Fable Showrunner). La cible crédible : 90 min **assisté** — l'humain garde les gates aux niveaux narratifs, la machine produit/raccorde les shots. Pilote recommandé : un épisode de 5 min avant toute ambition de long métrage.

### B6 — Génération ("Forge")

| Besoin | Open par défaut (self-host) | Tier premium (API, par plan) |
|---|---|---|
| Image / keyframes | Flux + SDXL (ComfyUI) — keyframes obligatoires (REX : jamais skip imagegen) | Seedream 4.5 (éprouvé) |
| Vidéo | **LTX-2** (open-weights jan 2026 : 4K 50 fps, **audio+vidéo synchrones en une passe**, <20 s/plan) + **Wan 2.2** A14B (photoréalisme, LoRA natif) | Veo 3.x, Seedance (éprouvés REX) ; Kling/Minimax via fal (câblés, à bencher) |
| Personnages cohérents | LoRA Wan 2.2 (20-50 images, qqs h/GPU — pods éphémères) + **VACE**/Phantom (reference-to-video) | Higgsfield Soul équivalent → notre Cast est versionné et possédé |
| Voix | **VibeVoice** (90 min, 4 speakers — taillé long-form) ; Chatterbox (cloning) ; Kokoro (presets rapides) | ElevenLabs v3 (audio tags, Text-to-Dialogue) |
| Musique / SFX | **ACE-Step 1.5** (MIT, 10 min, <10 s sur 3090, entraîné licencié — important vu les procès Suno/Udio en cours) ; Stable Audio Open (SFX) | — |
| Lipsync | LatentSync (qualité) / InfiniteTalk (dubbing) ; LTX-2 natif | — |

Le choix open-first résout au passage le REX voiceover (Kokoro timeout ARM64) : l'audio LTX-2 natif + TTS pré-généré **async dès le lock-script**, jamais dans le chemin critique du montage.

### B7 — Assemblage & review ("Cutting Room")

- **OTIO comme format pivot** (v0.18.1, adapters Premiere/Resolve/Avid — export pro possible). La Timeline est une entité de domaine, pas un JSON jetable.
- Reels : Remotion garde le motion design/captions/branding (ses forces) — mais sur worker x86, plus sur le Pi (720p cap, OOM Chromium = REX).
- Long-form : **conform ffmpeg piloté par OTIO** (concat, transitions, mix stems) — Remotion frame-par-frame sur 90 min n'est pas viable.
- **Review web frame-accurate** intégrée à Studio (player + ReviewNotes + comparaison de takes côte à côte) — c'est la pièce qu'on re-code faute d'équivalent OSS de Frame.io, et c'est elle qui génère les signaux qualité de B3.

### B8 — Publication & analytics ("Broadcast")

- **Postiz self-hosted** (AGPL, 31,7k★, releases hebdo) comme couche connecteurs : évite de porter soi-même App Review Meta (2-4 sem), audit TikTok (sinon posts privés SELF_ONLY) et quotas YouTube. À noter : YouTube débloqué depuis déc 2025 (~100 uploads/jour au quota gratuit).
- Déclinaison multi-format avant push (reel 9:16 / story / carousel / Shorts) = recompositions Remotion paramétrées.
- Analytics post-publication réingérées par Scout (B4) → boucle fermée.

---

## 4. UX cible — deux modes, un seul état

**Le constat Higgsfield** : sa force = presets one-click + agrégation modèles + vitesse. Sa faiblesse n°1 (Trustpilot 3,7/5) = **anxiété crédits** (pas de rollover, 3-5 itérations/clip facturées, coûts opaques, censure rétroactive). Un self-hosted gagne en rendant l'itération *psychologiquement gratuite* et le coût *radicalement transparent*.

### Mode Studio (web, desktop) — l'instrument
- **Arbre de production** à gauche (Production→Scene→Shot), **storyboard/canvas** au centre, **tiroir de takes** par shot : grille de comparaison, re-roll 1-clic, seed lock, choix provider avec **estimation € live** (PodPilot)
- **Comparaison multi-modèles côte à côte** (même plan sur Wan 2.2 + LTX-2 + Veo) — économiquement impossible pour Higgsfield, trivial à coût marginal GPU
- **Catalogue de presets** ("apps" à la Higgsfield) : chaque workflow ComfyUI/Remotion versionné = une carte avec 2-4 champs (pattern ViewComfy : workflow JSON → web-app). Démarrage : 10-15 presets
- Onglet **Timeline** (OTIO), mode **Review** (commentaires frame-accurate, approve/retake)
- **Cost ledger permanent** : coût réel du contenu en cours (LLM + GPU + APIs), par étape, par take — l'anti-crédits assumé
- File temps réel : position, ETA, worker (chaud/froid), provenance des latences

### Mode Factory (Telegram) — la télécommande
- Le flux 14 étapes/4 gates actuel **conservé** (c'est une bonne UX d'astreinte mobile) mais rebranché sur les signals Temporal
- Notifications riches : preview inline + boutons ok/retake/adjust ; `/adjust` devient **scène-local** (matrice d'invalidation au niveau take, plus de re-gen complète)
- Mode batch : `/drop 5` → 5 contenus en parallèle (le GPU élastique le permet enfin)

### Mode War Room (long-form)
- Burn-down de shots par scène, projection coût vs budget film, alertes continuité (QC VLM), heatmap des scènes en retake

---

## 5. Le pari 30 s → 90 min : ce qui change, ce qui ne change pas

| Dimension | Reel 30 s | Film 90 min | Conséquence d'architecture |
|---|---|---|---|
| Hiérarchie | 1 scène, ~8 shots | ~90 scènes, ~1500 shots | Mêmes entités, récursion plus profonde — le modèle Take/Shot/Scene est invariant |
| Écriture | 1 passe LLM | Beat sheet → scene cards → shot list + bible | Writer's Room hiérarchique (B5) |
| Cohérence | Prompt anchoring (REX) | Cast LoRA + VACE + continuity ledger + QC VLM | CastMember première classe |
| Orchestration | minutes | jours, milliers de jobs | Temporal obligatoire (D3) |
| Assemblage | Remotion | OTIO + ffmpeg conform | Timeline première classe |
| Review | 1 vidéo | par scène, par bobine | Review web + playlists |
| Coût | ~1-3 € | ~150-800 € (estimation à valider au pilote) | Cost ledger + budget caps par production |

**Le même produit sert les deux** si et seulement si les invariants (Take, Timeline, Cast, workflow durable, ledger) sont posés dès M0. C'est tout l'enjeu de la refonte.

---

## 6. Différenciateurs (ce que personne ne fait en juin 2026)

1. **Routage GPU appris par les retours factuels** : PodPilot (coût/latence/dispo mesurés) × signaux qualité de la review (Elo provider/type de plan) → le système choisit le modèle comme un directeur de production qui connaît ses équipes
2. **Script supervisor automatique** : QC continuité inter-shots par VLM
3. **Transparence radicale des coûts** : € réel par take, par étape, par contenu — l'inverse exact du modèle crédits
4. **Boucle fermée tendances→performance** : ContentDNA des références ET de nos propres publications
5. **Comparaison multi-modèles systématique** à coût marginal
6. **Cast possédé** : personnages = LoRA + voix + bible versionnés, réutilisables sur tous les formats, exportables — aucun lock-in
7. **Double échelle native** 30 s/90 min sur les mêmes primitives

---

## 7. Roadmap proposée (vagues, sans dates fermes)

| Vague | Contenu | Critère de sortie |
|---|---|---|
| **M0 — Colonne vertébrale** | Repo `~/work/saas/content-factory` (doctrine MANIFESTE) ; schéma domain (Take-centric) ; Temporal + workflow 14 étapes (strangler : n8n appelle la nouvelle API) ; import données CF v1 | Un contenu v1 complet tourne sur Temporal, état inspectable, zéro Kitsu/NocoDB dans le chemin |
| **M1 — GPU élastique** | worker-comfy RunPod (pattern fantrad) + volumes LTX-2/Wan 2.2 + policies PodPilot + warm événementiel ; Langfuse | Étape génération : 20-30 min → 2-4 min, 1080p+, coût/take dans le ledger |
| **M2 — Studio** | Web UI : galerie, takes, re-roll, comparaison multi-modèles, presets (10-15), review frame-accurate, cost ledger | Boucle brief→vidéo sans toucher Telegram ni Kitsu ; signaux qualité alimentent le resolver |
| **M3 — Boucle fermée** | Scout (fetcher+whisper+scenedetect+Qwen3-VL) ; Postiz + multi-format ; analytics réingérées | Brief généré avec références factuelles ; publication 1-clic ; perfs visibles dans Studio |
| **M4 — Long-form** | Writer's Room hiérarchique ; Cast LoRA pipeline ; OTIO conform ; QC continuité ; War Room | **Pilote : épisode 5 min** cohérent (cast, décors, audio) sous budget défini |

Coût de croisière estimé M1-M3 : **$30-120/mois GPU** (scale-to-zero + warm événementiel, réf. fantrad) + APIs fermées à la demande + maintenance ingestion.

## 8. Risques & points à re-vérifier

| Risque | Mitigation |
|---|---|
| Ingestion YouTube (SABR, PO tokens) fragile | Abstraction fetcher + fallback Apify budgété ; ne jamais en faire un chemin critique |
| Temporal = un système de plus à opérer | Hors Sese (Hetzner/NAS) ; docker-compose officiel ; c'est le prix du long-form — alternative assumée si refus : queue Postgres `SKIP LOCKED` en M0 puis migration |
| PodPilot pré-prod (8 items P0 hardening) | Prérequis M1, plan déjà écrit (`podpilot/docs/.../2026-06-08-hardening-plan.md`) |
| Review web = développement UI conséquent | Périmètre minimal M2 (player + notes + compare), pas un Frame.io complet |
| HunyuanVideo licence Tencent (restrictions UE) | Écarté du tier par défaut ; LTX-2/Wan 2.2 suffisent |
| Plafond exact publication IG API (25/50/100 par 24 h — sources divergentes) | Vérifier developers.facebook.com avant design Broadcast ; Postiz absorbe |
| 90 min full-auto n'existe nulle part | Objectif = assisté, pilote 5 min M4 ; ne pas vendre le film auto |

## 9. Annexe — Vérification des configurations réelles (2026-06-10)

Vérification post-rédaction (MCP comfyui-studio live + lecture directe `inventory/group_vars/all/versions.yml`, `roles/*/defaults/main.yml`, playbooks) — corrige les hypothèses de la première version de ce document :

| Composant | Où | Version | État réel vérifié | Impact sur l'analyse |
|---|---|---|---|---|
| ComfyUI | Waza | v0.18.1 | **CPU-only** (`--cpu --force-fp32`, PyTorch 2.7.1+cpu — vérifié MCP live), 4096M/3CPU, **zéro modèle local**, 7 custom nodes (fal-API, fal-Connector, IPAdapter+, AnimateDiff, Impact, InstantID, controlnet_aux), 1 seul workflow sauvegardé (`cli-demo-test.json`) | **Hub d'orchestration cloud déjà en place** — B3 corrigé : ComfyUI = plan de contrôle, GPU à la demande via PodPilot |
| comfyui-studio MCP + comfyui-cli | Waza | — | `roles/comfyui/files/comfyui-studio/mcp_server.py` + `comfyui-cli/montage*.py` : assemblage de workflows ComfyUI depuis templates Jinja2 (`montage_build`/`montage_render`) | **Base existante pour les presets (U1) et le Cutting Room** — pas un greenfield |
| Remotion | Waza | 4.0.437 | port 3200, 8G/2CPU, compositions au runtime | Conforme |
| **VideoRef-Engine** | Waza | v0.2.0 | port 8082, 3072M/3CPU — keyframes + optical flow + couleur + OCR (EasyOCR/Surya) → workflows ComfyUI ; intégré Kitsu, Qdrant `videoref_styles`, LiteLLM, Gitea ; watch le dossier MeTube | **Oublié de la v1 de cette analyse** — Scout (B4) = son évolution |
| MeTube | Waza | 2026.03.21 | port 8081, cookies yt-dlp optionnels (désactivés) | Conforme |
| Plane | Sese | v1.3.1 | 6 conteneurs actifs, MinIO 2024-11-07 (post-fix), IDs NocoDB liés en group_vars | **B1 corrigé : conservé, PM principal multi-projets** |
| NocoDB | Sese | 2026.05.1 | base CF `pwb0jn4ncdsz460`, 3 tables | Conforme (remplacé par Postgres domaine en v2) |
| Qdrant | Sese | v1.18.1 | **5 collections** : semantic_cache, content_index, comfyui-docs, videoref_styles, ideas | Plus riche qu'estimé (pas seulement brand-voice) |
| LiteLLM | Sese | 1.83.3 | Seedream conditionné à `openrouter_api_key`, Gemini à `google_gemini_api_key` ; **Seedance N'EST PAS routé LiteLLM** (accès direct fal via custom node ComfyUI) ; pas de modèle `veo3` nommé | Routage vidéo réel = ComfyUI custom nodes, pas LiteLLM |
| OpenClaw | Sese | 2026.5.27 | **20 skills** dont content-director, studio-produce, video-remix, swarm-coordinator | Assets réutilisables en v2 |
| Kokoro TTS | — | — | **Jamais déployé en rôle** (le REX 2026-03-22 = test ponctuel) | Confirme le choix LTX-2 audio natif + TTS async |
| Postiz / Stitch / Canva MCP | — | — | **Inexistants** (planifiés, zéro déploiement) | À créer en M3 |
| NAS Tier 3 (P6X58D-E) | — | — | Planifié : Xeon X58 CPU-only + ZFS — **pas de GPU** ; fallback LLM GGUF + backups restic | Pas de tier génération locale possible — RunPod reste le seul GPU |
| Grafana | Sese | 12.4.3 | dashboards `litellm_spend_*` présents, **0 alerte Telegram branchée** ; Phase 10 obs = 0 déployé | Confirme C1/C4 |
| Backups | Sese | — | PG dumps cassés mars-mai, drill jamais fait (audit : 4/10) | Risque transverse, hors périmètre CF mais bloquant prod |

## 10. Décisions à trancher (gate humain)

1. **Tracker natif** (recommandé) vs AYON vs Kitsu conservé — engage tout M0
2. **Temporal** vs queue Postgres simple en M0 (Temporal recommandé si M4 long-form est sérieux)
3. Kitsu : extinction pour CF ? — **Plane tranché (2026-06-10) : conservé comme PM principal, mise à jour automatisée par adapter, Take ajouté côté contenu**
4. Nom et création du repo (`content-factory` ? appliquer MANIFESTE-CREATION-PROJET.md : wing `saas`, déclaration Qdrant)
5. Hébergement Temporal + workers render (Hetzner prod-apps vs NAS cible)
6. Budget mensuel GPU cible (gouverne les policies PodPilot)
