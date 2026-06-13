# archive/

Composants retirés du périmètre actif du dépôt mais conservés pour référence
historique. **Non déployés, non testés, non maintenus.**

| Élément | Provenance | Raison de l'archivage |
|---------|-----------|------------------------|
| `flash-studio-complete/` | ancien `FS/flash-studio-complete/` | Sous-projet Ansible autonome (rôles `sd-*`) jamais référencé par les playbooks VPAI. Brouillait la frontière infra/produit (cf. `docs/audits/2026-04-11-vpai-repo-audit-v2.md`). |

Pour réactiver un élément, le sortir de `archive/` et le recâbler explicitement
dans un playbook + la CI.
