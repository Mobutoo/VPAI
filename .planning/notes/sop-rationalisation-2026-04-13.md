# SOP Rationalisation — État finalisé 2026-04-14

> Statut : **VALIDÉ** — fusion 13→8 appliquée (mop-get.json, mop-route.json, generate-mop-sop-search.py)
> Source authoritative : `drop.ewutelo.cloud/align/sop-alignment-review.xlsx` (onglet "New SOPs × incidents types")

---

## Résultat : 13 SOPs → 8 SOPs

| New ID | Réf OPSSD | Titre | Absorbe (anciens IDs) |
|--------|-----------|-------|----------------------|
| 10-SOP | OPSSD-03.03.S0.10-SOP | Vérification OOB & Accès management | SOP-01 + SOP-02 + SOP-08 + SOP-09 |
| 11-SOP | OPSSD-03.03.S0.11-SOP | Analyse Optique SFP | SOP-05 + SOP-11 + SOP-12 |
| 12-SOP | OPSSD-03.03.S0.12-SOP | Test Viavi E2E | SOP-08 + SOP-13 |
| 13-SOP | OPSSD-03.03.S0.13-SOP | Remplacement matériel (carte + SFP) | SOP-06 + SOP-07 |
| 14-SOP | OPSSD-03.03.S0.14-SOP | Diagnostic signal OTN (OSNR + FEC/BER) | SOP-04 + SOP-07 (OLP) |
| 15-SOP | OPSSD-03.03.S0.15-SOP | Escalade Constructeur (Ribbon) | SOP-03 |
| 16-SOP | OPSSD-03.03.S0.16-SOP | Escalade Supervision (Lugos) | SOP-10 |
| 17-SOP | OPSSD-03.03.S0.17-SOP | Escalade Opérateur | NEW |

**Supprimé :** SOP-02 (Reset GCC / OSPF Ribbon) — absorbé dans 10-SOP

---

## Décisions de fusion

| Fusion | Justification |
|--------|---------------|
| SOP-01 + SOP-08 + SOP-09 → 10-SOP | OOB Cogent et firewall Lugos = sous-cas du check accès universel |
| SOP-02 supprimé | Reset GCC couvert par check accès 10-SOP + escalade 15-SOP |
| SOP-05 + SOP-11 + SOP-12 → 11-SOP | PM Counters = Analyse Optique SFP — même flux diagnostic |
| SOP-04 + SOP-07 → 14-SOP | Bascule OLP = cas particulier du diagnostic signal OTN |
| SOP-06 + SOP-07 → 13-SOP | Pattern identique : identify → spare → ESD → insert → validate |
| SOP-03 → 15-SOP | Renommé "Escalade Constructeur" — scope élargi |
| SOP-10 → 16-SOP | Rebaptisé "Escalade Supervision Lugos" (bascule OLP dans 14-SOP) |
| — → 17-SOP | Nouvelle SOP : escalade opérateur (Cogent/EuNetwork) — manquait |

---

## Format référence

```
OPSSD-03.03.S0.[10-17]-SOP
```
- `OPSSD` : Service Technique
- `03.03` : Code processus
- `S0` : Type SOP (vs M0 pour MOP)
- `.10 → .17` : numéros 1→8
- `-SOP` : suffixe (remplace `-P-V1` de l'ancienne convention)

---

## Fichiers mis à jour (2026-04-14)

- `scripts/generate-mop-sop-search.py` — MAPPING_OLD_NEW + SOP_NEW
- `scripts/n8n-workflows/mop-route.json` — MATRIX nœud "SOP Matrix"
- `scripts/n8n-workflows/mop-get.json` — nœud "SOP Data"

## À faire (restant)

- [ ] Valider les 8 nouvelles SOPs avec un technicien NOC
- [ ] Documenter les SOPs avec les vrais seuils ITU-T / Ribbon
- [ ] Implémenter les blocs GrapeJS dans wizy (en-tête SOP, tableau seuils, décision post-SOP)
- [ ] Mettre à jour `docs/sop-alignment-review.xlsx` (remplacer par version drop)

---

*Analyse initiale : 2026-04-13 | Finalisation : 2026-04-14 | Source : drop.ewutelo.cloud/align/sop-alignment-review.xlsx*
