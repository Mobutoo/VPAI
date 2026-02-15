#!/bin/bash
# Diagnostic des vault-ids Ansible

echo "=========================================="
echo "DIAGNOSTIC VAULT-IDS ANSIBLE"
echo "=========================================="
echo ""

echo "1. Version Ansible :"
ansible --version | head -3
echo ""

echo "2. Fichier .vault_password actuel :"
if [ -f .vault_password ]; then
    echo "✓ Existe ($(wc -c < .vault_password) bytes)"
    echo "  Contenu : $(cat .vault_password)"
else
    echo "✗ N'existe pas"
fi
echo ""

echo "3. Configuration ansible.cfg (vault) :"
grep -A2 "vault" ansible.cfg || echo "Aucune config vault trouvée"
echo ""

echo "4. Test de création avec différentes syntaxes :"
echo ""
echo "   a) Avec --vault-password-file :"
ansible-vault create /tmp/test1.yml --vault-password-file .vault_password 2>&1 | head -5
rm -f /tmp/test1.yml
echo ""

echo "   b) Avec --encrypt-vault-id=default :"
echo "test" | ansible-vault encrypt --encrypt-vault-id=default --vault-password-file .vault_password --output /tmp/test2.yml 2>&1
rm -f /tmp/test2.yml
echo ""

echo "   c) Sans spécifier vault-id :"
echo "test" | ansible-vault encrypt --vault-password-file .vault_password --output /tmp/test3.yml 2>&1
rm -f /tmp/test3.yml
echo ""

echo "5. Vérifier s'il existe d'autres fichiers vault dans le projet :"
find . -name ".vault_*" -o -name "vault_*" 2>/dev/null | grep -v ".venv" | grep -v ".git"
echo ""

echo "6. Configuration active (ansible-config dump) :"
ansible-config dump 2>&1 | grep -i "vault\|password" | head -20
echo ""

echo "=========================================="
echo "FIN DU DIAGNOSTIC"
echo "=========================================="
