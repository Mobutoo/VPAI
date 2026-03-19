# Waza VPAI Repo Setup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Installer le repo VPAI sur le RPi "waza" (192.168.1.8 / Tailscale 100.64.0.1) avec GitHub sync, venv Ansible et tout le nécessaire pour que Claude CLI sur waza travaille directement dessus.

**Architecture:** Setup SSH direct via Tailscale — connexion en `mobuone@100.64.0.1`, configuration `~/.ssh/config` avec alias `github-seko`, clone du repo en `/home/mobuone/VPAI`, venv Python + Ansible. Pas de nouveau role Ansible (setup one-shot).

**Tech Stack:** SSH, Git, Python venv, Ansible, ansible-vault

---

## Contexte & Prérequis

- Pi accessible via Tailscale : `ssh -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1`
- La clé `~/.ssh/seko-vpn-deploy` EST DÉJÀ sur le Pi (dans `~/.ssh/`)
- GitHub remote : `git@github-seko:Mobutoo/VPAI.git`
- Git email : `seko.mobutoo@gmail.com`
- Vault password fichier WSL : `/home/asus/seko/VPAI/.vault_password`
- Toutes les commandes SSH se lancent depuis WSL

---

### Task 1 : Renommer le hostname en `waza`

**Files:** aucun fichier local modifié (action sur le Pi)

**Step 1 : Renommer hostname**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "sudo hostnamectl set-hostname waza"
```

**Step 2 : Mettre à jour /etc/hosts**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "sudo sed -i 's/workstation-pi/waza/g' /etc/hosts; grep waza /etc/hosts"
```

**Step 3 : Vérifier**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 "hostname"
```

Expected: `waza`

---

### Task 2 : Configurer SSH client pour GitHub (`github-seko` alias)

**Step 1 : Vérifier que la clé seko-vpn-deploy existe sur le Pi**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "ls -la ~/.ssh/seko-vpn-deploy* 2>/dev/null || echo 'KEY_MISSING'"
```

Expected: fichier `seko-vpn-deploy` présent (pas KEY_MISSING).
Si KEY_MISSING : copier via `scp -i ~/.ssh/seko-vpn-deploy ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1:~/.ssh/` (cas rare).

**Step 2 : Créer ~/.ssh/config sur le Pi**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 "cat > ~/.ssh/config << 'EOF'
Host github-seko
    HostName github.com
    User git
    IdentityFile ~/.ssh/seko-vpn-deploy
    IdentitiesOnly yes

Host *
    ServerAliveInterval 60
    ServerAliveCountMax 3
EOF
chmod 600 ~/.ssh/config"
```

**Step 3 : Ajouter github.com aux known_hosts**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null; sort -u ~/.ssh/known_hosts -o ~/.ssh/known_hosts"
```

**Step 4 : Tester la connexion GitHub**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "ssh -T github-seko 2>&1 || true"
```

Expected: `Hi Mobutoo! You have successfully authenticated...`

---

### Task 3 : Cloner le repo VPAI

**Step 1 : Vérifier si repo déjà cloné**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "test -d /home/mobuone/VPAI/.git && echo 'ALREADY_CLONED' || echo 'NOT_CLONED'"
```

**Step 2 : Cloner (si NOT_CLONED)**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "git clone git@github-seko:Mobutoo/VPAI.git /home/mobuone/VPAI"
```

**Step 3 : Si ALREADY_CLONED — vérifier remote et faire un pull**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "cd /home/mobuone/VPAI && git remote -v && git pull"
```

---

### Task 4 : Configurer Git user dans le repo

**Step 1 : Configurer user.name et user.email**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "cd /home/mobuone/VPAI && git config user.name 'Mobuone' && git config user.email 'seko.mobutoo@gmail.com'"
```

**Step 2 : Configurer git globalement aussi**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "git config --global user.name 'Mobuone' && git config --global user.email 'seko.mobutoo@gmail.com' && git config --global init.defaultBranch main"
```

**Step 3 : Vérifier**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "cd /home/mobuone/VPAI && git log --oneline -3"
```

Expected: 3 derniers commits visibles.

---

### Task 5 : Créer le venv Python + installer Ansible

**Step 1 : Créer le venv**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "python3 -m venv /home/mobuone/VPAI/.venv"
```

**Step 2 : Installer les packages**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "/home/mobuone/VPAI/.venv/bin/pip install --upgrade pip ansible ansible-lint yamllint"
```

**Step 3 : Installer les collections Ansible**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "/home/mobuone/VPAI/.venv/bin/ansible-galaxy collection install community.general community.docker ansible.posix"
```

**Step 4 : Vérifier**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "source /home/mobuone/VPAI/.venv/bin/activate && ansible --version | head -3"
```

Expected: `ansible [core 2.16+]` ou supérieur.

---

### Task 6 : Copier le fichier vault secrets.yml

Le fichier `secrets.yml` est chiffré (Ansible Vault) — il peut être copié en clair sans risque car il reste chiffré.

**Step 1 : Copier secrets.yml depuis WSL vers le Pi**

```bash
scp -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy \
  /home/asus/seko/VPAI/inventory/group_vars/all/secrets.yml \
  mobuone@100.64.0.1:/home/mobuone/VPAI/inventory/group_vars/all/secrets.yml
```

**Step 2 : Copier .vault_password**

```bash
scp -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy \
  /home/asus/seko/VPAI/.vault_password \
  mobuone@100.64.0.1:/home/mobuone/VPAI/.vault_password
```

**Step 3 : Vérifier que le vault est lisible**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "/home/mobuone/VPAI/.venv/bin/ansible-vault view /home/mobuone/VPAI/inventory/group_vars/all/secrets.yml \
  --vault-password-file /home/mobuone/VPAI/.vault_password 2>/dev/null | head -5"
```

Expected: Variables vault visibles (pas d'erreur de décryptage).

---

### Task 7 : Mettre à jour l'inventaire Ansible (hostname waza)

**Files:**
- Modify: `inventory/group_vars/all/main.yml` — changer `workstation_pi_hostname`

**Step 1 : Editer main.yml localement (depuis WSL)**

Changer la ligne `workstation_pi_hostname: "workstation-pi"` en `workstation_pi_hostname: "waza"`.

**Step 2 : Commit**

```bash
cd /home/asus/seko/VPAI && git add inventory/group_vars/all/main.yml && \
git commit -m "feat(workstation): rename Pi hostname to waza"
```

**Step 3 : Push vers GitHub**

```bash
cd /home/asus/seko/VPAI && git push git@github-seko:Mobutoo/VPAI.git main
```

**Step 4 : Pull sur waza pour vérifier la synchronisation**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "cd /home/mobuone/VPAI && git pull && git log --oneline -2"
```

---

### Task 8 : Vérification finale end-to-end

**Step 1 : Test SSH → GitHub**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "ssh -T github-seko 2>&1 || true"
```

**Step 2 : Test git pull depuis waza**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "cd /home/mobuone/VPAI && git status && git log --oneline -3"
```

**Step 3 : Test ansible --version et vault decrypt**

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.1 \
  "source /home/mobuone/VPAI/.venv/bin/activate && cd /home/mobuone/VPAI && ansible --version | head -1 && ansible-vault view inventory/group_vars/all/secrets.yml --vault-password-file .vault_password 2>/dev/null | grep vault_domain | head -1"
```

**Step 4 : Résumé du succès**

Si toutes les commandes passent sans erreur → setup complet. Waza est prêt pour que Claude CLI travaille directement sur VPAI.

---

## Notes importantes

- **WSL prefix** : toutes les commandes `ssh`, `scp`, `git` lancées depuis WSL doivent être préfixées de `wsl -e bash -c '...'` si appelées depuis un agent Windows. Les agents Bash dans ce projet tournent dans WSL donc le prefix n'est pas nécessaire.
- **Tailscale doit être actif** sur la machine Windows pour atteindre `100.64.0.1`
- **Le .vault_password ne doit jamais être commité** (déjà dans .gitignore)
