# Template SimuBot — Scénario "Perte de Supervision Réseau Optique"

**Slug :** `supervision-perte-visibilite-equipements`
**Version :** 1.0
**Durée estimée :** 25-35 min
**Modes autorisés :** exam, terrain, accompanied
**Domaines compétences :** Technique Réseau, Procédural, Qualité d'exécution, Relationnel, Cognitif

Ce document contient deux parties indispensables à la mise en œuvre :

1. **Partie A** — Le descripteur YAML SimuBot (à placer dans le dépôt `simubot-scenarios` ou importer via interface)
2. **Partie B** — La spécification du flow Typebot (à reconstruire dans l'éditeur visuel Typebot en suivant les blocs pas à pas)

Un glossaire anonymisé est fourni en fin de document pour que l'auteur puisse adapter le vocabulaire à sa propre organisation.

---

## Partie A — Descripteur YAML SimuBot

Fichier `supervision-perte-visibilite-equipements.yaml` :

```yaml
slug: supervision-perte-visibilite-equipements
titre: "Perte de supervision sur équipements réseau optique"
description: |
  Scénario d'intervention sur perte de supervision affectant la visibilité
  des équipements réseau optique (NE). Le candidat doit détecter, qualifier,
  diagnostiquer la cause racine, choisir la bonne voie d'escalade et valider
  le rétablissement. Scénario multi-cas : lien transport opérateur down,
  infrastructure supervision HS, compte authentification bloqué, certificat
  expiré, ou carte de contrôle NE défaillante.

version: 1

engine:
  type: typebot
  typebot_public_id: "REMPLACER_PAR_ID_TYPEBOT"
  typebot_url_path: "/supervision-perte-visibilite"

allowed_modes: [exam, terrain, accompanied]
pass_policy: per_competence
required_validation: false
duree_estimee_min: 30

site_id: null
tags: [reseau_optique, supervision, intervention_niveau_2, procedure_longue]

scoring_schema:
  blocks:
    - block_ref: detection
      ordre: 1
      titre: "Détection et première réaction"
      competences:
        - { code: comp_reseau_alarme_identification, max_score: 3, weight: 1.0 }
        - { code: comp_qual_horodatage, max_score: 2, weight: 1.0 }
        - { code: comp_cog_gestion_stress, max_score: 2, weight: 0.5 }
      feedback_success: |
        Bonne détection : horodatage précis et prise en compte ordonnée.
        Réflexe d'ouverture du catalogue d'alarmes correct.
      feedback_failure: |
        La détection a manqué de rigueur. À retenir : horodater IMMÉDIATEMENT
        dans le ticket interne avant toute action, et consulter le catalogue
        d'alarmes pour identifier la fiche applicable.
      mop_refs: [M0.20]

    - block_ref: mop_identification
      ordre: 2
      titre: "Identification de la MOP à appliquer"
      competences:
        - { code: comp_procedural_mop_identification, max_score: 4, weight: 1.0 }
      feedback_success: "MOP M0.20 correctement identifiée."
      feedback_failure: |
        La MOP applicable était M0.20 "Perte de Supervision". Les autres MOP
        proposées couvrent des situations différentes (châssis, alimentation,
        etc.). À chaque type d'alarme correspond une MOP — voir le catalogue.
      mop_refs: [M0.20]

    - block_ref: qualification_perimetre
      ordre: 3
      titre: "Qualification du périmètre impacté"
      competences:
        - { code: comp_reseau_qualification_perimetre, max_score: 4, weight: 1.0 }
        - { code: comp_cog_synthese_diagnostic, max_score: 3, weight: 0.5 }
      feedback_success: "Qualification correcte, les bons tests ont été conduits dans le bon ordre."
      feedback_failure: |
        La qualification doit répondre à trois questions dans l'ordre :
        1) Le périmètre (1 NE / multi-NE / multi-sites)
        2) L'EMS est-il accessible ?
        3) Le dashboard SaaS reçoit-il encore des heartbeats ?
        Selon les réponses, on oriente vers infra applicative vs réseau OOB vs NE isolé.
      mop_refs: [M0.20]

    - block_ref: info_support_client
      ordre: 4
      titre: "Information de l'équipe support client"
      competences:
        - { code: comp_rel_communication_support, max_score: 3, weight: 1.0 }
        - { code: comp_qual_documentation, max_score: 2, weight: 0.5 }
      feedback_success: "Communication au support client claire et horodatée."
      feedback_failure: |
        L'information au support client doit être systématique dès la prise en compte,
        pas après le rétablissement. Contenu minimal : perimètre impacté, cause suspectée,
        ETA d'investigation.

    - block_ref: sop_diagnostic_identification
      ordre: 5
      titre: "Identification de la SOP de diagnostic"
      competences:
        - { code: comp_procedural_sop_identification, max_score: 4, weight: 1.0 }
      feedback_success: "Bonne identification — la SOP 10 couvre le diagnostic de perte supervision OOB."
      feedback_failure: |
        La SOP à dérouler pour le diagnostic est la 10-SOP. Les autres SOPs
        couvrent la connexion (19), l'escalade constructeur (20), l'escalade
        supervision (21), et l'escalade opérateur (22).
      sop_refs: [SOP-10]

    - block_ref: diag_infra_supervision
      ordre: 6
      titre: "Diagnostic bascule serveur de supervision"
      competences:
        - { code: comp_reseau_diagnostic_infra, max_score: 4, weight: 1.0 }
        - { code: comp_cog_synthese_diagnostic, max_score: 2, weight: 1.0 }
      feedback_success: "Bon réflexe — la bascule inter-sites permet d'isoler un défaut serveur."
      feedback_failure: |
        Dans la phase diagnostic, basculer l'EMS d'un site vers l'autre permet
        d'écarter ou confirmer un défaut côté serveur. Si le problème persiste
        après bascule → infra applicative ou réseau plus large.

    - block_ref: diag_reseau_oob
      ordre: 7
      titre: "Diagnostic du réseau OOB et identification du cas"
      competences:
        - { code: comp_reseau_diagnostic_oob, max_score: 5, weight: 1.0 }
        - { code: comp_procedural_decision_cas, max_score: 4, weight: 1.0 }
      feedback_success: "Bonne lecture des symptômes → bonne identification du cas."
      feedback_failure: |
        Les 5 cas à connaître par cœur :
        A) Lien L2/L3 opérateur OOB down
        B) Infrastructure supervision HS côté fournisseur
        C) Compte d'authentification bloqué / TOTP KO
        D) Certificat NE expiré
        E) Carte de contrôle NE défaillante
        Chaque cas a sa SOP d'escalade dédiée.

    - block_ref: sop_escalade_identification
      ordre: 8
      titre: "Identification de la voie d'escalade appropriée"
      competences:
        - { code: comp_procedural_sop_escalade, max_score: 4, weight: 1.0 }
        - { code: comp_procedural_decision_cas, max_score: 2, weight: 0.5 }
      feedback_success: "SOP d'escalade correcte pour le cas diagnostiqué."
      feedback_failure: |
        Mapping cas → SOP :
        Cas A → SOP-22 (opérateur transport)
        Cas B → SOP-21 (infrastructure supervision)
        Cas C → SOP-21 (via référent habilité pour déblocage compte)
        Cas D → PKI interne ou SOP-21 si externalisé
        Cas E → SOP-20 (constructeur NE) + bascule MOP Châssis
      sop_refs: [SOP-20, SOP-21, SOP-22]

    - block_ref: ticket_contenu
      ordre: 9
      titre: "Contenu du ticket d'escalade fournisseur"
      competences:
        - { code: comp_qual_ticket_contenu, max_score: 4, weight: 1.0 }
        - { code: comp_qual_documentation, max_score: 2, weight: 1.0 }
      feedback_success: "Ticket complet — le fournisseur pourra traiter rapidement."
      feedback_failure: |
        Un ticket d'escalade complet contient a minima : numéro circuit/équipement,
        horodatage de détection, type de coupure observé, topologie concernée,
        criticité, actions déjà entreprises. Sans ces éléments, le fournisseur
        perdra du temps en allers-retours.

    - block_ref: retablissement_validation
      ordre: 10
      titre: "Validation du rétablissement"
      competences:
        - { code: comp_procedural_validation_retablissement, max_score: 4, weight: 1.0 }
        - { code: comp_qual_verification, max_score: 3, weight: 1.0 }
      feedback_success: "Validation complète sur les 4 axes — bonne rigueur."
      feedback_failure: |
        Un rétablissement se valide sur 4 axes et pas un seul :
        1) NE verts sur topologie EMS
        2) Dashboard SaaS reçoit à nouveau les heartbeats
        3) Accès supervision testé depuis plusieurs postes
        4) Trails/services non impactés (vérification trafic)

    - block_ref: cloture_documentation
      ordre: 11
      titre: "Clôture et compte-rendu d'incident"
      competences:
        - { code: comp_qual_documentation, max_score: 5, weight: 1.0 }
        - { code: comp_qual_post_mortem, max_score: 3, weight: 0.5 }
        - { code: comp_rel_communication_support, max_score: 2, weight: 0.5 }
      feedback_success: "Compte-rendu structuré et complet."
      feedback_failure: |
        Un bon compte-rendu contient : chronologie (détection → qualification
        → diagnostic → actions → rétablissement), cause racine identifiée,
        SOPs mobilisées, voie d'escalade utilisée, ticket(s) fournisseur archivé(s).
        La clôture comprend aussi la communication "supervision rétablie" au support
        client avec horodatage et périmètre.

    - block_ref: post_mortem_decision
      ordre: 12
      titre: "Décision post-mortem"
      competences:
        - { code: comp_procedural_cloture, max_score: 2, weight: 1.0 }
        - { code: comp_qual_post_mortem, max_score: 2, weight: 1.0 }
      feedback_success: "Bon jugement — post-mortem déclenché selon les critères."
      feedback_failure: |
        Déclencheurs de post-mortem : cause inhabituelle OU impact > 1h OU
        récurrence observée. Le post-mortem se rédige et se partage avec
        l'équipe de management pour capitalisation.

    # Blocs d'auto-évaluation (ne scorent pas, alimentent la calibration)
    - block_ref: self_eval_diagnostic
      ordre: 90
      titre: "Auto-évaluation — confiance sur le diagnostic"
      is_self_eval: true
      self_eval_target_code: comp_reseau_diagnostic_oob
      competences: []

    - block_ref: self_eval_procedural
      ordre: 91
      titre: "Auto-évaluation — maîtrise procédurale"
      is_self_eval: true
      self_eval_target_code: comp_procedural_mop_identification
      competences: []

    - block_ref: self_eval_stress
      ordre: 92
      titre: "Auto-évaluation — gestion du stress"
      is_self_eval: true
      self_eval_target_code: comp_cog_gestion_stress
      competences: []

    - block_ref: self_eval_documentation
      ordre: 93
      titre: "Auto-évaluation — qualité documentation"
      is_self_eval: true
      self_eval_target_code: comp_qual_documentation
      competences: []
```

---

## Partie B — Spécification du flow Typebot

Cette partie décrit ce qu'il faut construire dans l'éditeur visuel Typebot. Elle liste tous les blocs Typebot dans l'ordre, avec leur contenu, les variables à créer, les options de réponse et les incréments de scoring.

### B.1 Variables Typebot à créer

Dans l'onglet "Variables" de Typebot, créer les variables suivantes (type `number`, valeur initiale `0` sauf indication) :

**Variables d'entrée (captées depuis l'URL)**

| Variable | Type | Source |
|---|---|---|
| `assignment_id` | string | URL param |
| `user_id` | string | URL param |
| `launch_token` | string | URL param |
| `mode` | string | URL param |
| `webhook_signature` | string | URL param |

**Variables de scoring par bloc**

| Variable | Type | Max |
|---|---|---|
| `block_detection_raw` | number | 7 |
| `block_mop_identification_raw` | number | 4 |
| `block_qualification_perimetre_raw` | number | 7 |
| `block_info_support_client_raw` | number | 5 |
| `block_sop_diagnostic_identification_raw` | number | 4 |
| `block_diag_infra_supervision_raw` | number | 6 |
| `block_diag_reseau_oob_raw` | number | 9 |
| `block_sop_escalade_identification_raw` | number | 6 |
| `block_ticket_contenu_raw` | number | 6 |
| `block_retablissement_validation_raw` | number | 7 |
| `block_cloture_documentation_raw` | number | 10 |
| `block_post_mortem_decision_raw` | number | 4 |

**Variables d'auto-évaluation**

| Variable | Type | Échelle |
|---|---|---|
| `self_eval_comp_reseau_diagnostic_oob` | number | 0-100 |
| `self_eval_comp_procedural_mop_identification` | number | 0-100 |
| `self_eval_comp_cog_gestion_stress` | number | 0-100 |
| `self_eval_comp_qual_documentation` | number | 0-100 |

**Variables contextuelles (pour personnaliser l'expérience)**

| Variable | Type | Usage |
|---|---|---|
| `cas_diagnostique` | string | Stocke le cas identifié par le candidat (A/B/C/D/E) |
| `heure_detection` | string | Horodatage saisi par le candidat |

---

### B.2 Structure narrative

Le scénario suit un arbre principalement linéaire avec quelques branchements selon les réponses. Par défaut, le scénario force le candidat à suivre la "bonne" trajectoire même s'il répond mal à une étape (sinon il resterait bloqué dans un cul-de-sac), mais chaque mauvaise réponse n'incrémente pas le `block_*_raw` correspondant. Les feedbacks pédagogiques sont affichés en fin de parcours par SimuBot, pas par Typebot.

Principe : **on score, on ne commente pas en cours de route** (ce serait un feedback qui fausserait la suite de l'évaluation).

---

### B.3 Bloc 0 — Accueil et capture des variables URL

**Type Typebot :** Start + Set Variable (multiple)

**Contenu (bulle texte) :**

> Bonjour. Vous démarrez une simulation d'intervention sur **perte de supervision réseau optique**.
>
> Durée estimée : 30 minutes. Les réponses sont évaluées mais aucun feedback n'est affiché pendant le parcours ; le bilan complet vous sera présenté à la fin.
>
> Vous recevez à 02h14 une série d'alertes sur votre outil de supervision :
>
> - Dashboard SaaS : "Host unreachable" sur 12 équipements NE du site A
> - EMS primaire : 12 NE passent en gris-bleu sur la topologie
> - Une alarme "No OSPF hello packets received from neighbor" apparaît puis se résout automatiquement en moins de 30 secondes
>
> Vous êtes de permanence. Respirez et procédons étape par étape.

**Actions Set Variable :**
- `assignment_id` = {{URL param assignment_id}}
- `user_id` = {{URL param user_id}}
- `launch_token` = {{URL param launch_token}}
- `mode` = {{URL param mode}}
- `webhook_signature` = {{URL param webhook_signature}}

**Bouton continue :** "Je commence"

→ Bloc 1

---

### B.4 Bloc 1 — `detection` : Première réaction

**Type :** Question radio (choix unique) + Text input (horodatage)

**Contenu :**

> **Question 1/12** — Détection et première action
>
> Quelle est votre toute première action, avant même d'ouvrir un outil de diagnostic ?

**Options :**

1. **Horodater précisément l'incident dans le ticket interne et consulter le catalogue d'alarmes pour identifier la MOP applicable**
   - `Set Variable` : `block_detection_raw` += 3
   - → sous-bloc horodatage

2. Appeler immédiatement le support client pour informer
   - `Set Variable` : `block_detection_raw` += 1
   - → sous-bloc horodatage (tardif mais acceptable)

3. Commencer immédiatement à diagnostiquer les NE en alarme
   - `Set Variable` : `block_detection_raw` += 0
   - → sous-bloc horodatage

4. Attendre que plus d'alarmes remontent pour avoir une vue complète
   - `Set Variable` : `block_detection_raw` += 0
   - → sous-bloc horodatage

**Sous-bloc horodatage (Text input) :**

> Vous procédez à l'horodatage. Saisissez l'heure exacte de détection (format HH:MM) :

- `Set Variable` : `heure_detection` = {{reponse}}
- Validation : l'entrée contient bien `HH:MM`, sinon on reboucle
- Scoring bonus si heure raisonnable (< 02h16) : `block_detection_raw` += 2 (horodatage rapide)
- Sinon +1

**Sous-bloc catalogue (Bulle texte + continue) :**

> Vous consultez le catalogue d'alarmes. Les fiches applicables pour les mots-clés "supervision", "OOB" pointent vers la MOP M0.20 "Perte de Supervision".
>
> Votre ticket interne est ouvert, horodaté {{heure_detection}}.

- `Set Variable` : `block_detection_raw` += 2 (rigueur)

→ Bloc 2

---

### B.5 Bloc 2 — `mop_identification` : Identification de la MOP

**Type :** Question radio

**Contenu :**

> **Question 2/12** — Identification de la MOP
>
> Parmi les MOPs suivantes, laquelle est applicable à cette situation ?

**Options :**

1. M0.15 — Perte d'alimentation site
   - `block_mop_identification_raw` += 0
2. **M0.20 — Perte de supervision**
   - `block_mop_identification_raw` += 4
3. M0.23 — Défaut châssis / carte NE
   - `block_mop_identification_raw` += 1 (proche mais pas le point d'entrée)
4. M0.08 — Dégradation de performance optique
   - `block_mop_identification_raw` += 0

→ Bloc 3 (dans tous les cas, on continue avec la M0.20)

---

### B.6 Bloc 3 — `qualification_perimetre` : Qualification

**Type :** Séquence de 3 questions radio

**Sous-question 3a — Périmètre :**

> **Question 3/12 — Étape 1/3** — Qualification du périmètre
>
> Vous commencez la qualification. Quel est votre premier test ?

1. **Déterminer si l'impact est sur 1 NE, plusieurs NE d'un même site, ou multi-sites**
   - `block_qualification_perimetre_raw` += 3
2. Tester directement la connexion SSH sur un NE
   - `block_qualification_perimetre_raw` += 0
3. Redémarrer le serveur EMS
   - `block_qualification_perimetre_raw` += 0 (action précoce, risquée)

**Bulle résultat (auto) :**

> Votre investigation révèle : 12 NE du **site A** impactés, 0 NE du site B impacté. Donc **périmètre = multi-NE, un seul site**.

**Sous-question 3b — Accès EMS :**

> Test suivant : accédez-vous à l'EMS ?

1. L'EMS est accessible, les NE impactés sont en alarme dessus → **problème côté NE ou réseau OOB**
   - `block_qualification_perimetre_raw` += 2
2. L'EMS est inaccessible → problème applicatif ou infra supervision
   - `block_qualification_perimetre_raw` += 1 (partiellement vrai mais inadapté au cas réel)

**Bulle résultat (auto) :**

> EMS accessible, NE en alarme dessus. Donc **le problème n'est pas côté supervision applicative**.

**Sous-question 3c — Dashboard SaaS :**

> Le dashboard SaaS reçoit-il encore des heartbeats ?

1. **Oui, les heartbeats des switches OOB et firewalls du site A arrivent encore → infra tourne**
   - `block_qualification_perimetre_raw` += 2
2. Non, le SaaS est muet → perte infrastructure large
   - `block_qualification_perimetre_raw` += 0

**Bulle synthèse (auto) :**

> Synthèse : périmètre multi-NE site A, EMS OK, SaaS OK pour infra site A. Le problème se situe donc **entre l'infra supervision du site A et les NE du site A**, probablement sur le chemin OOB.

→ Bloc 4

---

### B.7 Bloc 4 — `info_support_client` : Communication

**Type :** Question radio + Text input

**Contenu :**

> **Question 4/12** — Information au support client
>
> Quand informez-vous l'équipe support client (celle qui gère la relation client) ?

1. Dès la détection confirmée, avec un message court (périmètre + action en cours)
   - `block_info_support_client_raw` += 3
2. Après avoir trouvé la cause racine
   - `block_info_support_client_raw` += 1
3. Après le rétablissement complet
   - `block_info_support_client_raw` += 0
4. Uniquement si le support client appelle en premier
   - `block_info_support_client_raw` += 0

**Sous-bloc Text input (uniquement si choix 1 ou 2) :**

> Rédigez votre message au support client en une phrase (max 200 caractères) :

- `Set Variable` : message stocké dans les réponses
- Scoring indicatif (à évaluer en post-traitement côté SimuBot ou via détection de mots-clés Typebot) :
  - Contient "supervision" OU "NE" → `block_info_support_client_raw` += 1
  - Contient "en cours" OU "investigation" → `block_info_support_client_raw` += 1

→ Bloc 5

---

### B.8 Bloc 5 — `sop_diagnostic_identification` : Identification SOP diagnostic

**Type :** Question radio

**Contenu :**

> **Question 5/12** — Identification de la SOP de diagnostic
>
> Pour le diagnostic de cette perte de supervision, quelle SOP dérouler ?

1. SOP-19 — Connexion supervision (VPN / local)
   - `block_sop_diagnostic_identification_raw` += 1 (pré-requis, pas diagnostic)
2. **SOP-10 — Diagnostic & traitement perte supervision OOB**
   - `block_sop_diagnostic_identification_raw` += 4
3. SOP-20 — Escalade constructeur
   - `block_sop_diagnostic_identification_raw` += 0 (trop tôt)
4. SOP-21 — Escalade supervision
   - `block_sop_diagnostic_identification_raw` += 0 (trop tôt)
5. SOP-22 — Escalade opérateur fibre
   - `block_sop_diagnostic_identification_raw` += 0 (trop tôt)

→ Bloc 6

---

### B.9 Bloc 6 — `diag_infra_supervision` : Bascule serveur

**Type :** Question radio

**Contenu :**

> **Question 6/12** — Diagnostic infrastructure supervision
>
> Selon SOP-10, vous testez en basculant le serveur EMS d'un site vers l'autre. Vous passez du serveur `Site-A-EMS-01` vers `Site-B-EMS-01`. Le problème persiste.
>
> Qu'est-ce que ce test vous a permis d'établir ?

1. **Le défaut n'est pas côté serveur EMS (les deux serveurs voient le même problème)**
   - `block_diag_infra_supervision_raw` += 4
2. Le défaut est côté `Site-A-EMS-01`, il faut le réparer
   - `block_diag_infra_supervision_raw` += 0
3. Le défaut est côté `Site-B-EMS-01`
   - `block_diag_infra_supervision_raw` += 0
4. Le test n'est pas concluant, il faut recommencer
   - `block_diag_infra_supervision_raw` += 1

**Bulle suivante (auto) :**

> Bon raisonnement. Le problème étant visible depuis les deux serveurs EMS, la cause racine est en aval — dans le réseau OOB qui achemine les données depuis les NE vers les serveurs EMS.

- `block_diag_infra_supervision_raw` += 2 (pour la synthèse correcte)

→ Bloc 7

---

### B.10 Bloc 7 — `diag_reseau_oob` : Diagnostic réseau OOB et identification du cas

**Type :** Bulle texte + Question radio (cas)

**Contenu (bulle) :**

> Vous passez au diagnostic réseau OOB. Tests effectués :
>
> - Ping de la passerelle OOB depuis votre poste de supervision : **OK**
> - État BGP vers Opérateur Transport 1 (site A) : **down depuis 02h11**
> - État BGP vers Opérateur Transport 2 (site B) : OK
> - Cartes RCP des NE site A : pas d'alarme Equipment Mismatch
> - Certificats numériques NE : valides jusqu'en 2028
> - Compte d'authentification : fonctionnel
>
> **Quel cas diagnostiquez-vous ?**

**Options :**

1. **Cas A — Lien L2/L3 opérateur OOB down**
   - `block_diag_reseau_oob_raw` += 9
   - `Set Variable` : `cas_diagnostique` = "A"
2. Cas B — Infrastructure supervision (fournisseur) défaillante
   - `block_diag_reseau_oob_raw` += 2
   - `cas_diagnostique` = "B"
3. Cas C — Compte d'authentification bloqué / TOTP KO
   - `block_diag_reseau_oob_raw` += 0
   - `cas_diagnostique` = "C"
4. Cas D — Certificat NE expiré
   - `block_diag_reseau_oob_raw` += 0
   - `cas_diagnostique` = "D"
5. Cas E — Carte de contrôle NE en défaut
   - `block_diag_reseau_oob_raw` += 0
   - `cas_diagnostique` = "E"

→ Bloc 8

---

### B.11 Bloc 8 — `sop_escalade_identification` : SOP d'escalade

**Type :** Question radio (branchement dynamique selon `cas_diagnostique`)

**Contenu (affichage adaptatif selon le cas saisi précédemment) :**

> **Question 8/12** — Voie d'escalade
>
> Pour le cas que vous avez diagnostiqué ({{cas_diagnostique}}), quelle SOP d'escalade déclenchez-vous ?

**Options (toujours affichées) :**

1. SOP-20 — Escalade Fournisseur Alpha (constructeur NE)
2. SOP-21 — Escalade Fournisseur Beta (infrastructure supervision)
3. **SOP-22 — Escalade Opérateur Transport**
4. Aucune — résolution en interne

**Logique de scoring (selon `cas_diagnostique`) :**

| Cas | Bonne réponse | Score max |
|---|---|---|
| A | SOP-22 | +4 sur option 3 |
| B | SOP-21 | +4 sur option 2 |
| C | SOP-21 | +4 sur option 2 |
| D | Option 4 (PKI interne) ou SOP-21 | +3 sur 2 ou 4 |
| E | SOP-20 | +4 sur option 1 |

**Scoring bonus (cohérence diagnostic → escalade) :** +2 si la SOP choisie est cohérente avec le cas diagnostiqué.

→ Bloc 9

---

### B.12 Bloc 9 — `ticket_contenu` : Contenu du ticket

**Type :** Question checkbox (choix multiple)

**Contenu :**

> **Question 9/12** — Contenu du ticket d'escalade
>
> Vous ouvrez un ticket auprès du fournisseur ou opérateur concerné. Parmi les éléments suivants, **cochez tous ceux qui doivent figurer dans votre ticket** :

**Options (checkbox) :**

1. **Numéro de circuit / identifiant équipement concerné** → +1
2. **Horodatage précis de la détection** → +1
3. **Type de coupure observé (LOS, BGP down, etc.)** → +1
4. **Topologie concernée (sites, NE, liens)** → +1
5. **Criticité déclarée** → +1
6. **Actions déjà entreprises** → +1
7. La couleur du câble physique sur site → 0 (distracteur)
8. L'historique des 6 derniers mois de maintenance → 0 (distracteur)

**Scoring :** `block_ticket_contenu_raw` += 1 par option correcte cochée (max 6), −1 par distracteur coché (plancher 0).

→ Bloc 10

---

### B.13 Bloc 10 — `retablissement_validation` : Validation rétablissement

**Type :** Question checkbox

**Contenu :**

> **Question 10/12** — Validation du rétablissement
>
> L'opérateur transport résout le problème sur son lien. Vous recevez sa confirmation à 03h47.
>
> **Quelles vérifications effectuez-vous pour valider le rétablissement ?** (cocher toutes celles applicables)

**Options :**

1. **Vérifier que les 12 NE repassent en vert sur la topologie EMS** → +2
2. **Vérifier que le dashboard SaaS reçoit à nouveau les heartbeats des équipements du site A** → +2
3. **Tester l'accès supervision depuis au moins 2 postes différents de l'équipe** → +2
4. **Vérifier que les trails / services n'ont pas été impactés via le dashboard SaaS** → +1
5. Redémarrer les NE pour être sûr → 0 (distracteur, risqué)
6. Appeler un collègue pour qu'il vérifie à votre place → 0 (distracteur)

**Scoring :** `block_retablissement_validation_raw` += somme des valeurs des options cochées, max 7.

→ Bloc 11

---

### B.14 Bloc 11 — `cloture_documentation` : Compte-rendu

**Type :** Text input long (zone de texte)

**Contenu :**

> **Question 11/12** — Compte-rendu d'incident
>
> L'incident est clôturé. Rédigez votre compte-rendu pour le ticket interne. Il doit comporter :
>
> - La chronologie (détection → qualification → diagnostic → actions → rétablissement)
> - La cause racine identifiée
> - Les SOPs mobilisées
> - La voie d'escalade utilisée
>
> (champ libre, max 2000 caractères)

**Scoring par détection de mots-clés (via Set Variable + Condition Typebot) :**

- Contient un horodatage (détection regex `\d{2}:\d{2}`) → +2
- Contient les mots "détection" ou "qualification" ou "diagnostic" → +1
- Contient "cause racine" ou "cause" → +1
- Contient "SOP" ou référence à une procédure → +2
- Contient "escalade" ou "opérateur" → +2
- Longueur > 300 caractères → +1
- Longueur > 600 caractères → +1

Max `block_cloture_documentation_raw` = 10.

**Sous-bloc communication support client (Question radio) :**

> Avez-vous envoyé un message de clôture "supervision rétablie" au support client ?

1. Oui, avec horodatage et périmètre → +0 (déjà compté dans `info_support_client`, évite double comptage)
2. Non, pas nécessaire → 0

→ Bloc 12

---

### B.15 Bloc 12 — `post_mortem_decision` : Décision post-mortem

**Type :** Question radio

**Contenu :**

> **Question 12/12** — Décision post-mortem
>
> L'incident a duré de 02h11 à 03h47 (durée : **1h36**).
>
> Déclenchez-vous un post-mortem ?

1. **Oui, durée > 1h (critère déclencheur) — je rédige et partage avec l'équipe de management**
   - `block_post_mortem_decision_raw` += 4
2. Oui, par principe, pour tout incident
   - `block_post_mortem_decision_raw` += 2 (zèle, mais pas la logique normée)
3. Non, la cause est connue (opérateur transport), pas utile
   - `block_post_mortem_decision_raw` += 1
4. Non, on verra en réunion d'équipe
   - `block_post_mortem_decision_raw` += 0

→ Bloc 13 (auto-évaluation)

---

### B.16 Blocs 13-16 — Auto-évaluations

**Type :** Question rating / number input (échelle 0-100)

Chaque bloc suit le même modèle. Présentation avec slider ou saisie numérique.

**Bloc 13 — `self_eval_diagnostic` :**

> **Auto-évaluation 1/4 — Confiance sur votre diagnostic**
>
> Sur une échelle de 0 à 100, comment évaluez-vous la qualité de votre diagnostic dans cette simulation ?
>
> (0 = très faible, 100 = excellente)

- `Set Variable` : `self_eval_comp_reseau_diagnostic_oob` = {{reponse}}

**Bloc 14 — `self_eval_procedural` :**

> **Auto-évaluation 2/4 — Maîtrise des procédures (MOP / SOP)**
>
> Sur 0-100, comment évaluez-vous votre maîtrise des procédures sur cette intervention ?

- `Set Variable` : `self_eval_comp_procedural_mop_identification` = {{reponse}}

**Bloc 15 — `self_eval_stress` :**

> **Auto-évaluation 3/4 — Gestion du stress**
>
> Sur 0-100, comment avez-vous géré le stress / la charge cognitive pendant cette intervention ?

- `Set Variable` : `self_eval_comp_cog_gestion_stress` = {{reponse}}

**Bloc 16 — `self_eval_documentation` :**

> **Auto-évaluation 4/4 — Qualité de votre documentation**
>
> Sur 0-100, comment évaluez-vous la qualité de votre compte-rendu d'incident ?

- `Set Variable` : `self_eval_comp_qual_documentation` = {{reponse}}

→ Bloc Webhook

---

### B.17 Bloc Webhook — Envoi à SimuBot

**Type :** Webhook

**Configuration :**

- **URL :** `{{SIMUBOT_URL}}/api/webhook/typebot-complete`
  (à remplacer par l'URL réelle de l'instance SimuBot)
- **Méthode :** `POST`
- **Headers :**
  - `Content-Type: application/json`
  - `X-Simubot-Signature: {{webhook_signature}}`

**Body (JSON) :**

```json
{
  "assignment_id": "{{assignment_id}}",
  "user_id": "{{user_id}}",
  "launch_token": "{{launch_token}}",
  "mode": "{{mode}}",
  "typebot_result_id": "{{result_id}}",
  "completed_at": "{{timestamp}}",
  "blocks": {
    "block_detection_raw": {{block_detection_raw}},
    "block_mop_identification_raw": {{block_mop_identification_raw}},
    "block_qualification_perimetre_raw": {{block_qualification_perimetre_raw}},
    "block_info_support_client_raw": {{block_info_support_client_raw}},
    "block_sop_diagnostic_identification_raw": {{block_sop_diagnostic_identification_raw}},
    "block_diag_infra_supervision_raw": {{block_diag_infra_supervision_raw}},
    "block_diag_reseau_oob_raw": {{block_diag_reseau_oob_raw}},
    "block_sop_escalade_identification_raw": {{block_sop_escalade_identification_raw}},
    "block_ticket_contenu_raw": {{block_ticket_contenu_raw}},
    "block_retablissement_validation_raw": {{block_retablissement_validation_raw}},
    "block_cloture_documentation_raw": {{block_cloture_documentation_raw}},
    "block_post_mortem_decision_raw": {{block_post_mortem_decision_raw}}
  },
  "self_evals": {
    "self_eval_comp_reseau_diagnostic_oob": {{self_eval_comp_reseau_diagnostic_oob}},
    "self_eval_comp_procedural_mop_identification": {{self_eval_comp_procedural_mop_identification}},
    "self_eval_comp_cog_gestion_stress": {{self_eval_comp_cog_gestion_stress}},
    "self_eval_comp_qual_documentation": {{self_eval_comp_qual_documentation}}
  },
  "context": {
    "cas_diagnostique": "{{cas_diagnostique}}",
    "heure_detection": "{{heure_detection}}"
  }
}
```

**Gestion de la réponse :** Typebot peut ignorer le contenu de la réponse. SimuBot renvoie 200 OK en cas de succès.

→ Bloc Redirect

---

### B.18 Bloc Redirect — Retour vers SimuBot

**Type :** Redirect

**Configuration :**

- **URL :** `{{SIMUBOT_URL}}/attempt/by-assignment/{{assignment_id}}/result`

Ce bloc ferme le scénario et renvoie le candidat vers SimuBot qui affichera le résultat consolidé (scores par compétence, feedbacks pédagogiques, écart d'auto-évaluation).

---

## Partie C — Référentiel des compétences utilisées

À créer dans SimuBot avant publication du scénario. Peut servir de point de départ pour compléter le référentiel global.

### Domaine : Technique Réseau Optique (`dom_reseau_optique`)

| Code compétence | Libellé | Catégorie |
|---|---|---|
| `comp_reseau_alarme_identification` | Identification d'alarme réseau | Diagnostic |
| `comp_reseau_qualification_perimetre` | Qualification périmètre d'incident | Diagnostic |
| `comp_reseau_diagnostic_infra` | Diagnostic infrastructure supervision | Diagnostic |
| `comp_reseau_diagnostic_oob` | Diagnostic réseau OOB | Diagnostic |

### Domaine : Procédural (`dom_procedural`)

| Code compétence | Libellé | Catégorie |
|---|---|---|
| `comp_procedural_mop_identification` | Identification MOP applicable | Application procédures |
| `comp_procedural_sop_identification` | Identification SOP diagnostic | Application procédures |
| `comp_procedural_sop_escalade` | Identification SOP d'escalade | Application procédures |
| `comp_procedural_decision_cas` | Décision de cas diagnostiqué | Jugement procédural |
| `comp_procedural_validation_retablissement` | Validation rétablissement par procédure | Application procédures |
| `comp_procedural_cloture` | Clôture et post-mortem | Application procédures |

### Domaine : Qualité d'exécution (`dom_qualite`)

| Code compétence | Libellé | Catégorie |
|---|---|---|
| `comp_qual_horodatage` | Horodatage précis | Rigueur |
| `comp_qual_documentation` | Qualité documentation | Documentation |
| `comp_qual_ticket_contenu` | Qualité contenu ticket escalade | Documentation |
| `comp_qual_verification` | Vérification post-action | Rigueur |
| `comp_qual_post_mortem` | Rédaction post-mortem | Documentation |

### Domaine : Relationnel (`dom_relationnel`)

| Code compétence | Libellé | Catégorie |
|---|---|---|
| `comp_rel_communication_support` | Communication équipe support | Communication interne |

### Domaine : Cognitif (`dom_cognitif`)

| Code compétence | Libellé | Catégorie |
|---|---|---|
| `comp_cog_gestion_stress` | Gestion du stress en incident | Comportemental |
| `comp_cog_synthese_diagnostic` | Synthèse et analyse | Raisonnement |

---

## Partie D — Glossaire anonymisé (à adapter à votre organisation)

Ce glossaire liste les termes génériques utilisés dans le scénario et leur équivalent probable dans une organisation réelle. À adapter en cohérence avec le vocabulaire interne.

| Terme générique scénario | Équivalent typique |
|---|---|
| Équipe support client | Cellule de coordination clientèle / NOC client |
| EMS primaire / secondaire | Serveur de management d'éléments réseau |
| Dashboard SaaS | Outil de supervision cloud / monitoring externe |
| Fournisseur Alpha | Constructeur des NE optiques |
| Fournisseur Beta | Infrastructure partner supervision |
| Opérateur Transport 1 / 2 | Opérateurs fibre tierce |
| Site A / Site B | Sites techniques distincts (à nommer selon convention) |
| Site-A-EMS-01 | Serveur EMS du site A |
| NE | Network Element (équipement optique terminal) |
| RCP | Carte de contrôle du NE |
| OOB | Réseau Out Of Band de gestion |
| SOP-10 à SOP-22 | SOP internes numérotées (à mapper sur votre référentiel) |
| M0.20 | Code MOP (à mapper sur votre convention) |

---

## Partie E — Notes d'implémentation

### E.1 Ordre de création

1. Créer le référentiel compétences dans SimuBot (domaines, catégories, compétences) via l'interface admin
2. Créer le scénario Typebot dans l'éditeur Typebot en suivant la partie B
3. Noter le `typebot_public_id` généré par Typebot
4. Placer le fichier YAML dans le dépôt Git scénarios (ou importer via interface) après mise à jour du `typebot_public_id`
5. Publier le scénario (passage en état `publie`)
6. Tester en prévisualisation avec un token admin (ne génère pas d'attempt)
7. Assigner à un candidat pilote en mode `exam`

### E.2 Variantes futures

Ce scénario peut être dérivé en plusieurs versions pour éviter la mémorisation :

- **Variante B** : même structure, cas racine = cas B (infra supervision HS au lieu d'opérateur transport)
- **Variante C** : cas C (compte d'authentification bloqué)
- **Variante D** : cas D (certificat NE expiré)
- **Variante E** : cas E (carte de contrôle NE défaillante)

Chaque variante a son propre slug, son propre YAML, et son propre public_id Typebot, mais elles peuvent toutes appartenir au même `pool de remédiation` sur les compétences réseau optique + procédural.

### E.3 Calibration du scoring

Les scores max bruts proposés sont indicatifs. À ajuster après les premiers passages :

- Si tous les candidats obtiennent > 90% sur un bloc → bloc trop facile, ajouter des distracteurs
- Si moins de 30% obtiennent > 50% → bloc trop dur ou ambigu, revoir la formulation

Ce suivi qualité est disponible dans le dashboard admin SimuBot (14.7 du CDC) — encart "Qualité des scénarios".

### E.4 Mode terrain

Pour une exécution en mode `terrain`, certains blocs changent légèrement de posture :

- Bloc 1 détection : remplacer "Vous recevez" par "Vous avez reçu — cochez ce qui correspond à votre situation"
- Bloc 7 diagnostic : "Cochez le cas que vous avez diagnostiqué sur cette intervention réelle"
- Bloc 11 compte-rendu : le texte saisi est directement le compte-rendu du ticket réel
- Blocs d'auto-évaluation : identiques

La variable `mode` injectée dans l'URL permet à Typebot de changer dynamiquement le texte de chaque bloc via des conditions.

---

*Template SimuBot — Scénario Perte de Supervision — v1.0*