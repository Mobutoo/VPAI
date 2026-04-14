# Phase 3 — VPS Telehouse Power Apps Canvas App
> Plan autonome — peut être lancé dans une session parallèle sans contexte préalable.
> Toutes les données de référence sont embarquées ici.

---

## 0. Contexte global

**Projet** : Digitalisation de la VPS (Visite Prévention Sécurité) Telehouse  
**Phase 1** : Fiche Excel individuelle fillable — LIVREE V4 (`drop.ewutelo.cloud/Simu/VPS_Fiche_Saisie_V4.xlsx`)  
**Phase 2** : Microsoft Forms JSON (session parallèle)  
**Phase 3** : Power Apps Canvas App (ce document)  

**Contrainte critique** : L'utilisateur est sur un réseau d'entreprise **G-Zero / Zscaler**.  
→ Import unique sur `make.powerapps.com` — pas d'aller-retour possible.  
→ Build complet en local (RPi waza) → livraison d'un `.msapp` prêt à importer.  
→ Tests : validation syntaxique + preview local uniquement. Pas de tenant live.

**Licence M365** : E3 — Canvas Apps + connecteurs standard (SharePoint, Excel, Office 365 Users) inclus. **Zéro premium connector** autorisé.

---

## 1. Design de référence — Stitch

**Project ID** : `10620473155392717268`  
**URL MCP** : `mcp__stitch__list_screens` avec `projectId: "10620473155392717268"`

### Screens (ordre logique 1→4)

| # | Titre | Screen ID |
|---|-------|-----------|
| 1 | Informations générales (1/4) | `958de4e6313d414e9e5f15bb43f7b24c` |
| 2 | Type d'intervention (2/4) | `dda64813cf6f48c88cf11f7fd5181f07` |
| 2b | Type d'intervention (2/4) - Corrected | `dcd805a7fb1a4ab79c9a772ec6efa086` |
| 3 | Vérification EPI (3/4) | `249ceaf0743a41b3a78837acb8d7d78e` |
| 4a | Récapitulatif et validation (4/4) | `7f45105ce25f42668c88e92697619b11` |
| 4b | Récapitulatif et export (Corrected) | `306c9fa63ffe44cfbfdf88facc1f9c4f` |
| 1b | Informations générales (Corrected) | `6beec46b3e1d42599b0cf7c8551497e4` |

**Utiliser les versions "Corrected"** pour les écrans 1, 2, 4. Pour récupérer le HTML/screenshot :
```
mcp__stitch__get_screen projectId=10620473155392717268 screenId=<id>
```

### Design System (extrait clé)

```
Palette principale :
  primary    : #001E40  (bleu marine — header, boutons primaires)
  secondary  : #003366  (bleu intermédiaire)
  accent     : #1B4F9B  (bouton nav)
  surface    : #F9F9FE  (fond app)
  surface-low: #F4F3F8  (sections)
  white      : #FFFFFF  (inputs)
  border     : #E0E0E0  (bords légers)

Règle fondamentale : NO-LINE — pas de borders 1px pour délimiter sections.
Boundaries = background color shifts uniquement.

Typographie : Inter (système M365)
Mode : Light, Mobile-first 780px wide
```

---

## 2. Données métier complètes

### Sites
```
TH2, TH3
```

### Techniciens par site

**TH2** (14 personnes) :
```
Florian RIAUD, Yassin SELKA, Jerome GRAND'HAYE, Zacharie SAIDANI,
Guillaume CANAL, Rachid BENGHILAS, Aissa MESSAOUDI, Christophe RENE,
Binh VU, Mel LASME, Lyes AMGHAR, Boukary GASSAMA,
Sofiane DE ALMEIDA SANTOS, Abdel YAKOUT
```

**TH3** (8 personnes) :
```
Gabriel ALONSO, Khaled AMGHAR, Chris BENDA, Adel DOUALANE,
Michael LE ROUX, Martin REUMAUX, Sathees THURAIRAJAH, Rayan SAHIRI
```

### Auditeurs (5 personnes)
```
Brigitte GOMES, Erwin MOMBILI, Hassan BELLAHCEN,
Zakaria IMAGHRI, Stephanie DOLAK
```

### Types d'intervention (9)
```
0: Installation/Retrait d'equipement.
1: Reboot electrique.
2: Disjonction de rack client.
3: Tirage a plus de 2m de hauteur.
4: Tirage en faux plancher.
5: Manutention de charges lourdes.
6: Gestions des stocks.
7: Utilisation du transpalette.
8: Test avec un laser.
```

### EPI par type (36 EPI total)
Format: `(type_idx, label, is_recommandation)`  
`is_recommandation=True` → fond jaune pâle, italique, "(R)" en suffixe

```
(0, "Chaussure de securite.",         obligatoire)
(0, "Gant anti-coupure.",              obligatoire)
(0, "Casque anti-bruit.",              obligatoire)
(0, "Leve-serveur au-dela de 2U.",    obligatoire)
(0, "Port du PTI.",                    RECOMMANDATION)
(1, "Chaussure de securite.",          obligatoire)
(1, "Gant anti-coupure.",              obligatoire)
(1, "Casque anti-bruit.",              RECOMMANDATION)
(1, "Port du PTI.",                    RECOMMANDATION)
(2, "Habilitation electrique.",        obligatoire)
(2, "Chaussure de securite.",          obligatoire)
(2, "Port du PTI.",                    RECOMMANDATION)
(3, "Chaussure de securite.",          obligatoire)
(3, "Gants anti-coupure.",             obligatoire)
(3, "Lunettes anti-poussiere.",        obligatoire)
(3, "Casquette de protection.",        obligatoire)
(3, "Utilisation d'une PIRL.",         RECOMMANDATION)
(3, "Port du PTI.",                    RECOMMANDATION)
(4, "Chaussure de securite.",          obligatoire)
(4, "Gants anti-coupure.",             obligatoire)
(4, "Lunettes anti-poussiere.",        obligatoire)
(4, "Casquette de protection.",        obligatoire)
(4, "Ventouse.",                        RECOMMANDATION)
(4, "Port du PTI.",                    RECOMMANDATION)
(5, "Chaussure de securite.",          obligatoire)
(5, "Gants anti-coupure.",             obligatoire)
(5, "Port du PTI.",                    RECOMMANDATION)
(6, "Chaussure de securite.",          obligatoire)
(6, "Utilisation d'une gazelle.",      obligatoire)
(6, "Gants anti-coupure.",             obligatoire)
(6, "Port du PTI.",                    RECOMMANDATION)
(7, "Chaussure de securite.",          obligatoire)
(7, "Gants anti-coupure.",             obligatoire)
(8, "Chaussure de securite.",          obligatoire)
(8, "Lunettes de protection laser.",   obligatoire)
(8, "Port du PTI.",                    RECOMMANDATION)
```

### Couleurs des headers de type
```
Type 0: #1B4F9B   Type 1: #155A6C   Type 2: #4A3580
Type 3: #1A6B43   Type 4: #7A3510   Type 5: #5C1A4A
Type 6: #2E6060   Type 7: #8B4A00   Type 8: #1A4A6B
```

### Validations
- **État EPI** : `Bon` / `Mauvais`
- **Porté** : `OUI` / `NON`

---

## 3. Architecture Power Apps

### Flux utilisateur (4 écrans)

```
[Screen1: Infos générales]
  → Site (dropdown: TH2/TH3)
  → Technicien audité (dropdown filtré par Site)
  → Auditeur (dropdown)
  → Date (date picker, défaut = Today())
  → Remarque (texte optionnel)
  [Suivant →]

[Screen2: Type d'intervention]
  → Sélection type parmi 9 (gallery ou radio)
  [Suivant →]

[Screen3: Vérification EPI]
  → Liste filtrée par type sélectionné
  → Chaque EPI : label + dropdown État (Bon/Mauvais) + dropdown Porté (OUI/NON)
  → Recommandations : fond jaune, badge "(R)"
  [Suivant →]

[Screen4: Récapitulatif + Export]
  → Tableau récap de tous les EPI saisis
  → Bouton "Enregistrer" → SharePoint List
  → Bouton "Exporter PDF" → Power Automate (si configuré) ou screenshot guide
  [Valider]
```

### Variables globales (Power Fx)
```powerfx
varSite          // "TH2" ou "TH3"
varTechnicien    // nom technicien
varAuditeur      // nom auditeur
varDate          // date (default Today())
varRemarque      // texte libre
varTypeIdx       // 0-8 = index type intervention
varEPIResults    // collection: {TypeIdx, EPILabel, IsReco, Etat, Porte}
```

### SharePoint List cible : `VPS_Audits`
À créer manuellement dans SharePoint avant import Power Apps.

| Colonne | Type SP | Notes |
|---------|---------|-------|
| Title | Single line | Auto (requis SP) — utiliser comme ID unique |
| Site | Choice | TH2, TH3 |
| Technicien | Single line | |
| Auditeur | Single line | |
| DateVisite | Date | |
| TypeIntervention | Single line | label complet |
| TypeIdx | Number | 0-8 |
| Remarque | Multi-line | optionnel |
| EPIResultsJSON | Multi-line | JSON stringifié de la collection EPI |
| StatutGlobal | Choice | Conforme, Non-conforme, Partiel |

**Calcul StatutGlobal** (Power Fx) :
```powerfx
If(
  CountIf(varEPIResults, Etat = "Mauvais") = 0,
  "Conforme",
  If(
    CountIf(varEPIResults, Etat = "Mauvais") = CountRows(varEPIResults),
    "Non-conforme",
    "Partiel"
  )
)
```

---

## 4. Données statiques dans l'app (pas de SharePoint requis pour les listes)

Les listes (techs, auditeurs, EPIs) sont embarquées comme collections statiques dans `OnStart` de l'app — **pas de connecteur externe nécessaire** :

```powerfx
// OnStart de App
ClearCollect(colTechsTH2,
  {Nom: "Florian RIAUD"}, {Nom: "Yassin SELKA"},
  {Nom: "Jerome GRAND'HAYE"}, {Nom: "Zacharie SAIDANI"},
  ...
);
ClearCollect(colTechsTH3,
  {Nom: "Gabriel ALONSO"}, {Nom: "Khaled AMGHAR"},
  ...
);
ClearCollect(colAuditeurs,
  {Nom: "Brigitte GOMES"}, {Nom: "Erwin MOMBILI"},
  ...
);
ClearCollect(colEPIDef,
  {TypeIdx: 0, Label: "Chaussure de securite.", IsReco: false},
  {TypeIdx: 0, Label: "Gant anti-coupure.", IsReco: false},
  ...
);
```

---

## 5. Méthode de build — pac CLI sur RPi

### Prérequis (à installer sur waza si absent)
```bash
# Power Platform CLI
curl -Lo pac.tar.gz https://aka.ms/PowerAppsCLI/linux/pac.tar.gz
mkdir -p ~/.pac && tar -xzf pac.tar.gz -C ~/.pac
export PATH="$PATH:$HOME/.pac"

# Vérification
pac --version
```

### Structure de projet YAML
```
vps-powerapp/
├── CanvasManifest.json      # metadata app
├── Src/
│   ├── App.pa.yaml          # App-level (OnStart collections)
│   ├── Screen1.pa.yaml      # Informations générales
│   ├── Screen2.pa.yaml      # Type d'intervention
│   ├── Screen3.pa.yaml      # Vérification EPI
│   └── Screen4.pa.yaml      # Récapitulatif
├── DataSources/
│   └── VPS_Audits.json      # SharePoint list connector def
└── Themes/
    └── VPS_Theme.json       # Palette Stitch (#001E40 etc.)
```

### Build → .msapp
```bash
cd vps-powerapp/
pac canvas pack --sources Src/ --msapp ../VPS_PowerApp.msapp
```

### Validation syntaxique (sans tenant)
```bash
pac canvas validate --msapp VPS_PowerApp.msapp
# Sortie attendue : "No issues found" ou liste d'erreurs Power Fx
```

### Livraison
```bash
# Upload vers dufs pour téléchargement par l'utilisateur
curl -T VPS_PowerApp.msapp https://drop.ewutelo.cloud/Simu/VPS_PowerApp.msapp
# URL résultante : https://drop.ewutelo.cloud/Simu/VPS_PowerApp.msapp
```

---

## 6. Import par l'utilisateur (one-shot)

Instructions à donner à l'utilisateur :

1. Ouvrir `make.powerapps.com` sur le PC professionnel (Teams/M365)
2. **Avant l'import** : créer la liste SharePoint `VPS_Audits` avec les colonnes listées en §3
3. `Apps` → `Importer une application de canevas` → sélectionner `VPS_PowerApp.msapp`
4. Dans l'assistant d'import : mapper le connecteur `VPS_Audits` vers la liste SharePoint créée
5. Cliquer `Importer` → attendre confirmation
6. Ouvrir l'app depuis `make.powerapps.com` pour vérification
7. Partager via Teams : `Applications` → `VPS Telehouse` → `Partager`

---

## 7. Stratégie de test (sans tenant)

### Tests réalisables sur RPi (avant livraison)

| Test | Outil | Commande |
|------|-------|---------|
| Syntaxe Power Fx | pac validate | `pac canvas validate --msapp VPS_PowerApp.msapp` |
| Structure YAML | yamllint | `yamllint Src/*.pa.yaml` |
| Collections complètes | grep count | vérifier que 36 EPI + 9 types sont dans App.pa.yaml |
| Cohérence données | Python script | script de cross-check type_idx vs EPI_ROWS |

### Tests post-import (par l'utilisateur)
1. Screen 1 : sélectionner TH2 → vérifier que seuls les 14 techs TH2 apparaissent
2. Screen 1 : sélectionner TH3 → vérifier que seuls les 8 techs TH3 apparaissent
3. Screen 2 : sélectionner type 0 ("Installation...") → Screen 3 doit montrer 5 EPI
4. Screen 3 : mettre un EPI en "Mauvais" → Screen 4 doit montrer StatutGlobal = "Partiel"
5. Screen 4 : cliquer "Enregistrer" → vérifier que l'enregistrement apparaît dans SharePoint

---

## 8. Fichiers de référence à lire au démarrage de la session

| Fichier | Pourquoi |
|---------|----------|
| `/tmp/build_vps_form.py` | Source de vérité des données EPI (si encore présent) |
| `/home/mobuone/VPAI/scripts/n8n-workflows/vps-generate.json` | Batch n8n déjà existant (peut inspirer la logique) |
| Ce fichier | Tout le reste |

### Commande de récupération Stitch (si besoin de revoir les écrans)
```python
# Via MCP dans Claude Code
mcp__stitch__get_screen(
  name="projects/10620473155392717268/screens/<SCREEN_ID>",
  projectId="10620473155392717268",
  screenId="<SCREEN_ID>"
)
```

Screenshots disponibles directement via les `downloadUrl` retournées par `list_screens`.

---

## 9. Checklist de livraison

> **Note** : pac CLI est incompatible Linux (PE32 net48 Windows-only). Pivot vers livraison Power Fx + guide.

- [x] ~~`pac` CLI installé sur waza~~ — Non viable sur ARM64 Linux (net48 PE32)
- [x] ~~Structure YAML~~  — Remplacé par source Power Fx copy-paste
- [x] Collections statiques complètes — 14+8 techs, 5 auditeurs, 36 EPI dans `VPS_PowerFx_Source.txt`
- [x] Filtrage technicien par site — `If(varSite = "TH2", colTechsTH2, colTechsTH3)` documenté
- [x] EPI Gallery filtrée par TypeIdx — `Filter(colEPIDef, TypeIdx = varTypeIdx)` documenté
- [x] Calcul StatutGlobal correct — formule complète dans `VPS_PowerFx_Source.txt`
- [x] Connecteur SharePoint `VPS_Audits` — colonnes définies dans `VPS_Creation_Guide.md`
- [x] ~~`pac canvas validate`~~ — 48/48 vérifications Python passent (`validate_vps_data.py`)
- [x] Livrables uploadés sur `drop.ewutelo.cloud/Simu/` :
  - `VPS_PowerFx_Source.txt` — toutes les formules Power Fx (copy-paste ready)
  - `VPS_Creation_Guide.md` — guide screen-by-screen make.powerapps.com
  - `validate_vps_data.py` — script de validation données (48/48 PASS)
- [x] Instructions import fournies dans `VPS_Creation_Guide.md`

---

## 10. Décisions en suspens (à confirmer avec l'utilisateur)

1. **Export PDF** : Power Automate (flow séparé, nécessite connexion) ou guide manuel (Imprimer → PDF) ?
2. **SharePoint site** : quel site SharePoint cible pour la liste `VPS_Audits` ? (URL du tenant)
3. **Nom de l'app** dans M365 : "VPS Telehouse" ou autre ?
4. **Signature auditeur** : dans le récapitulatif, faut-il un champ signature électronique ?
