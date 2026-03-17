# PRD — Content Factory : Pipeline de Creation de Contenu Automatise

> **Statut** : Design valide — En attente d'implementation
> **Date** : 2026-03-17
> **Auteur** : mobuone + Claude Code
> **Premier projet** : Lancement Paul Taff (Flash Studio — plateforme IaaS, agents IA ton decale)

---

## 1. Vision

Un workflow de creation de contenu pour les reseaux sociaux et spots publicitaires,
pilote par Telegram (via OpenClaw) et suivi visuellement dans Kitsu.

Le systeme est **multi-projet** (brand profiles dans NocoDB) mais le premier cas d'usage
est la production de **videos virales pour le lancement de Paul Taff** sur Instagram.

### Objectifs

- Produire du contenu de qualite studio avec un workflow professionnel (14 etapes, 4 gates)
- Piloter depuis Telegram (commandes rapides) ET Kitsu (vue globale, annotations visuelles)
- Supporter les allers-retours creatifs sans tout casser (invalidation ciblee par scene)
- Passer progressivement de l'assiste au full autonome

### Cadence cible

- **Lancement** : drops de 5-10 contenus d'un coup
- **Regime de croisiere** : 3-5 contenus/semaine
- **Formats** : mix (memes/skits, motion design, IA generative, talking head + overlay)

---

## 2. Architecture Globale

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INTERFACES HUMAINES                          │
│                                                                     │
│   Telegram (mobile/rapide)          Kitsu (vue globale/review)      │
│   /content, /ok, /adjust, /back     Pipeline visuel, annotations    │
│   /preview, /impact, /drop          Previews, versioning, gates     │
└────────────┬───────────────────────────────┬────────────────────────┘
             │                               │
             ▼                               ▼
┌─────────────────────┐          ┌─────────────────────────┐
│  OpenClaw            │          │  Kitsu + Zou             │
│  (Sese-AI)           │◀────────▶│  (Sese-AI)               │
│                      │  API Zou │                           │
│  Skill:              │          │  - Projets/shots          │
│  content-director    │          │  - Taches (14 etapes)     │
│  + generate-visual   │          │  - Previews + annotations │
│  + video-composition │          │  - Gates de validation    │
└──────────┬───────────┘          └───────────┬───────────────┘
           │                                  │ webhooks
           ▼                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                        n8n (Sese-AI)                              │
│                     Orchestrateur central                         │
│                                                                   │
│  Workflows :                                                      │
│  - brief-to-concept     (etapes 1-5)                              │
│  - script-to-storyboard (etapes 6-8)                              │
│  - generate-assets      (etapes 9-11)                             │
│  - review-and-publish   (etapes 12-14)                            │
│  - kitsu-sync           (upload previews, maj statuts)            │
│  - invalidation-engine  (cascade d'invalidation ciblee)           │
└───────┬──────────┬──────────┬──────────┬──────────┬──────────────┘
        │          │          │          │          │
        ▼          ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│ ComfyUI  │ │ Remotion │ │ Fal.ai │ │Seedance│ │ Seedream │
│ (Waza)   │ │ (Waza)   │ │ (cloud)│ │ (cloud)│ │ (cloud)  │
│ images   │ │ motion   │ │ Kling  │ │ video  │ │ images   │
│ locales  │ │ design   │ │Minimax │ │ IA     │ │ cloud    │
└──────────┘ └──────────┘ │HunyuanV│ └────────┘ └──────────┘
                          └────────┘
```

### Repartition des serveurs

| Serveur | Role dans le pipeline |
|---|---|
| **Sese-AI** (VPS 8GB) | Kitsu, n8n, OpenClaw, PostgreSQL, Qdrant, NocoDB, Caddy |
| **Waza** (RPi5 16GB) | ComfyUI (generation images), Remotion (render video), Claude Code |
| **Cloud** | Fal.ai, Seedance, Seedream, ElevenLabs (voiceover) |

### Principe cle

**Kitsu ne genere rien.** C'est le tableau d'affichage. n8n orchestre, OpenClaw raisonne,
les providers produisent. Kitsu affiche les resultats et recueille le feedback humain.

---

## 3. Stockage des Donnees

### Double stockage : NocoDB + Qdrant

| Systeme | Role | Contenu |
|---|---|---|
| **NocoDB** | Source de verite (CRUD, statuts) | Scripts, brand profiles, calendrier editorial, metadata |
| **Qdrant** | Memoire creative (recherche semantique) | Embeddings des scripts valides, brand voice, references |

**Sync** : webhook n8n a chaque validation de script dans NocoDB → embed via LiteLLM → upsert Qdrant.

L'agent OpenClaw consulte Qdrant pour :
- Retrouver des scripts similaires ("comme celui sur le sarcasme")
- Maintenir la coherence du ton entre les contenus
- S'inspirer des references indexees

### Tables NocoDB

**`brands`** — Profils de marque

| Champ | Type | Exemple |
|---|---|---|
| id | auto | 1 |
| name | text | Paul Taff |
| tagline | text | Des agents IA avec du caractere |
| tone | text | Decale, sarcastique, audacieux |
| palette | json | {"primary": "#FF6B35", "accent": "#2EC4B6"} |
| typography | text | Space Grotesk / Inter |
| target_audience | text | Dev/founders 25-40, early adopters |
| platforms | json | ["instagram"] |

**`contents`** — Projets de contenu (1 ligne = 1 contenu)

| Champ | Type |
|---|---|
| id | auto |
| brand_id | FK → brands |
| kitsu_project_id | text (ID Kitsu pour sync) |
| title | text |
| format | enum (reel, carousel, post, story, ad) |
| status | enum (brief → ... → published) |
| current_phase | int (1-4) |
| current_step | int (1-14) |
| brief | json |
| script | long text |
| storyboard | json (array de scenes) |
| assets_urls | json |
| final_url | text |
| published_at | datetime |
| instagram_id | text |
| created_at | datetime |

**`scenes`** — Decoupage scene par scene

| Champ | Type |
|---|---|
| id | auto |
| content_id | FK → contents |
| scene_number | int |
| description | text |
| dialogue | text |
| screen_text | text |
| duration_sec | float |
| transition | text |
| visual_type | enum (motion_design, ai_generative, stock, meme) |
| provider | enum (remotion, comfyui, fal_ai, seedance, seedream) |
| asset_url | text |
| version | int |
| status | enum (draft, validated, invalidated) |

---

## 4. Pipeline Creatif — 4 Phases, 14 Etapes

### Vue d'ensemble

```
 PHASE I ── PRE-PRODUCTION ──────────────────────────────
 │ 1. Brief creatif
 │ 2. Recherche & references
 │ 3. Moodboard
 │ 4. Concept & hook
 │ 5. Casting
 │
 ├── GATE 1 : /lock-preprod ─────────────────────────────
 │
 PHASE II ── ECRITURE ───────────────────────────────────
 │ 6. Script
 │ 7. Storyboard
 │ 8. Sound design (pre-plan)
 │
 ├── GATE 2 : /lock-script ──────────────────────────────
 │
 PHASE III ── PRODUCTION ────────────────────────────────
 │  9. Generation assets
 │ 10. Rough cut
 │
 ├── GATE 3 : /ok-rough ─────────────────────────────────
 │
 │ 11. Fine cut
 │
 PHASE IV ── POST-PRODUCTION & DISTRIBUTION ─────────────
 │ 12. Review final
 │ 13. Adaptation multi-format
 │ 14. Publication & archivage
 │
 └── GATE 4 : /published ────────────────────────────────
```

### Detail de chaque etape

#### PHASE I — PRE-PRODUCTION

**Etape 1 — Brief creatif**

Contenu du brief :
- Objectif (notoriete, conversion, engagement)
- Cible (persona, demographie)
- Plateforme (Instagram Reel, Story, Post, Carousel)
- Format et duree cible
- Message cle a transmettre
- Contraintes (budget providers, deadline)
- KPI attendus (vues, engagement rate, partages)
- Livrables attendus (nombre de formats/declinaisons)

Qui le fait : toi via Telegram (`/content reel teaser Paul Taff — ...`) ou OpenClaw propose.
Kitsu : tache "Brief" passe en "todo" → "wip" → "done".

**Etape 2 — Recherche & references**

- Tendances actuelles sur la plateforme cible
- Contenus concurrents/inspirants (URLs, screenshots)
- Hooks viraux qui marchent dans la niche
- Sons/musiques tendance

Qui le fait : OpenClaw (skill `search-content` + web search).
Stockage : references indexees dans Qdrant pour reutilisation.
Kitsu : upload des screenshots de reference comme preview.

**Etape 3 — Moodboard**

- Direction artistique : palette couleurs, typographie
- Ambiance visuelle : 4-8 images de reference (generees ou trouvees)
- Ambiance sonore : style de musique, tempo, energie
- Exemples de transitions/effets

Qui le fait : OpenClaw genere des visuels de reference via ComfyUI ou Fal.ai.
Kitsu : moodboard uploade comme preview, annotations pour feedback.

**Etape 4 — Concept & hook**

- Angle creatif : l'idee centrale du contenu
- **Hook** (les 3 premieres secondes) : livrable explicite, texte exact ou description visuelle
- Message cle : ce que le spectateur retient
- CTA (call to action) : ce qu'on veut qu'il fasse

Pourquoi le hook est un livrable : 80% de la retention se joue dans les 3 premieres secondes.
Kitsu : concept redige comme commentaire, hook mis en evidence.

**Etape 5 — Casting**

- Personnages/voix : caractere, ton, role dans le contenu
- Style visuel de chaque personnage (avatar IA, illustration, texte)
- Voix off : choix du provider et de la voix (ElevenLabs voice ID, Fal.ai TTS)
- Preview voix : sample audio genere pour validation

Kitsu : samples audio uploades comme previews.

```
── GATE 1 : /lock-preprod ──
Validation : toutes les etapes 1-5 en statut "done" dans Kitsu.
Effet : les etapes 1-5 passent en lecture seule.
Deverrouillage : /unlock-preprod (explicite, montre l'impact cascade).
```

#### PHASE II — ECRITURE

**Etape 6 — Script**

Structure narrative obligatoire :
- **Hook** (0-3s) : accroche visuelle + textuelle
- **Tension** (3-15s) : probleme, curiosite, escalade
- **Resolution** (15-45s) : demonstration, punchline, valeur
- **CTA** (45-60s) : action demandee

Livrables distincts :
- Narration / voix off (texte exact avec timings)
- Dialogues par personnage (avec indications de ton)
- Textes ecran (supers, captions, lower thirds — texte exact + timing)

Kitsu : script uploade, versionne a chaque modification.

**Etape 7 — Storyboard**

Plan par plan, chaque scene contient :

| Champ | Description |
|---|---|
| scene_number | Numero sequentiel |
| description | Description visuelle (cadrage, action, decor) |
| dialogue | Replique du personnage (si applicable) |
| narration | Texte voix off (si applicable) |
| screen_text | Texte affiche a l'ecran |
| duration_sec | Duree en secondes |
| transition | Coupe franche, fondu, zoom, swipe... |
| visual_type | motion_design / ai_generative / stock / meme |
| provider | remotion / comfyui / fal_ai / seedance / seedream |
| audio | Description de l'audio (musique, SFX) |

Kitsu : chaque scene = une sous-tache avec sa propre preview (croquis ou image placeholder).

**Etape 8 — Sound design (pre-plan)**

- Musique : style, BPM, moments cles (drop au hook, calme sur la resolution)
- SFX : sons par scene (whoosh sur les transitions, ding sur le CTA)
- Voiceover : timings cales sur le storyboard, pauses, emphases
- Source : stock libre (Pixabay, Freesound) ou generation IA

```
── GATE 2 : /lock-script ──
Validation : etapes 6-8 en statut "done".
Effet : script et storyboard verrouilles.
Le nombre de scenes et leur structure sont fixes.
Les providers par scene sont confirmes.
```

#### PHASE III — PRODUCTION

**Etape 9 — Generation assets**

Pour chaque scene du storyboard, selon le provider assigne :

| Provider | Localisation | Usage | Cout |
|---|---|---|---|
| ComfyUI | Waza (local) | Images, backgrounds, textures | Gratuit |
| Remotion | Waza (local) | Motion design, typo animee, templates | Gratuit |
| Fal.ai | Cloud | Kling (video), Minimax, Hunyuan Video | Variable |
| Seedance | Cloud (BytePlus) | Video IA cinematique | ~$0.10-0.80/min |
| Seedream | Cloud (LiteLLM) | Images haute qualite | ~$0.04/image |
| ElevenLabs | Cloud | Voiceover | ~$0.30/1000 chars |

Workflow n8n : parcourt les scenes, dispatch vers le bon provider, collecte les resultats.
Kitsu : chaque asset genere est uploade comme preview de la scene correspondante.

**Etape 10 — Rough cut (premier montage)**

- Assemblage sequentiel des scenes dans Remotion
- Calage voix off + musique (timing approximatif)
- Pas de transitions fines, pas de color grading
- Export basse qualite pour review rapide

Kitsu : video rough cut uploadee comme preview du shot principal.
Telegram : notification avec lien direct vers la preview.

```
── GATE 3 : /ok-rough ──
Validation : le rough cut est globalement bon.
Effet : la structure du montage est fixee.
Les ajustements restants sont cosmetiques (transitions, couleurs, timing fin).
```

**Etape 11 — Fine cut (montage affine)**

- Transitions fluides entre scenes
- Color grading / direction artistique
- Captions et textes animes (timing precis)
- SFX integres aux bons moments
- Musique mixee avec la voix off
- Export haute qualite

#### PHASE IV — POST-PRODUCTION & DISTRIBUTION

**Etape 12 — Review final**

- Export haute qualite → preview Telegram + Kitsu
- Boucle d'ajustements fins (max 3 iterations)
- Chaque iteration : feedback annote dans Kitsu → correction → nouvelle preview
- Validation finale : `/ok-final`

**Etape 13 — Adaptation multi-format**

A partir du contenu valide, decliner automatiquement :

| Format | Ratio | Duree | Usage |
|---|---|---|---|
| Reel Instagram | 9:16 | 15-60s | Feed + Explore |
| Story Instagram | 9:16 | 15s segments | Stories (ephemere) |
| Post carrousel | 1:1 | N/A (frames cles) | Feed |
| YouTube Shorts | 9:16 | 15-60s | YouTube |
| Version Ad | 9:16 ou 1:1 | 15s / 30s | Meta Ads (futur) |

Chaque format = une composition Remotion avec les memes assets mais recadres/retimes.
Kitsu : chaque format = un output file attache au shot.

**Etape 14 — Publication & archivage**

Phase 1 (manuelle) :
- Export des fichiers finaux → lien de telechargement Telegram
- Caption + hashtags generes par OpenClaw
- Publication manuelle sur Instagram

Phase 2+ (automatique, futur) :
- Publication via Instagram Graph API
- Scheduling via NocoDB (calendrier editorial)

Archivage :
- NocoDB : metadata complete (urls, dates, metriques futures)
- Qdrant : embedding du script + metadata pour memoire creative
- Kitsu : projet archive avec toutes les previews

```
── GATE 4 : /published ──
Le contenu est en ligne. Le projet est archive.
Les metriques de performance alimenteront les futurs briefs (feedback loop, Phase 3 du projet).
```

---

## 5. Mecanique de Retour en Arriere

### Principe : invalidation ciblee, pas reconstruction totale

Quand tu modifies une etape deja validee, seuls les elements **dependants** sont invalides.

### Matrice d'impact

```
Modification de...    │ Ce qui est invalide
───────────────────────┼──────────────────────────────────────
Brief (1)              │ TOUT — mais l'agent propose ce qui peut etre conserve
Moodboard (3)          │ Concept → Script → Decoupage → Assets → Montage
Concept/Hook (4)       │ Script → Decoupage → Assets → Montage
Casting (5)            │ Script (dialogues) → Decoupage → Assets (scenes avec persos)
Script (6)             │ Decoupage → Assets → Montage
1 scene du storyboard  │ Uniquement l'asset + portion du montage de cette scene
Sound design (8)       │ Musique/SFX dans le montage uniquement
```

### Regles de gates

| Action | Intra-phase | Cross-phase |
|---|---|---|
| Modifier une etape | Libre, pas besoin de gate | Necessite `/unlock-<phase>` |
| Invalider une scene | Auto — seul l'asset de cette scene est marque | Idem si la scene change le script |
| Revenir au brief | `/unlock-preprod` — montre l'impact complet | L'agent propose un plan de conservation |

### Conversation Telegram type

```
Toi    : /adjust casting — le CEO doit etre plus sarcastique
Agent  : Persona CEO mis a jour (v3).
         Impact :
         - Script : repliques CEO scenes 2, 5, 7 → a reecrire
         - Storyboard : scenes 2, 5, 7 dialogues a mettre a jour
         - Assets : scene 2 deja generee → a refaire
         - Scenes 1, 3, 4, 6 : pas impactees ✓

         Je reecris les repliques du CEO ? /go ou /adjust
Toi    : /go
Agent  : [reecrit scenes 2, 5, 7 — uploade nouvelles versions dans Kitsu]
         Script v4 uploade. Scenes 2, 5, 7 mises a jour.
         Preview storyboard : [lien Kitsu]
```

---

## 6. Mapping Kitsu

### Modele Kitsu adapte au pipeline

Kitsu est concu pour l'animation/VFX. Voici comment on mappe notre pipeline :

| Concept Kitsu | Notre usage |
|---|---|
| **Production** | Un projet de marque (ex: "Paul Taff — Lancement") |
| **Episode** | Un drop ou une campagne |
| **Sequence** | Une des 4 phases (Pre-prod, Ecriture, Production, Post-prod) |
| **Shot** | Un contenu individuel (1 reel, 1 carrousel, etc.) |
| **Task** | Une etape du pipeline (1 a 14) |
| **Task Status** | todo → wip → retake → done |
| **Preview** | Image/video/audio uploadee a chaque etape |
| **Comment** | Feedback annote sur une preview |

### Statuts personnalises

| Statut Kitsu | Signification |
|---|---|
| `todo` | Etape pas encore commencee |
| `wip` | En cours de generation/ecriture |
| `pending_review` | En attente de validation humaine |
| `retake` | Feedback donne, a reprendre |
| `done` | Valide |
| `locked` | Gate passee, en lecture seule |
| `invalidated` | Invalide par une modification en amont |

### Webhooks Kitsu → n8n

| Evenement Kitsu | Action n8n |
|---|---|
| Task status → `done` | Verifie si toutes les taches de la gate sont done → propose le lock |
| Task status → `retake` | Notifie OpenClaw du feedback → relance la generation |
| Comment created | Extrait le texte → envoie a OpenClaw pour interpretation |
| Preview uploaded | Notifie Telegram avec lien de preview |

---

## 7. Commandes Telegram

### Commandes de pilotage

| Commande | Description |
|---|---|
| `/content <format> <brief>` | Cree un nouveau contenu (lance etape 1) |
| `/ok` | Valide l'etape courante, passe a la suivante |
| `/adjust <instruction>` | Modifie l'etape courante (nouvelle version) |
| `/back <etape>` | Retourne a une etape anterieure |
| `/go` | Confirme une action proposee par l'agent |
| `/preview` | Affiche l'etat global du projet en cours |
| `/impact` | Montre ce qui serait invalide si tu changes l'etape courante |
| `/drop` | Abandonne le projet en cours |

### Commandes de gates

| Commande | Description |
|---|---|
| `/lock-preprod` | Verrouille la pre-production (gate 1) |
| `/lock-script` | Verrouille l'ecriture (gate 2) |
| `/ok-rough` | Valide le rough cut (gate 3) |
| `/ok-final` | Valide le rendu final |
| `/published` | Marque comme publie (gate 4) |
| `/unlock-<phase>` | Deverrouille une phase (montre l'impact d'abord) |

### Commandes de calendrier

| Commande | Description |
|---|---|
| `/calendar` | Affiche le calendrier editorial de la semaine |
| `/drop <nombre>` | Prepare un drop de N contenus |
| `/brands` | Liste les profils de marque disponibles |

---

## 8. Compositions Remotion a Creer

4 compositions prioritaires pour Instagram :

| Composition | Format | Usage |
|---|---|---|
| `reel-motion-text` | 9:16, 15-60s | Texte anime dynamique, transitions, fond gradie ou image |
| `reel-meme-skit` | 9:16, 15-30s | Format meme/skit — texte + image/video + reactions |
| `reel-feature-showcase` | 9:16, 30-60s | Demo produit — screen capture + overlays + voix off |
| `reel-teaser` | 9:16, 15s | Teaser court — hook fort, mystere, CTA |
| `carousel-slides` | 1:1, N slides | Slides individuelles pour carrousel Instagram |
| `story-segment` | 9:16, 15s | Segment Story avec CTA swipe up |

Chaque composition accepte en props :
- `scenes[]` : array de scenes du storyboard
- `brand` : profil de marque (couleurs, typo, logo)
- `audio` : URL du fichier audio (voix off + musique)

---

## 9. Providers et Couts

### Providers images

| Provider | Localisation | Modele | Cout | Usage |
|---|---|---|---|---|
| ComfyUI | Waza (local) | SDXL / custom | Gratuit | Backgrounds, textures, mockups |
| Seedream 4.5 | Cloud (LiteLLM) | Seedream | ~$0.04/img | Images haute qualite |
| Fal.ai | Cloud | Flux, SDXL | Variable | Styles specifiques, modeles specialises |

### Providers video

| Provider | Localisation | Modele | Cout | Usage |
|---|---|---|---|---|
| Remotion | Waza (local) | Compositions React | Gratuit | Motion design, templates, montage |
| Seedance 2.0 | Cloud (BytePlus) | Seedance | ~$0.10-0.80/min | Video IA cinematique |
| Fal.ai | Cloud | Kling, Minimax, Hunyuan | Variable | Video IA (alternatives) |
| Veo 3 Fast | Cloud (Google) | Veo | ~$0.15/sec | Fallback scenes realistes |

### Providers audio

| Provider | Usage | Cout |
|---|---|---|
| ElevenLabs | Voiceover haute qualite | ~$0.30/1000 chars |
| Fal.ai TTS | Voiceover alternative | Variable |
| Stock libre | Musique, SFX (Pixabay, Freesound) | Gratuit |

### Budget estime par contenu

| Type de contenu | Cout estime |
|---|---|
| Reel motion design (local only) | ~$0.10 (LLM pour le script) |
| Reel avec scenes IA generees | ~$0.50-2.00 |
| Reel full IA (Seedance + voiceover) | ~$2.00-5.00 |
| Carrousel (images only) | ~$0.20-0.50 |

---

## 10. Phases d'Implementation

### Phase 1 — Fondations (semaine 1-2)

- [ ] Deployer Kitsu + Zou sur Sese-AI (role Ansible `kitsu`)
- [ ] Ajouter Fal.ai comme provider dans n8n
- [ ] Creer les tables NocoDB (`brands`, `contents`, `scenes`)
- [ ] Configurer la collection Qdrant `brand-voice`
- [ ] Creer le skill OpenClaw `content-director`
- [ ] Commandes Telegram de base (`/content`, `/ok`, `/adjust`, `/back`, `/preview`)
- [ ] Workflow n8n `brief-to-concept` (etapes 1-5)
- [ ] Workflow n8n `kitsu-sync` (upload previews, maj statuts)

### Phase 2 — Production (semaine 3-4)

- [ ] 4 compositions Remotion Instagram (motion-text, meme, feature-showcase, teaser)
- [ ] Workflow n8n `script-to-storyboard` (etapes 6-8)
- [ ] Workflow n8n `generate-assets` (dispatch multi-provider par scene)
- [ ] Workflow n8n `rough-cut` (assemblage Remotion)
- [ ] Mecanique d'invalidation ciblee (par scene)
- [ ] Gates dans Kitsu (statuts personnalises + webhooks)

### Phase 3 — Autonomie (semaine 5+)

- [ ] Calendrier editorial auto-genere (l'agent propose les contenus de la semaine)
- [ ] Publication automatique Instagram (Graph API)
- [ ] Adaptation multi-format automatique (etape 13)
- [ ] Feedback loop : metriques Instagram → ajustement du style
- [ ] Skill `publish-content` pour OpenClaw
- [ ] Format Ad (declinaison organique → Meta Ads)

---

## 11. Dependances Techniques

### Services existants requis

- [x] OpenClaw (Sese-AI) — agents IA + Telegram bot
- [x] n8n (Sese-AI) — orchestration workflows
- [x] NocoDB (Sese-AI) — base de donnees structuree
- [x] Qdrant (Sese-AI) — recherche semantique
- [x] ComfyUI (Waza) — generation images locale
- [x] Remotion (Waza) — render video local
- [x] LiteLLM (Sese-AI) — proxy IA multi-provider
- [x] Caddy (Sese-AI) — reverse proxy + TLS + VPN ACL
- [x] PostgreSQL (Sese-AI) — base de donnees

### Nouveaux composants a deployer

- [ ] **Kitsu + Zou** (Sese-AI) — production tracking, ~500MB RAM
- [ ] **Fal.ai integration** — cle API dans secrets.yml, workflows n8n
- [ ] **ElevenLabs integration** — cle API dans secrets.yml (voiceover)
- [ ] **Compositions Remotion** — 4-6 templates Instagram sur Waza
- [ ] **Skill OpenClaw `content-director`** — nouveau skill a creer
- [ ] **Collection Qdrant `brand-voice`** — schema + pipeline d'indexation

### Acces reseau

```
Waza (local) ←──Tailscale VPN──→ Sese-AI (VPS)
                                      │
                                      ├──→ Fal.ai API (HTTPS)
                                      ├──→ Seedance API (HTTPS)
                                      ├──→ ElevenLabs API (HTTPS)
                                      ├──→ OpenRouter (via LiteLLM)
                                      └──→ Instagram Graph API (futur)
```

---

## 12. Risques et Mitigations

| Risque | Impact | Mitigation |
|---|---|---|
| Cout par contenu plus eleve que prevu | Budget | Privilegier Remotion (gratuit) + ComfyUI (gratuit) pour les formats motion design |
| Kitsu trop complexe pour 1 personne | Adoption | Telegram reste le pilotage principal, Kitsu = review/vue globale uniquement |
| Qualite video IA insuffisante pour viral | Qualite | Mix de styles (motion design + IA), pas tout-IA |
| Latence generation (Waza RPi5 lent) | Temps | Assets lourds sur cloud (Fal.ai), Waza pour le motion design leger |
| Pipeline trop rigide pour la creativite | Flexibilite | Invalidation ciblee par scene, pas de reconstruction totale |
