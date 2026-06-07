# REX MOP Machinery 2026-04-13

## FAIT et fonctionnel

### Infrastructure
- Caddy : mop.ewutelo.cloud (viewer public) + mop-dl.ewutelo.cloud (PDFs public) + mop-build.ewutelo.cloud (builder VPN-only)
- mop-dl sert /opt/javisi/data/mop/pdf/
- template.html depose dans /opt/javisi/data/mop/pdf/template.html — https://mop-dl.ewutelo.cloud/template.html

### n8n workflows
- mop-route (kQRrDB7w5wfqWIrG) : PUBLIE. Retourne sops, sops_csv, total, incident_id
- mop-get (FFIkjYMyxLdHroAN) : fonctionnel, GET ?sop_id=&sops_list=&idx= retourne formatted_display, next_sop, is_last
- mop-generate (jtvnpjvxc3RjnIwA) : fonctionnel. Gotenberg OK. PDF accessible sur mop-dl.

### Typebot bot (cmnue3spm00051drwymwqg57l)
- mop-noc-v2.json corrige : bodyPath rvm_csv = data.sops_csv (ancienne valeur = expression JS invalide)
- Draft + published ont les bons bodyPaths (verifie via API /publishedTypebot)
- ACT 1 + ACT 2 : qualification, appel mop-route, "3 procedures identifiees" OK
- mop-get bien appele par Typebot (execution 12093 = success dans n8n)

---

## BUG ACTIF : ACT 3 formatted_display vide

mop-get est execute (n8n success) mais le bot affiche le bouton sans texte SOP.

Hypothese prioritaire : var_sop_id non extrait correctement depuis var_sops_csv.
Le bloc b_set_sop_id utilise peut-etre une expression Typebot invalide pour split/index.
mop-get recoit sop_id vide -> retourne peut-etre vide.

A verifier : ouvrir execution 12093 dans n8n builder -> voir query params recus.
Si sop_id vide : corriger b_set_sop_id dans mop-noc-v2.json.

## Reste a faire
- Fix ACT 3 (voir ci-dessus)
- Valider boucle 3 SOPs complete
- ACT 4 : resolution + commentaires + duree
- ACT 5 : trigger mop-generate, verifier pdf_url, verifier PDF sur mop-dl
- Commit mop-noc-v2.json (bodyPath fix pas encore commite)

---

## Erreurs rencontrees

| Erreur | Cause | Fix |
|--------|-------|-----|
| mop-route sans sops_csv en prod | R10 : workflow_history pas mis a jour, n8n execute depuis history pas entity | Cliquer Publish dans n8n UI |
| var_sops_csv vide Typebot | bodyPath avec expression JS invalide (Typebot = lodash dot-notation uniquement) | Remplacer par data.sops_csv |
| PATCH 404 | Typebot utilise PATCH pas PUT | Utiliser PATCH |
| Publish API 404 | POST /publish non expose dans API publique Typebot | Passer par UI builder |
| Builder publie ancien draft | Si builder ouvert pendant PATCH, "Publish" peut publier version en memoire | Fermer/reouvrir builder avant Publish |
| Playwright URL affiche MailHog | Bug metadata MCP Playwright | Ignorer metadata URL, se fier au snapshot |
| SSH IP directe bloque | R7 LOI OP : utiliser Tailscale 100.64.0.14 | Remplacer IP par Tailscale |
| Permission denied /opt/javisi/data/mop/pdf/ | Owner debian != mobuone | sudo tee |

---

## Pour reprendre

1. n8n > mop-get > executions > cliquer 12093 > voir query params (sop_id vide ou non ?)
2. Si vide : corriger b_set_sop_id dans scripts/typebot/mop-noc-v2.json
3. PATCH Typebot depuis builder browser + Publish
4. Relancer E2E Playwright complet
