# Procedure de secours — Lockout SSH

Ce document decrit comment recuperer l'acces a un serveur VPS OVH
si SSH est devenu inaccessible (mauvaise config, VPN down, UFW bloquant).

---

## Symptomes

- `ssh: connect to host X port 2222: Connection refused`
- `ssh: connect to host X port 2222: Connection timed out`
- SSH fonctionne uniquement via IP VPN mais Tailscale est down

---

## Option 1 — Console KVM OVH (rapide)

### Etapes

1. **Acceder a la console OVH**
   - Aller sur <https://www.ovh.com/manager/>
   - Naviguer : Bare Metal Cloud > VPS > votre VPS
   - Cliquer sur l'onglet "Console KVM" (ou "VNC")

2. **Se connecter**
   ```
   Login: deploy  (ou root si premier acces)
   Password: (le mot de passe defini lors de la creation)
   ```

3. **Reparer sshd_config**
   ```bash
   sudo nano /etc/ssh/sshd_config
   ```
   Modifier `ListenAddress` :
   ```
   # Remplacer :
   ListenAddress 100.64.x.x
   # Par :
   ListenAddress 0.0.0.0
   ```

4. **Ouvrir UFW pour SSH public**
   ```bash
   sudo ufw allow 2222/tcp
   sudo ufw reload
   ```

5. **Redemarrer SSH**
   ```bash
   sudo sshd -t  # Valider la config d'abord !
   sudo systemctl restart sshd
   ```

6. **Tester la connexion** depuis votre machine :
   ```bash
   ssh -p 2222 deploy@IP_PUBLIQUE_VPS
   ```

---

## Option 2 — Mode Rescue OVH

Si la console KVM ne fonctionne pas ou si le systeme ne boot plus.

### Etapes

1. **Activer le mode Rescue**
   - OVH Manager > VPS > onglet "Reboot"
   - Selectionner "Reboot en mode Rescue"
   - Confirmer — OVH enverra un email avec le mot de passe root temporaire

2. **Se connecter en Rescue**
   ```bash
   ssh root@IP_PUBLIQUE_VPS
   # Utiliser le mot de passe recu par email
   ```

3. **Monter le disque systeme**
   ```bash
   # Identifier le disque
   lsblk
   # Generalement /dev/sda1 ou /dev/vda1

   mount /dev/vda1 /mnt
   ```

4. **Reparer sshd_config**
   ```bash
   nano /mnt/etc/ssh/sshd_config
   ```
   Changer `ListenAddress` en `0.0.0.0`.

5. **Reparer UFW (si necessaire)**
   ```bash
   # Voir les regles UFW
   cat /mnt/etc/ufw/user.rules

   # Ajouter une regle SSH ouverte
   # Ou desactiver UFW temporairement :
   echo "ENABLED=no" > /mnt/etc/ufw/ufw.conf
   ```

6. **Quitter le mode Rescue**
   ```bash
   umount /mnt
   ```
   - OVH Manager > VPS > "Reboot en mode normal"
   - Attendre ~2 minutes

7. **Se reconnecter**
   ```bash
   ssh -p 2222 deploy@IP_PUBLIQUE_VPS
   ```

---

## Option 3 — Reinstaller et redeployer (dernier recours)

Si le systeme est corrompu au point de ne pas pouvoir etre repare.

1. **OVH Manager > VPS > Reinstaller**
   - Choisir Debian 13 (Bookworm)
   - Ajouter votre cle SSH publique

2. **Redeployer VPAI** avec le mode open :
   ```bash
   ansible-playbook playbooks/site.yml \
     -e "target_env=prod" \
     -e "hardening_ssh_force_open=true" \
     -e "ansible_user=root" \
     --diff
   ```

3. **Installer et connecter Tailscale**
   ```bash
   ansible-playbook playbooks/site.yml \
     --tags "headscale-node" \
     -e "target_env=prod"
   ```

4. **Verifier que le VPN fonctionne** :
   ```bash
   ansible-playbook playbooks/safety-check.yml -e "target_env=prod"
   ```

5. **Redeployer en mode verrouille** :
   ```bash
   ansible-playbook playbooks/site.yml \
     -e "target_env=prod" \
     --diff
   ```

---

## Prevention — Bonnes pratiques

### Avant chaque modification de hardening

```bash
# 1. Verifier l'etat actuel
ansible-playbook playbooks/safety-check.yml -e "target_env=prod"

# 2. S'assurer que le VPN est up
ssh -p 2222 deploy@IP_VPN_TAILSCALE "tailscale status"

# 3. Deployer avec --check d'abord (dry run)
ansible-playbook playbooks/site.yml \
  --tags hardening \
  -e "target_env=prod" \
  --check --diff
```

### Pendant le debug initial

Tant que l'infrastructure n'est pas stabilisee, utiliser `force_open` :

```bash
# Deployer sans restriction SSH
ansible-playbook playbooks/site.yml \
  -e "target_env=prod" \
  -e "hardening_ssh_force_open=true" \
  --diff
```

Le guard automatique fait deja cela si Tailscale n'est pas connecte,
mais `force_open=true` le force meme si Tailscale semble up.

### Variables cles

| Variable | Default | Effet |
|----------|---------|-------|
| `hardening_ssh_force_open` | `false` | Force SSH sur 0.0.0.0 + UFW ouvert |
| `hardening_ssh_listen_address` | IP VPN | Adresse de bind quand verrouille |
| `hardening_ssh_port` | 2222 | Port SSH custom |

### Comportement automatique du guard

```
Tailscale UP + force_open=false  →  SSH verrouille sur IP VPN
Tailscale UP + force_open=true   →  SSH ouvert sur 0.0.0.0
Tailscale DOWN + force_open=false →  SSH ouvert sur 0.0.0.0 (auto)
Tailscale DOWN + force_open=true  →  SSH ouvert sur 0.0.0.0
```

Le guard ne verrouille **jamais** si le VPN n'est pas confirme operationnel.

---

## Contacts utiles

- **Console OVH** : <https://www.ovh.com/manager/>
- **Support OVH VPS** : <https://help.ovhcloud.com/csm?id=csm_get_help>
- **Status OVH** : <https://web-cloud.status-ovhcloud.com/>
