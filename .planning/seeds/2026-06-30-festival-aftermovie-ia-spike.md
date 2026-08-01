# Spike — Aftermovie IA festival Portugal (montage décisionnel + scene-augment)

**Date** : 2026-06-30
**Type** : spike/seed (PAS un PLAN.md produit — voir altitude ci-dessous)
**Déclencheur** : séjour festival Portugal, captation vidéo perso. Footage **pas encore tournée**.
**Objectif** : aftermovie monté/augmenté par IA — sélection auto, EDL décisionnel, effets + augmentation "blockbuster" (sky/bg replace, restyle décor, inserts).

## Altitude — pourquoi un spike, pas le repo CF v2

| | Décision |
|---|---|
| **Ce qu'on NE fait PAS** | Créer `~/work/saas/content-factory`, Temporal, Postgres domain Take. Ça shipperait après le festival. |
| **Ce qu'on fait** | Pipeline jetable sur la **stack existante** (ComfyUI Waza + PodPilot + Remotion + n8n), scripts + graphs ComfyUI. |
| **North star** | Façonner les artefacts (EDL JSON, graphs `scene-augment`, templates Remotion) pour **greffer dans CF v2 B6/B7 + modèle Take** plus tard. Migration target, pas prérequis. |

Réf. cadre cible : `docs/audits/2026-06-10-content-factory-v2-analyse-fonctionnelle-structurelle.md` (§B6 Forge, §B7 Cutting Room). Ce spike = preview jetable de ces briques.

---

## Section 1 — Capture brief (IRRÉVERSIBLE — à faire EN PREMIER)

Contrainte unique non-rattrapable : aucun pipeline ne répare une footage mal tournée. Décisions de tournage = entrée qu'on ne peut pas refaire.

| À capter | Pourquoi (alimente quoi) | Contrainte tournage |
|---|---|---|
| **2-3 plans "VFX-intended"** | scene-augment (sky replace, restyle, insert) | **caméra fixe ou pano lent**, expo stable, sujet détachable du fond |
| **Audio propre** d'un bout de set (≥30 s continu) | beat-sync (#1) + ambiance voix-off | source la moins bruitée possible, niveau stable |
| **B-roll texturé** (mains, scène, foule, azulejos réels, détails) | matière aftermovie + harmonisation LUT | plans courts 5-10 s, nets |
| **1 plan "même cadre" jour/nuit** | transition générative | tripod / point fixe repérable |
| Plans larges fixes 5-10 s | style-transfer (ComfyUI aime la stabilité) | éviter le shaky |

> Checklist à imprimer/mémoriser avant le départ. C'est la seule partie urgente.

---

## Section 2 — Spike post-prod (stack EXISTANTE, après le séjour)

Pipeline 4 étages, jetable, sans nouvelle infra.

| Étage | Quoi | Outil existant | Sortie |
|---|---|---|---|
| 1. **analyze** | scene-detect + transcript + scoring (énergie/visages/mouvement/audio peak) | n8n + whisper + vision via LiteLLM | `timeline.json` annoté |
| 2. **decide** | LLM lit l'annotation → propose coupe/transition/vitesse/effet/insert + **raison** | LiteLLM | `edl.json` (la partition) |
| 3. **augment** | exécute : LUT, slow-mo, upscale, + graphs scene-augment sur plans flaggés `vfx:true` | ComfyUI Waza → GPU PodPilot on-demand | clips boostés |
| 4. **render** | EDL → MP4, effets/transitions/captions programmatiques | Remotion (`montage_build`/`montage_render`) | aftermovie final |

**Garde-fou (gate humain étage 2→3)** : l'IA propose `edl.json`, je valide/édite **avant** de brûler du GPU. Évite de re-rendre des choix de montage à refaire.

### Graphs scene-augment (étage 3, ciblés)
Du facile-propre au fragile — **se limiter aux 🟢/🟡 pour ce spike** :
- 🟢 sky/bg replacement (SAM2 + matte + composite)
- 🟢 retrait objet (ProPainter, fond statique)
- 🟡 restyle décor (vid2vid ControlNet depth+canny + LTX-2/Wan 2.2)
- 🔴 insert personnage animé full-CG → **hors scope spike** (ratio effort/qualité, 1 plan vitrine max si curiosité)

GPU : `worker-comfy` éphémère RunPod via PodPilot (pattern fantrad), scale-to-zero. Cibler **2-3 money shots**, pas tout le film.

---

## Section 3 — Forward-compat (greffe CF v2 plus tard)

Façonner dès maintenant pour migrer sans réécrire :

| Artefact spike | Cible CF v2 |
|---|---|
| `edl.json` schema (segments + effects + reason + insert) | Timeline OTIO (B7) + ReviewNote |
| chaque génération = `{seed, model, provider, cost, params}` | modèle **Take** (B1/B6) — logguer ces champs MÊME en jetable |
| graphs ComfyUI `scene-augment`, `beat-sync` | presets versionnés Forge (B6) |
| templates Remotion (intro/outro Yinda, captions) | Cutting Room reels (B7) |
| scoring choix de take (A préféré à B) | signal qualité Elo resolver PodPilot (B3) |

> Règle : logguer seed/modèle/coût par génération dès le spike. C'est gratuit maintenant, c'est la généalogie Take plus tard.

---

## Découpage exécution (ordre)

1. **[urgent, avant départ]** Finaliser Section 1 → checklist tournage
2. **[sans GPU]** Étage 1 `analyze` : 1 rush → `timeline.json` (proto n8n ou script Python)
3. **[sans GPU]** Étage 2 `decide` : prompt LLM → `edl.json` + validation manuelle
4. **[sans GPU]** Étage 4 `render` Remotion sur EDL simple (coupes + LUT + captions, sans augment)
5. **[GPU PodPilot]** Étage 3 `augment` : 1 graph 🟢 sky/bg sur 1 frame → puis animé sur 1 plan
6. **[GPU]** Étendre à 2-3 money shots 🟡 restyle si étape 5 probante

## Dépendances / prérequis
- PodPilot opérationnel (8 items P0 hardening — réf. `podpilot/docs/.../2026-06-08-hardening-plan.md`)
- Volumes ComfyUI RunPod : LTX-2 / Wan 2.2 (cold load ~20-30 s)
- ComfyUI Waza CPU-only confirmé = drafts/compositing gratuit ; tout le lourd → RunPod

## Risques
| Risque | Parade |
|---|---|
| Footage non tournée VFX-ready | Section 1 = priorité absolue, checklist |
| Flicker temporel restyle | ControlNet depth/optical-flow + modèles natifs vidéo (LTX-2) |
| Coût/temps GPU | scale-to-zero, 2-3 money shots max, gate EDL avant augment |
| Scope creep vers CF v2 | Ce doc = spike jetable ; le repo produit reste l'audit, pas urgent |

## Non-objectifs (explicites)
- ❌ Créer le repo CF v2 / Temporal / Postgres Take (= roadmap audit, hors festival)
- ❌ Insertion personnage animé full-CG (🔴, hors scope)
- ❌ 90 min / long-form (audit M4)
