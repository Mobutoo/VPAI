# Commandes pour le déploiement

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

### Premier déploiement (VPS neuf, SSH sur port 22)

```bash
make deploy-prod EXTRA_VARS="ansible_port_override=22"
```

Ansible va :
1. Se connecter au VPS sur le **port 22** (override explicite)
2. Exécuter tous les rôles dans l'ordre
3. Le rôle `hardening` va configurer le **port SSH custom (804)**

### Déploiements suivants (SSH déjà sur port 804)

```bash
make deploy-prod
```

Le port SSH est automatiquement lu depuis `prod_ssh_port` (804) dans `inventory/group_vars/all/main.yml`.

> **Note** : La variable `EXTRA_VARS` permet de passer des extra-vars Ansible.
> Exemple : `make deploy-prod EXTRA_VARS="ansible_port_override=22"`

## En cas d'erreur

### Si "Connection refused" ou "Connection timed out"

Vérifier quel port SSH est actif sur le VPS :

```bash
# Tester le port 804 (après hardening)
ssh -p 804 debian@<IP_VPS> echo ok

# Tester le port 22 (VPS neuf)
ssh -p 22 debian@<IP_VPS> echo ok
```

- Si **port 22** répond : `make deploy-prod EXTRA_VARS="ansible_port_override=22"`
- Si **port 804** répond : `make deploy-prod` (défaut)

### Si "vault-id" error pendant le déploiement

```bash
# Vérifier la configuration
ansible-config dump | grep -i vault
```

Doit afficher :
```
DEFAULT_VAULT_IDENTITY_LIST(/chemin/ansible.cfg) = ['default@.vault_password']
```

### Si "localhost 127.0.0.1"

Le vault n'existe pas ou n'est pas chiffré correctement.
Vérifier : `file inventory/group_vars/all/secrets.yml`

## Déployer un rôle spécifique

```bash
make deploy-role ROLE=caddy ENV=prod
make deploy-role ROLE=docker-stack ENV=prod
```

## Commandes utiles sur le VPS

```bash
# Voir les containers
docker ps -a

# Logs d'un container
docker logs javisi_caddy --tail 50
docker logs javisi_postgresql --tail 50

# Redémarrer un container
docker restart javisi_caddy

# Relancer la stack infra
cd /opt/javisi && docker compose -f docker-compose-infra.yml up -d

# Relancer la stack apps
cd /opt/javisi && docker compose -f docker-compose.yml up -d
```
