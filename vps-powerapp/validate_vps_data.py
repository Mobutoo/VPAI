#!/usr/bin/env python3
"""
Validation cross-check des données VPS Telehouse pour Power Apps.
Vérifie la cohérence de toutes les constantes avant déploiement.
"""

# ============================================================
# DONNÉES DE RÉFÉRENCE (miroir de PHASE3-PLAN.md)
# ============================================================

TECHS_TH2 = [
    "Florian RIAUD", "Yassin SELKA", "Jerome GRAND'HAYE", "Zacharie SAIDANI",
    "Guillaume CANAL", "Rachid BENGHILAS", "Aissa MESSAOUDI", "Christophe RENE",
    "Binh VU", "Mel LASME", "Lyes AMGHAR", "Boukary GASSAMA",
    "Sofiane DE ALMEIDA SANTOS", "Abdel YAKOUT"
]

TECHS_TH3 = [
    "Gabriel ALONSO", "Khaled AMGHAR", "Chris BENDA", "Adel DOUALANE",
    "Michael LE ROUX", "Martin REUMAUX", "Sathees THURAIRAJAH", "Rayan SAHIRI"
]

AUDITEURS = [
    "Brigitte GOMES", "Erwin MOMBILI", "Hassan BELLAHCEN",
    "Zakaria IMAGHRI", "Stephanie DOLAK"
]

INTERVENTION_TYPES = {
    0: "Installation/Retrait d'equipement",
    1: "Reboot electrique",
    2: "Disjonction de rack client",
    3: "Tirage a plus de 2m de hauteur",
    4: "Tirage en faux plancher",
    5: "Manutention de charges lourdes",
    6: "Gestions des stocks",
    7: "Utilisation du transpalette",
    8: "Test avec un laser",
}

TYPE_COLORS = {
    0: "#1B4F9B", 1: "#155A6C", 2: "#4A3580",
    3: "#1A6B43", 4: "#7A3510", 5: "#5C1A4A",
    6: "#2E6060", 7: "#8B4A00", 8: "#1A4A6B",
}

# (type_idx, label, is_reco)
EPI_ROWS = [
    (0, "Chaussure de securite.",       False),
    (0, "Gant anti-coupure.",            False),
    (0, "Casque anti-bruit.",            False),
    (0, "Leve-serveur au-dela de 2U.",  False),
    (0, "Port du PTI.",                  True),
    (1, "Chaussure de securite.",        False),
    (1, "Gant anti-coupure.",            False),
    (1, "Casque anti-bruit.",            True),
    (1, "Port du PTI.",                  True),
    (2, "Habilitation electrique.",      False),
    (2, "Chaussure de securite.",        False),
    (2, "Port du PTI.",                  True),
    (3, "Chaussure de securite.",        False),
    (3, "Gants anti-coupure.",           False),
    (3, "Lunettes anti-poussiere.",      False),
    (3, "Casquette de protection.",      False),
    (3, "Utilisation d'une PIRL.",       True),
    (3, "Port du PTI.",                  True),
    (4, "Chaussure de securite.",        False),
    (4, "Gants anti-coupure.",           False),
    (4, "Lunettes anti-poussiere.",      False),
    (4, "Casquette de protection.",      False),
    (4, "Ventouse.",                     True),
    (4, "Port du PTI.",                  True),
    (5, "Chaussure de securite.",        False),
    (5, "Gants anti-coupure.",           False),
    (5, "Port du PTI.",                  True),
    (6, "Chaussure de securite.",        False),
    (6, "Utilisation d'une gazelle.",    False),
    (6, "Gants anti-coupure.",           False),
    (6, "Port du PTI.",                  True),
    (7, "Chaussure de securite.",        False),
    (7, "Gants anti-coupure.",           False),
    (8, "Chaussure de securite.",        False),
    (8, "Lunettes de protection laser.", False),
    (8, "Port du PTI.",                  True),
]

# ============================================================
# VALIDATIONS
# ============================================================

errors = []
ok_count = 0

def check(condition, msg_ok, msg_fail):
    global ok_count
    if condition:
        print(f"  ✓ {msg_ok}")
        ok_count += 1
    else:
        print(f"  ✗ {msg_fail}")
        errors.append(msg_fail)


print("=" * 60)
print("VPS TELEHOUSE — Validation données Power Apps")
print("=" * 60)

# --- Comptes de base ---
print("\n[1] Comptes de base")
check(len(TECHS_TH2) == 14, f"TH2: 14 techniciens", f"TH2: attendu 14, trouvé {len(TECHS_TH2)}")
check(len(TECHS_TH3) == 8,  f"TH3: 8 techniciens",  f"TH3: attendu 8, trouvé {len(TECHS_TH3)}")
check(len(AUDITEURS) == 5,  f"Auditeurs: 5",         f"Auditeurs: attendu 5, trouvé {len(AUDITEURS)}")
check(len(INTERVENTION_TYPES) == 9, "Types: 9",       f"Types: attendu 9, trouvé {len(INTERVENTION_TYPES)}")
check(len(EPI_ROWS) == 36,  f"EPI rows: 36",          f"EPI rows: attendu 36, trouvé {len(EPI_ROWS)}")

# --- Types d'intervention continus 0-8 ---
print("\n[2] Continuité TypeIdx 0-8")
type_indices = sorted(INTERVENTION_TYPES.keys())
check(type_indices == list(range(9)), "TypeIdx 0-8 continus", f"TypeIdx non continus: {type_indices}")

# --- Couleurs définies pour chaque type ---
print("\n[3] Couleurs de header")
for t in range(9):
    check(t in TYPE_COLORS, f"Type {t}: couleur définie ({TYPE_COLORS.get(t, 'MANQUANT')})",
          f"Type {t}: couleur MANQUANTE")

# --- EPI TypeIdx tous dans [0-8] ---
print("\n[4] EPI TypeIdx valides")
epi_type_indices = set(row[0] for row in EPI_ROWS)
check(epi_type_indices == set(range(9)),
      f"EPI couvrent tous les types 0-8",
      f"Types non couverts: {set(range(9)) - epi_type_indices}")

# --- Comptage EPI par type ---
print("\n[5] EPI par type")
from collections import Counter
epi_by_type = Counter(row[0] for row in EPI_ROWS)
expected_counts = {0: 5, 1: 4, 2: 3, 3: 6, 4: 6, 5: 3, 6: 4, 7: 2, 8: 3}
for t, expected in expected_counts.items():
    found = epi_by_type[t]
    check(found == expected, f"Type {t}: {found} EPI", f"Type {t}: attendu {expected}, trouvé {found}")

# --- Pas de doublons dans les techniciens ---
print("\n[6] Doublons techniciens")
check(len(set(TECHS_TH2)) == len(TECHS_TH2), "TH2: pas de doublons", "TH2: DOUBLONS DÉTECTÉS")
check(len(set(TECHS_TH3)) == len(TECHS_TH3), "TH3: pas de doublons", "TH3: DOUBLONS DÉTECTÉS")
# Un technicien ne peut pas être dans les deux sites
overlap = set(TECHS_TH2) & set(TECHS_TH3)
check(len(overlap) == 0, "Pas de tech TH2/TH3 en double", f"Overlap TH2∩TH3: {overlap}")

# --- Pas de doublons dans les auditeurs ---
print("\n[7] Doublons auditeurs")
check(len(set(AUDITEURS)) == len(AUDITEURS), "Auditeurs: pas de doublons", "Auditeurs: DOUBLONS")

# --- Pas de doublons EPI dans un même type ---
print("\n[8] Doublons EPI par type")
for t in range(9):
    labels = [row[1] for row in EPI_ROWS if row[0] == t]
    check(len(set(labels)) == len(labels),
          f"Type {t}: pas de doublons EPI",
          f"Type {t}: EPI dupliqués: {[l for l in labels if labels.count(l) > 1]}")

# --- Cohérence IsReco ---
print("\n[9] Cohérence IsReco (booléen)")
for i, row in enumerate(EPI_ROWS):
    if not isinstance(row[2], bool):
        errors.append(f"EPI ligne {i}: IsReco={row[2]} n'est pas un booléen")
check(len([r for r in EPI_ROWS if not isinstance(r[2], bool)]) == 0,
      "Tous les IsReco sont des booléens", "IsReco non-booléens détectés")

# --- Total EPI obligatoires vs recommandations ---
print("\n[10] Répartition obligatoires / recommandations")
reco_count = sum(1 for r in EPI_ROWS if r[2] is True)
obli_count = sum(1 for r in EPI_ROWS if r[2] is False)
print(f"  ℹ  Obligatoires : {obli_count} / Recommandations (R) : {reco_count}")

# --- Validation format des couleurs ---
print("\n[11] Format des couleurs (#RRGGBB)")
import re
for t, color in TYPE_COLORS.items():
    check(bool(re.match(r'^#[0-9A-Fa-f]{6}$', color)),
          f"Type {t}: {color} format valide",
          f"Type {t}: {color} format INVALIDE")

# ============================================================
# RÉSUMÉ
# ============================================================
print("\n" + "=" * 60)
total_checks = ok_count + len(errors)
if not errors:
    print(f"✓ PASS — {ok_count}/{total_checks} vérifications réussies")
    print("Données prêtes pour Power Apps.")
else:
    print(f"✗ FAIL — {len(errors)} erreur(s) sur {total_checks} vérifications")
    print("\nErreurs :")
    for e in errors:
        print(f"  - {e}")
print("=" * 60)

exit(0 if not errors else 1)
