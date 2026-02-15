#!/bin/bash
set -e

echo "=== Chiffrement du vault ==="
echo ""

# Vérifier que le venv est actif
if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ ERREUR: Le venv n'est pas actif"
    echo "   Lance 'source .venv/bin/activate' d'abord"
    exit 1
fi

# Vérifier que le fichier source existe
if [ ! -f /tmp/secrets.yml ]; then
    echo "❌ ERREUR: /tmp/secrets.yml n'existe pas"
    exit 1
fi

# Chiffrer avec la syntaxe qui fonctionne
echo "Chiffrement en cours..."
ansible-vault encrypt /tmp/secrets.yml \
  --encrypt-vault-id=default \
  --vault-password-file .vault_password \
  --output inventory/group_vars/all/secrets.yml

if [ $? -eq 0 ]; then
    echo "✓ Vault chiffré avec succès !"
    echo ""
    echo "Vérification du fichier..."
    file inventory/group_vars/all/secrets.yml
    echo ""
    echo "Premières lignes (doit contenir \$ANSIBLE_VAULT;1.1;AES256) :"
    head -3 inventory/group_vars/all/secrets.yml
    echo ""
    echo "✓ Pour voir le contenu déchiffré :"
    echo "  ansible-vault view inventory/group_vars/all/secrets.yml --vault-id default@.vault_password"
else
    echo "❌ Erreur lors du chiffrement"
    exit 1
fi
