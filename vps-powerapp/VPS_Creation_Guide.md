# Guide de création — VPS Telehouse Power Apps Canvas App
> Import unique sur make.powerapps.com — suivre exactement dans l'ordre.
> Durée estimée : 45–60 min.

---

## Prérequis — Créer la liste SharePoint AVANT d'ouvrir Power Apps

1. Ouvrir [SharePoint Online](https://votre-tenant.sharepoint.com) sur le PC professionnel
2. Naviguer vers le site SharePoint de votre équipe (ex: `sites/TeleHouse`)
3. `+ Nouveau` → `Liste` → `Liste vide`
4. Nom : **VPS_Audits** → Créer

### Colonnes à créer (dans cet ordre)

| Colonne | Type | Options |
|---------|------|---------|
| `Site` | Choix | Valeurs : `TH2`, `TH3` |
| `Technicien` | Ligne de texte unique | — |
| `Auditeur` | Ligne de texte unique | — |
| `DateVisite` | Date et heure | Format : Date uniquement |
| `TypeIntervention` | Ligne de texte unique | — |
| `TypeIdx` | Nombre | Min: 0, Max: 8 |
| `Remarque` | Plusieurs lignes de texte | — |
| `EPIResultsJSON` | Plusieurs lignes de texte | Texte brut |
| `StatutGlobal` | Choix | Valeurs : `Conforme`, `Non-conforme`, `Partiel` |

> La colonne `Title` existe déjà par défaut — ne pas la supprimer.

---

## Étape 1 — Créer l'application

1. Ouvrir [make.powerapps.com](https://make.powerapps.com)
2. `+ Créer` → `Application vide` → `Application de canevas vide`
3. Format : **Téléphone** (mobile-first, 780px)
4. Nom de l'application : **VPS Telehouse**
5. Cliquer `Créer`

---

## Étape 2 — Connecter SharePoint

1. Volet gauche → `Données` (icône cylindre) → `+ Ajouter des données`
2. Rechercher "SharePoint" → sélectionner
3. Entrer l'URL de votre site SharePoint (ex: `https://votre-tenant.sharepoint.com/sites/TeleHouse`)
4. Sélectionner la liste **VPS_Audits** → `Connecter`

---

## Étape 3 — App.OnStart (collections statiques)

1. Cliquer sur `App` dans l'arborescence (volet gauche)
2. Dans la barre de formule, sélectionner `OnStart`
3. Coller le bloc complet depuis `VPS_PowerFx_Source.txt` → section `APP.OnStart`

```
Bloc à coller : depuis "ClearCollect(colTechsTH2," jusqu'à "Clear(varEPIResults);"
```

4. Cliquer `✓` pour valider — pas d'erreur = OK

---

## Étape 4 — Renommer les écrans

Power Apps crée 1 écran par défaut. En créer 3 de plus :

1. Volet gauche → icône `+` (Nouvel écran) × 3 → type **Vide**
2. Nommer les 4 écrans (clic droit → Renommer) :
   - `Screen1`
   - `Screen2`
   - `Screen3`
   - `Screen4`

---

## Étape 5 — Screen1 : Informations générales

### Composants à créer

**Header** (Rectangle)
- Fill : `RGBA(0, 30, 64, 1)`
- Y: 0, Height: 60, Width: Parent.Width
- Ajouter un Label dedans : `"Informations générales (1/4)"` — White, Bold

**Label "Site"** — texte `"Site *"`

**DropdownSite**
- Items : `["TH2", "TH3"]`
- OnChange : `Set(varSite, DropdownSite.SelectedText.Value); Set(varTechnicien, "")`

**Label "Technicien"** — texte `"Technicien audité *"`

**DropdownTechnicien**
- Items : `If(varSite = "TH2", colTechsTH2, colTechsTH3)`
- OnChange : `Set(varTechnicien, DropdownTechnicien.SelectedText.Nom)`

**Label "Auditeur"** — texte `"Auditeur *"`

**DropdownAuditeur**
- Items : `colAuditeurs`
- OnChange : `Set(varAuditeur, DropdownAuditeur.SelectedText.Nom)`

**Label "Date"** — texte `"Date de la visite *"`

**DatePickerDate** (contrôle Date Picker)
- DefaultDate : `Today()`
- OnChange : `Set(varDate, DatePickerDate.SelectedDate)`

**Label "Remarque"** — texte `"Remarque (optionnel)"`

**TextInputRemarque** (zone de texte multi-lignes)
- Mode : `TextMode.MultiLine`
- OnChange : `Set(varRemarque, TextInputRemarque.Text)`

**BtnSuivant1** (Bouton)
- Text : `"Suivant →"`
- Fill : `RGBA(27, 79, 155, 1)`
- Color : `White`
- DisplayMode :
  ```
  If(varSite <> "" && varTechnicien <> "" && varAuditeur <> "", DisplayMode.Edit, DisplayMode.Disabled)
  ```
- OnSelect : `Navigate(Screen2, ScreenTransition.Cover)`

---

## Étape 6 — Screen2 : Type d'intervention

### Composants à créer

**Header** (Rectangle)
- Fill : `RGBA(0, 30, 64, 1)`
- Label : `"Type d'intervention (2/4)"`

**GalleryTypes** (Gallery Vertical)
- Items : `colTypesIntervention`
- TemplateSize : `72`
- Dans chaque cellule :
  - Rectangle `RectType` : Fill = `ColorValue(ThisItem.Couleur)`, Width = 8, Height = Parent.TemplateHeight
  - Label `LabelType` : Text = `ThisItem.Label`, X = 20, FontWeight = Bold, Color = `RGBA(0,30,64,1)`
  - Circle `CircleSelected` : Visible = `ThisItem.TypeIdx = varTypeIdx`, Fill = `RGBA(27,79,155,1)`, radius 12
- OnSelect : `Set(varTypeIdx, ThisItem.TypeIdx)`

**BtnRetour2**
- Text : `"← Retour"`
- OnSelect : `Navigate(Screen1, ScreenTransition.UnCover)`

**BtnSuivant2**
- Text : `"Suivant →"`
- Fill : `RGBA(27, 79, 155, 1)`
- DisplayMode : `If(varTypeIdx >= 0, DisplayMode.Edit, DisplayMode.Disabled)`
- OnSelect :
  ```
  ClearCollect(
    varEPIResults,
    AddColumns(
      Filter(colEPIDef, TypeIdx = varTypeIdx),
      "Etat", "Bon",
      "Porte", "OUI"
    )
  );
  Navigate(Screen3, ScreenTransition.Cover)
  ```

---

## Étape 7 — Screen3 : Vérification EPI

### Composants à créer

**HeaderDynamique** (Rectangle)
- Fill : `ColorValue(LookUp(colTypesIntervention, TypeIdx = varTypeIdx, Couleur))`
- Height : 60
- Label dedans : `LookUp(colTypesIntervention, TypeIdx = varTypeIdx, Label) & " (3/4)"`
- Color : White

**GalleryEPI** (Gallery Vertical)
- Items : `varEPIResults`
- TemplateSize : `90`
- Dans chaque cellule :
  - Rectangle `RectBgEPI` : Fill = `If(ThisItem.IsReco, RGBA(255,248,200,1), RGBA(249,249,254,1))`, Width = Parent.Width
  - Label `LabelEPILabel` :
    - Text = `If(ThisItem.IsReco, ThisItem.Label & " (R)", ThisItem.Label)`
    - FontStyle = `If(ThisItem.IsReco, FontStyle.Italic, FontStyle.Normal)`
  - DropdownEtat :
    - Items = `["Bon", "Mauvais"]`
    - Default = `ThisItem.Etat`
    - OnChange = `Patch(varEPIResults, ThisItem, {Etat: DropdownEtat.SelectedText.Value})`
  - DropdownPorte :
    - Items = `["OUI", "NON"]`
    - Default = `ThisItem.Porte`
    - OnChange = `Patch(varEPIResults, ThisItem, {Porte: DropdownPorte.SelectedText.Value})`

**BtnRetour3**
- OnSelect : `Navigate(Screen2, ScreenTransition.UnCover)`

**BtnSuivant3**
- Text : `"Suivant →"`
- OnSelect : `Navigate(Screen4, ScreenTransition.Cover)`

---

## Étape 8 — Screen4 : Récapitulatif et validation

### Composants à créer

**Header** (Rectangle)
- Fill : `RGBA(0, 30, 64, 1)`
- Label : `"Récapitulatif (4/4)"`

**LabelStatut** (grand texte centré)
- Text :
  ```
  If(
    CountIf(varEPIResults, Etat = "Mauvais") = 0, "Conforme ✓",
    If(CountIf(varEPIResults, Etat = "Mauvais") = CountRows(varEPIResults), "Non-conforme ✗", "Partiel ⚠")
  )
  ```
- Color :
  ```
  If(CountIf(varEPIResults, Etat = "Mauvais") = 0, Color.Green,
    If(CountIf(varEPIResults, Etat = "Mauvais") = CountRows(varEPIResults), Color.Red, Color.Orange))
  ```

**Section infos** (4 Labels) :
- `"Site : " & varSite`
- `"Technicien : " & varTechnicien`
- `"Auditeur : " & varAuditeur`
- `"Date : " & Text(varDate, "dd/mm/yyyy")`
- `"Type : " & LookUp(colTypesIntervention, TypeIdx = varTypeIdx, Label)`
- `If(varRemarque <> "", "Remarque : " & varRemarque, "")`

**GalleryRecap** (Gallery Vertical)
- Items : `varEPIResults`
- TemplateSize : 55
- Dans chaque cellule :
  - `If(ThisItem.IsReco, ThisItem.Label & " (R)", ThisItem.Label)`
  - `ThisItem.Etat` — Color = `If(ThisItem.Etat = "Bon", Color.Green, Color.Red)`
  - `ThisItem.Porte` — Color = `If(ThisItem.Porte = "OUI", Color.Green, Color.Red)`

**BtnEnregistrer** (bouton primaire)
- Text : `"Enregistrer dans SharePoint"`
- Fill : `RGBA(0, 30, 64, 1)`
- OnSelect : coller le bloc `BtnEnregistrer > OnSelect` depuis `VPS_PowerFx_Source.txt`

**BtnNouveau**
- Text : `"Nouvelle saisie"`
- OnSelect : coller le bloc `BtnNouveau > OnSelect` depuis `VPS_PowerFx_Source.txt`

**BtnRetour4**
- OnSelect : `Navigate(Screen3, ScreenTransition.UnCover)`

---

## Étape 9 — Configurer le connecteur SharePoint dans BtnEnregistrer

Dans la formule `Patch(VPS_Audits, ...)`, Power Apps doit résoudre `VPS_Audits`.
Si soulignement rouge :
1. Vérifier que l'étape 2 (connexion SharePoint) est bien faite
2. Dans le volet `Données`, vérifier que `VPS_Audits` est listé
3. Supprimer et re-ajouter la connexion si nécessaire

---

## Étape 10 — Test avant publication

### Tests dans le Studio (bouton ▶)

| Test | Résultat attendu |
|------|-----------------|
| Screen1 → sélectionner TH2 | DropdownTechnicien affiche 14 noms TH2 uniquement |
| Screen1 → sélectionner TH3 | DropdownTechnicien affiche 8 noms TH3 uniquement |
| Bouton Suivant1 grisé | Si Site/Technicien/Auditeur vides |
| Screen2 → cliquer type 0 | Cercle de sélection apparaît sur type 0 |
| Screen2 → Suivant | Screen3 affiche 5 EPI (type 0) |
| Screen3 → mettre "Mauvais" sur 1 EPI | Screen4 → StatutGlobal = "Partiel ⚠" |
| Screen3 → mettre "Mauvais" sur tous | Screen4 → StatutGlobal = "Non-conforme ✗" |
| Screen4 → Enregistrer | Notification "Audit enregistré avec succès !" |
| Vérifier SharePoint | Nouvelle ligne dans VPS_Audits |

---

## Étape 11 — Publication et partage

1. `Fichier` → `Enregistrer` → nommer `VPS Telehouse`
2. `Fichier` → `Publier` → `Publier cette version`
3. Pour partager avec l'équipe :
   - `Accueil` → `Applications` → trouver `VPS Telehouse`
   - `...` → `Partager`
   - Ajouter les utilisateurs ou groupes AD concernés
4. L'app est aussi accessible via **Microsoft Teams** :
   - Teams → `Applications` → `Power Apps` → rechercher `VPS Telehouse`
   - Épingler dans la barre latérale pour accès rapide

---

## Points d'attention (réseau G-Zero / Zscaler)

- Toutes les opérations se font dans le navigateur — pas de téléchargement requis
- La connexion SharePoint est native M365 — pas bloquée par Zscaler
- Si un pop-up OAuth est bloqué : désactiver le bloqueur de pop-ups pour `make.powerapps.com`
- Pas de connecteur premium utilisé — M365 E3 suffit

---

## Questions en suspens (décisions utilisateur)

| # | Question | Défaut conseillé |
|---|----------|-----------------|
| 1 | Export PDF | Guide manuel : imprimer l'écran → Ctrl+P → PDF |
| 2 | Site SharePoint cible | À préciser (URL du tenant) |
| 3 | Signature auditeur | Non — hors scope V1 |
