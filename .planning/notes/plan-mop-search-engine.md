# Plan — Moteur de recherche MOP/SOP
> Session parallèle autonome — tout le contexte est ici, aucune question à poser.
> Date : 2026-04-14

---

## Objectif

Construire un outil de recherche MOP/SOP utilisable par un technicien NOC :
- Saisir une alarme Lightsoft, un domaine, ou une criticité
- Obtenir instantanément : MOP de référence + liste des SOPs à appliquer

**Deux livrables :**
- **V1** — Fichier Excel autonome (openpyxl, Python)
- **V2** — Microsoft Forms + Power Automate (plan de câblage, pas d'accès M365 requis)

---

## Contexte et sources de données

### Sources à lire en priorité

| Fichier | Contenu utile |
|---------|--------------|
| `/home/mobuone/VPAI/docs/mop-incidents-alignment.yml` | 47 incidents × 5 familles, colonnes: `Alarme Lightsoft`, `Criticité`, `Categorie`, SOP chains par incident |
| `/home/mobuone/VPAI/scripts/n8n-workflows/mop-route.json` | Matrice **domaine × criticité → SOPs** (node "SOP Matrix") — source de vérité du routing |
| `/home/mobuone/VPAI/scripts/n8n-workflows/mop-get.json` | 13 SOPs actuelles avec titres + résumés (node "SOP Data") |
| `/home/mobuone/VPAI/.planning/notes/sop-rationalisation-2026-04-13.md` | Plan fusion 13→9 SOPs + mapping old→new IDs |
| `/home/mobuone/VPAI/incidents-otn-oob-v2.xlsx` | 47 incidents source (Row1=titre, Row2=note, Row3=headers, Row4+=data) |

### Données clés extraites

**Domaines (mop-route.json)** : SUPERVISION, PHOTONIQUE, CARTE SERVICE, CARTE MANAGEMENT, CARTE INFRA, CHASSIS, PORT NNI, PORT UNI

**Criticités** : MINEUR, MAJEUR, CRITIQUE

**Familles MOP** :
- M0.20 — SUPERVISION (`OPSSD-03.03.M0.20-P-V1`)
- M0.21 — PHOTONIQUE (`OPSSD-03.03.M0.21-P-V1`)
- M0.22 — CARTE (`OPSSD-03.03.M0.22-P-V1`)
- M0.23 — CHASSIS (`OPSSD-03.03.M0.23-P-V1`)
- M0.24 — PORT NNI/UNI (`OPSSD-03.03.M0.24-P-V1`)

**SOPs cibles (après fusion 13→9)** :
- SOP-01 `S0.10` — Vérification OOB & accès management
- SOP-02 `S0.11` — Reset GCC / OSPF Ribbon
- SOP-03 `S0.12` — Escalade Ribbon TAC
- SOP-04 `S0.13` — Diagnostic signal OTN (OSNR + FEC/BER) ← fusion SOP-04+05
- SOP-05 `S0.14` — PM Counters OTN ← fusion SOP-11+12
- SOP-06 `S0.15` — Remplacement matériel (carte + SFP) ← fusion SOP-06+07
- SOP-07 `S0.16` — Bascule OLP ← ex SOP-10
- SOP-08 `S0.17` — Validation Viavi post-restauration ← ex SOP-13
- SOP-09 `S0.18` — Diagnostic firewall Lugos ← ex SOP-09

**Mapping old→new IDs pour la matrice :**
```
SOP-01 → SOP-01 | SOP-02 → SOP-02 | SOP-03 → SOP-03 | SOP-04 → SOP-04
SOP-05 → SOP-04 | SOP-06 → SOP-06 | SOP-07 → SOP-06 | SOP-08 → SOP-01
SOP-09 → SOP-09 | SOP-10 → SOP-07 | SOP-11 → SOP-05 | SOP-12 → SOP-05
SOP-13 → SOP-08
```

---

## V1 — Excel autonome

### Architecture du fichier

4 onglets :

**Onglet 1 — `Recherche`** (onglet actif, accès technicien)
```
┌─────────────────────────────────────────────────────────┐
│  🔍 RECHERCHE MOP / SOP                                  │
│                                                          │
│  Alarme / Mot-clé : [__________________________]  ← B3  │
│  Domaine           : [Tous ▼]  ← liste déroulante  B5   │
│  Criticité         : [Tous ▼]  ← liste déroulante  B7   │
│                                                          │
│  [Résultats — filtrés en temps réel via formules]        │
│                                                          │
│  Alarme  | Domaine | Criticité | MOP | SOPs | Résumé SOP │
└─────────────────────────────────────────────────────────┘
```

Mécanisme : formule `FILTER()` sur la feuille DB.
- B3 = texte libre → `ISNUMBER(SEARCH($B$3, DB[Alarme]))` (insensible casse)
- B5 = dropdown domaine → filtre exact ou "Tous"
- B7 = dropdown criticité → filtre exact ou "Tous"
- Combinaison : `FILTER(DB, condition1 * condition2 * condition3)`
- Si 0 résultats : message "Aucun incident trouvé — vérifier l'orthographe ou saisir 'Tous'"

**Onglet 2 — `DB`** (masqué, source de vérité)

Colonnes : `Alarme_Lightsoft | Domaine | Criticite | Famille_MOP | Ref_MOP | Titre_MOP | SOPs_Anciens | SOPs_Nouveaux | SOPs_Refs_OPSSD | Titres_SOPs | Nb_SOPs`

Construit depuis :
1. Parse `mop-route.json` → matrice domaine × criticité → SOPs
2. Convertir anciens IDs → nouveaux via mapping
3. Pour chaque incident du YAML : colonne Alarme_Lightsoft + famille
4. Jointure alarme ↔ domaine ↔ SOPs

**Onglet 3 — `Légende SOPs`** (référence rapide)

Tableau : Nouvel ID | Ref OPSSD | Titre | Domaine | Description courte
(les 9 SOPs cibles)

**Onglet 4 — `Mode d'emploi`**

Instructions en 5 lignes + légende couleurs.

### Styles

- Header zone recherche : bleu foncé (#1F3864), texte blanc
- Cellules résultats MOP : vert clair (#C6EFCE)
- Cellules résultats SOPs : violet clair (#D9B8FF)
- Ligne zéro résultat : orange (#F4B942) avec message

### Livrable V1

```
/home/mobuone/VPAI/docs/mop-sop-search.xlsx
```

Uploader sur `drop.ewutelo.cloud/mop-sop-search.xlsx` après génération.

### Script Python de génération

Utiliser `openpyxl`. Le script :
1. Lit `mop-route.json` → extrait la MATRIX JS avec `re.findall`
2. Lit `mop-incidents-alignment.yml` → extrait incidents avec `yaml.safe_load`
3. Lit `mop-get.json` → extrait titres SOPs
4. Construit la table DB (une ligne par couple alarme × domaine × criticité)
5. Génère les 4 onglets avec formules FILTER et listes déroulantes (`DataValidation`)
6. Sauvegarde + upload drop

**Note FILTER()** : openpyxl écrit les formules comme chaînes — Excel les évalue à l'ouverture.
Écrire exactement : `=IFERROR(FILTER(DB!A2:K200, (DB!A2:A200<>"")*...),{"Aucun résultat","","","","","","","","","",""})`

---

## V2 — Microsoft Forms + Power Automate

> Plan de câblage — ne nécessite pas d'accès M365 pour être rédigé.
> Implémenter quand l'accès SharePoint/Forms est disponible.

### Architecture

```
[Microsoft Forms]
       ↓  (trigger)
[Power Automate — Flow "NOC MOP Search"]
       ↓
[Excel Online (SharePoint)] — lit DB sheet de mop-sop-search.xlsx
       ↓
[Adaptive Card / Email] — retourne résultats
```

### Formulaire Forms (3 champs)

| Champ | Type | Options |
|-------|------|---------|
| Intitulé alarme ou mot-clé | Texte court | Libre |
| Domaine | Choix unique | SUPERVISION / PHOTONIQUE / CARTE SERVICE / CARTE MANAGEMENT / CARTE INFRA / CHASSIS / PORT NNI / PORT UNI / Je ne sais pas |
| Criticité | Choix unique | MINEUR / MAJEUR / CRITIQUE / Je ne sais pas |

### Flow Power Automate

```
Trigger: "When a new response is submitted" (Forms)
  ↓
Action: "Get response details" (Forms)
  ↓
Action: "List rows present in a table" (Excel Online)
  - Fichier: mop-sop-search.xlsx (SharePoint)
  - Table: DB
  - Filter Query: Alarme_Lightsoft eq '[alarme]' OR Domaine eq '[domaine]'
  ↓
Action: Compose — construire la réponse HTML
  - MOP : [Ref_MOP] — [Titre_MOP]
  - SOPs à appliquer : [SOPs_Nouveaux] — [Titres_SOPs]
  ↓
Condition: "Je ne sais pas" dans domaine OU criticité
  - Oui → renvoyer TOUTES les lignes matchant l'alarme
  - Non → filtrer domaine + criticité
  ↓
Action: "Send an email" OU "Post adaptive card to Teams"
  - Destinataire: email soumis dans le form (ou canal Teams NOC)
  - Corps: résultats formatés
```

### Adaptive Card Teams (optionnel)

```json
{
  "type": "AdaptiveCard",
  "body": [
    {"type": "TextBlock", "text": "🔍 Résultat MOP/SOP", "size": "Large", "weight": "Bolder"},
    {"type": "FactSet", "facts": [
      {"title": "MOP", "value": "OPSSD-03.03.M0.20-P-V1 — Supervision OTN"},
      {"title": "SOPs", "value": "SOP-01 → SOP-02 → SOP-05"},
      {"title": "Criticité", "value": "MAJEUR"}
    ]}
  ]
}
```

### Prérequis M365 pour implémenter V2

- [ ] Accès Power Automate (licence M365 Business Basic minimum)
- [ ] `mop-sop-search.xlsx` uploadé sur SharePoint (pas juste OneDrive)
- [ ] Table Excel nommée "DB" (Insert > Table dans Excel)
- [ ] Canal Teams NOC ou adresse email NOC pour les réponses

---

## Ordre d'exécution pour la session parallèle

1. **Lire** les 4 fichiers sources (mop-route.json, mop-incidents-alignment.yml, mop-get.json, sop-rationalisation.md)
2. **Construire** la table DB en mémoire (Python dict)
3. **Générer** `docs/mop-sop-search.xlsx` (openpyxl)
4. **Tester** : vérifier que les formules FILTER sont syntaxiquement correctes
5. **Uploader** sur `drop.ewutelo.cloud/mop-sop-search.xlsx`
6. **Rédiger** le plan V2 en bas du fichier ou dans un onglet dédié Excel
7. **Commiter** : `docs(mop): add mop-sop search engine excel v1`

---

## Contraintes techniques

- Python openpyxl pour la génération (pas de VBA — incompatible ARM64/Linux)
- Formules FILTER() requièrent Excel 365 / Excel 2021 (pas LibreOffice)
- Upload : `curl -s -T <file> https://drop.ewutelo.cloud/<filename>`
- Commit hook : sujet ≤ 72 chars, pas de heredoc, format `type(scope): subject`
- LOI R0 : si sujet n8n → `search_memory.py --query "n8n"` avant tout Write

---

*Plan rédigé le 2026-04-14 — prêt pour spawn session parallèle*
