# Commandes pour le premier déploiement

## Étape 1 : Chiffrer le vault

```bash
# Activer le venv
source .venv/bin/activate

# Lancer le script de chiffrement
bash encrypt_vault.sh
```

**Résultat attendu** :
- ✓ `inventory/group_vars/all/secrets.yml` créé et chiffré
- Premières lignes doivent contenir `$ANSIBLE_VAULT;1.1;AES256`

## Étape 2 : Vérifier le vault

```bash
# Voir le contenu déchiffré
ansible-vault view inventory/group_vars/all/secrets.yml --vault-id default@.vault_password
```

**Vérifier que toutes les valeurs sont correctes** :
- IPs, domaines, tokens
- Pas de `<...>` ou de placeholders
- Les mots de passe générés automatiquement sont présents

## Étape 3 : Déployer

```bash
# Lancer le déploiement
make deploy-prod
```

Ansible va :
1. Se connecter au VPS sur le **port 22** (défaut)
2. Exécuter tous les rôles dans l'ordre
3. Le rôle `hardening` va configurer le **port SSH custom (804)**
4. Les prochains déploiements devront utiliser : `make deploy-prod -e ansible_port_override=804`

## En cas d'erreur

### Si "vault-id" error pendant le déploiement

```bash
# Vérifier la configuration
ansible-config dump | grep -i vault
```

Doit afficher :
```
DEFAULT_VAULT_IDENTITY_LIST(/chemin/ansible.cfg) = ['default@.vault_password']
```

### Si "Connection refused" sur port 804

C'est normal au premier déploiement ! Le VPS écoute sur le port 22.
Ansible se connecte automatiquement sur le port 22 grâce à la configuration dans `inventory/hosts.yml`.

### Si "localhost 127.0.0.1"

Le vault n'existe pas ou n'est pas chiffré correctement.
Vérifier : `file inventory/group_vars/all/secrets.yml`

## Après le premier déploiement réussi

Les déploiements suivants doivent utiliser le port SSH custom :

```bash
make deploy-prod -e ansible_port_override=804
```

OU modifier `inventory/hosts.yml` pour utiliser le port 804 par défaut après le premier déploiement.
