# Seed — chantier racine : fuites de credentials dans les prompts/transcripts

Date : 2026-07-25
Décision opérateur (session memory-pipeline-drift-autorepair) : la rotation
Qdrant est DIFFÉRÉE — le vrai problème à réparer d'abord est la CAUSE des
fuites de credentials dans les prompts/transcripts des sessions agent, pour ne
pas avoir à faire des rotations tous les jours.

## Fuites constatées (précédents concrets)

- 2026-07-23 : clé Qdrant + password Grafana affichés par `ansible --diff`
  (fix ponctuel `no_log: true`, VPAI `21d9c01`) — REX
  `project_coffre_agents_secrets`.
- 2026-07-25 : clé Qdrant affichée dans le transcript de session (grep d'un
  fichier env avec masquage sed raté — la regex ne couvrait pas `_KEY=` avant
  le `=`).
- Antérieur : rotation DB cf_app recommandée (fuite transcript, REX
  `project_cf_blocs135_2026_07_17`).

## Pistes (à cadrer au chantier)

- Classes de vecteurs : (a) lecture directe de fichiers env/secrets par les
  sessions (Read/Bash cat/grep), (b) sorties de commandes qui impriment des
  secrets (`--diff`, printenv, docker inspect), (c) prompts d'agents/essaims
  (interdit par doctrine mais non outillé), (d) transcripts JSONL persistés
  en clair sur waza (= P0-1 coffre, RÉSERVÉ, + P2 scrubbing 46 876 secrets).
- Pistes outillage : hook PreToolUse qui refuse/masque la lecture brute de
  fichiers classés secrets ; redacteur systématique de sortie d'outil (motifs
  du design auto-repair §6 réutilisables) ; convention "sonde sans secret"
  (scripts qui impriment des états, jamais des valeurs) ; lien avec pattern
  fantrad `scrub.py` (REX Presidio).
- Lié : P0-1/P2 du coffre agents (`project_coffre_agents_secrets`), LOI
  essaims "rien de secret n'entre dans un essaim".

## Critère de done implicite

Une session agent ordinaire ne doit plus pouvoir faire fuiter une valeur de
credential dans son transcript par les chemins (a)/(b) sans action délibérée —
mesurable en rejouant les 3 précédents ci-dessus.
