# Qdrant Legacy Migration Map

Date: 2026-04-11
Statut: v0.5 mapping initial valide
Source: `/opt/workstation/data/ai-memory-worker/audits/qdrant-inventory-20260410T215942Z.json`
Portee: planification de migration des collections Qdrant legacy vers `memory_v1`

## 1. Objectif

Ce document transforme l'audit Qdrant v0.4 en decisions operationnelles par
collection.

Regle centrale: **aucune collection legacy ne doit etre supprimee ou migree en
masse sans validation retrieval**.

La migration correcte consiste a retrouver les sources originales, puis a
reindexer vers `memory_v1` avec:

- embedding local `google/embeddinggemma-300m`
- dimension cible 768
- payload normalise `memory_v1`
- chunking LlamaIndex applique par le worker
- benchmark retrieval avant toute purge

## 2. Resume v0.4

- collections inventoriees: 28
- collection cible active: `memory_v1`
- points `memory_v1`: 1105
- dimension `memory_v1`: 768
- collections legacy: 23
- collections vides: 4
- total points Qdrant: 252073

## 3. Decisions possibles

| Decision | Sens |
|---|---|
| `target_active` | Collection cible actuelle, a conserver. |
| `reindex_to_memory_v1` | Retrouver la source originale et reindexer proprement vers `memory_v1`. |
| `keep_as_is` | Collection utile mais hors memoire documentaire; ne pas fusionner maintenant. |
| `out_of_scope` | Collection hors lot memoire Waza; garder hors migration v0.x. |
| `investigate_source` | Source ou usage incertain; inspection requise avant decision. |
| `drop_candidate_empty` | Collection vide; candidate a suppression apres backup/validation humaine. |
| `archive_later` | A conserver temporairement, puis exporter/archiver avant purge eventuelle. |

## 4. Mapping par collection

| Collection | Points | Dim | Kind | Decision | Priorite | Justification | Action suivante |
|---|---:|---:|---|---|---|---|---|
| `memory_v1` | 1105 | 768 | memory_v1 | `target_active` | P0 | Collection cible deja au bon schema et au bon modele. | Continuer les backfills controles et benchmarks. |
| `app-factory-rex` | 13 | 1536 | rex | `reindex_to_memory_v1` | P1 | REX utile, faible volume, ancien embedding incompatible. | Retrouver les REX App Factory sources et reindexer avec `doc_kind=rex`. |
| `flash-rex` | 30 | 1536 | rex | `reindex_to_memory_v1` | P1 | REX projet Flash, directement utile aux agents. | Reindexer depuis les fichiers REX Flash si disponibles. |
| `operational-rex` | 281 | 384 | rex | `reindex_to_memory_v1` | P1 | REX operationnel transversal, forte valeur memoire. | Identifier les sources, mapper `service`, `severity`, `root_cause`, `fix` vers tags/topic. |
| `vpai_rex` | 231 | 1536 | rex | `reindex_to_memory_v1` | P1 | REX VPAI, tres pertinent pour Codex/Claude dans ce repo. | Retrouver les fichiers sources et reindexer dans `memory_v1`. |
| `rex_lessons` | 3 | 384 | rex | `reindex_to_memory_v1` | P2 | Tres faible volume, peut etre absorbe apres verification. | Verifier si doublon avec `operational-rex` avant reindex. |
| `zimboo-rex` | 15 | 1536 | rex | `reindex_to_memory_v1` | P3 | REX utile mais hors scope prioritaire actuel. | Reporter apres VPAI/Flash/operations. |
| `comfyui-docs` | 2436 | 1536 | docs | `reindex_to_memory_v1` | P2 | Docs volumineuses, probablement utiles pour Flash/ComfyUI, mais embedding incompatible. | Reprendre depuis scraper/source officielle, pas depuis vecteurs legacy. |
| `comfyui-node-docs` | 20 | 1536 | docs | `reindex_to_memory_v1` | P2 | Petite collection docs nodes, utile si source fiable. | Fusionner avec workflow futur docs officielles ComfyUI. |
| `dev-knowledge` | 196 | 384 | unknown | `investigate_source` | P2 | Semble documentation technique, mais taxonomie source incertaine. | Inspecter samples complets et source avant mapping. |
| `flash_knowledge` | 2 | 384 | unknown | `reindex_to_memory_v1` | P2 | Faible volume Flash; probablement migrable si source existe. | Verifier doublon avec `flash-rex`/docs Flash. |
| `jarvis-docs` | 11 | 384 | docs | `out_of_scope` | P3 | Docs Jarvis, hors lot Waza prioritaire actuel. | Garder hors migration jusqu'au lot Jarvis. |
| `kitsu-docs` | 98 | 1536 | docs | `reindex_to_memory_v1` | P3 | Documentation service utile, mais pas prioritaire pour memoire Waza. | Reindexer depuis documentation officielle quand le workflow docs stack arrive. |
| `metube-docs` | 21 | 1536 | docs | `reindex_to_memory_v1` | P3 | Documentation service, faible volume. | Reporter au lot docs officielles. |
| `netbird-docs` | 18 | 384 | docs | `reindex_to_memory_v1` | P3 | Documentation VPN potentiellement utile, mais moins prioritaire que Tailscale actuel. | Reevaluer selon stack active. |
| `vref-cli-docs` | 9 | 1536 | docs | `reindex_to_memory_v1` | P3 | Documentation CLI video reference, petite collection. | Reindexer depuis source officielle si encore utilisee. |
| `zitadel-docs` | 1922 | 384 | docs | `reindex_to_memory_v1` | P2 | Volume important, docs identite potentiellement utiles. | Reprendre depuis source officielle et benchmarker avant ingestion large. |
| `content_index` | 16 | 1536 | unknown | `investigate_source` | P2 | Semble index de sessions/documents, contexte insuffisant. | Inspecter payloads complets pour eviter doublons ou memoire conversationnelle prematuree. |
| `model-registry` | 67 | 1536 | unknown | `keep_as_is` | P2 | Registre de modeles structure, plus proche catalogue applicatif que memoire documentaire. | Ne pas migrer sans schema catalogue dedie. |
| `videoref_styles` | 16 | 1536 | unknown | `keep_as_is` | P3 | Donnees metier style/video, probablement consommables par app specialisee. | Garder separe tant que le cas d'usage n'est pas clarifie. |
| `jarvis-knowledge` | 2 | 384 | unknown | `out_of_scope` | P3 | Memoire agent Jarvis, risque de conflit avec future memoire multi-agents. | Reporter au lot provenance multi-agents. |
| `jarvis-sessions` | 1 | 384 | unknown | `out_of_scope` | P3 | Memoire conversationnelle/sessionnelle, pipeline dedie prevu plus tard. | Ne pas fusionner dans `memory_v1` documentaire. |
| `jarvis-tasks` | 5 | 1 | unknown | `archive_later` | P3 | Dimension 1 suspecte; probablement stockage non semantique. | Exporter/archiver avant suppression eventuelle, ne pas migrer. |
| `semantic_cache` | 245555 | 1536 | unknown | `keep_as_is` | P0 | Cache applicatif massif, pas une source documentaire. Migration aveugle dangereuse. | Exclure de `memory_v1`; definir une politique cache separee. |
| `app-factory-patterns` | 0 | 1536 | unknown | `drop_candidate_empty` | P3 | Collection vide. | Confirmer absence de producteur avant purge future. |
| `brand-voice` | 0 | 1536 | unknown | `drop_candidate_empty` | P3 | Collection vide. | Confirmer absence de producteur avant purge future. |
| `macgyver_insights` | 0 | 384 | unknown | `drop_candidate_empty` | P3 | Collection vide. | Confirmer absence de producteur avant purge future. |
| `palais_memory` | 0 | 1536 | unknown | `drop_candidate_empty` | P3 | Collection vide. | Confirmer absence de producteur avant purge future. |

## 5. Lots de migration proposes

### v0.6 - Migration pilote REX faible volume

But: valider la methode sur un scope petit et utile.

Candidats:

- `app-factory-rex`
- `flash-rex`
- `rex_lessons`

Regles:

- retrouver les fichiers sources avant ingestion
- reindexer vers `memory_v1`
- benchmarker les requetes REX avant/apres
- ne pas supprimer les collections legacy apres le premier passage

### v0.7 - Migration REX operationnelle / VPAI

Candidats:

- `vpai_rex`
- `operational-rex`

Regles:

- verifier doublons entre collections
- ajouter des requetes benchmark dediees REX
- conserver `severity`, `service`, `root_cause`, `fix` sous forme de tags/topic quand pertinent

### v0.8 - Docs officielles et stack

Candidats:

- `comfyui-docs`
- `comfyui-node-docs`
- `zitadel-docs`
- `kitsu-docs`
- `metube-docs`
- `netbird-docs`
- `vref-cli-docs`

Regles:

- reindexer depuis docs officielles a jour
- ne pas migrer depuis payload legacy si une source officielle existe
- separer docs stack et docs projet via `source_kind` et `doc_kind`

### Hors migration documentaire

Collections a garder hors `memory_v1` pour l'instant:

- `semantic_cache`
- `model-registry`
- `videoref_styles`
- `jarvis-knowledge`
- `jarvis-sessions`
- `jarvis-tasks`

## 6. Points d'attention

- Les dimensions 1536, 384 et 1 sont incompatibles avec `memory_v1` en 768.
- Une conversion directe de points Qdrant legacy vers `memory_v1` n'est pas une
  vraie migration: elle conserve les anciens embeddings et l'ancien chunking.
- Les collections vides ne doivent etre supprimees qu'apres verification des
  producteurs eventuels.
- Les collections Jarvis ressemblent a une memoire agent/session; elles doivent
  attendre le design provenance multi-agents.
- `semantic_cache` est massif et doit rester traite comme cache, pas comme
  memoire documentaire.

## 7. Definition de Done v0.5

- chaque collection Qdrant auditee a une decision initiale
- les collections candidates a migration pilote sont identifiees
- les collections hors scope sont explicitement exclues de `memory_v1`
- aucune suppression Qdrant n'a ete executee
- la prochaine version peut demarrer sur un pilote `v0.6` limite
