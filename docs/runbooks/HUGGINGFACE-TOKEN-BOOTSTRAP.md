# Hugging Face Token Bootstrap

Objectif: permettre au worker `llamaindex-memory-worker` de telecharger une premiere fois `google/embeddinggemma-300m`, puis d'executer l'inference localement sur Waza.

## 1. Pre-requis

- compte Hugging Face cree
- acces accepte sur `google/embeddinggemma-300m`
- token **read** genere

Source officielle:
- <https://ai.google.dev/gemma/docs/embeddinggemma/inference-embeddinggemma-with-sentence-transformers>
- <https://huggingface.co/google/embeddinggemma-300m>

## 2. Variable Ansible retenue

Variable claire dans le repo:
- `huggingface_token`

Source Vault attendue:
- `vault_huggingface_token`

Mapping:
- [main.yml](/home/mobuone/VPAI/inventory/group_vars/all/main.yml)
- [defaults/main.yml](/home/mobuone/VPAI/roles/llamaindex-memory-worker/defaults/main.yml)

## 3. Ce que fait le role

Le role depose le token dans:
- [memory-worker.env.j2](/home/mobuone/VPAI/roles/llamaindex-memory-worker/templates/memory-worker.env.j2)

Variables exportees:
- `HF_TOKEN`
- `HUGGINGFACE_HUB_TOKEN`

Le fichier rendu cote Waza est en `0600`.

## 4. Ou le modele sera mis en cache

Cache local du worker:
- `/opt/workstation/data/ai-memory-worker/hf-cache`

Une fois telecharge, l'embedding reste local.

## 5. Politique retenue

- ne jamais commiter le token
- ne jamais commiter les poids du modele dans Git
- le token sert uniquement au bootstrap du modele
- l'inference reste locale sur Waza

## 6. Etape suivante

Une fois `vault_huggingface_token` renseigne:

```bash
ansible-playbook playbooks/workstation.yml --tags llamaindex-memory-worker
```

Puis controle pilote:

```bash
ansible-playbook playbooks/workstation.yml --tags llamaindex-memory-worker --check --diff
```
