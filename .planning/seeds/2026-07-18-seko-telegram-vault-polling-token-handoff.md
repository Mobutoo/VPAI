# Handoff — Finaliser le split de tokens Telegram Seko (vault + template)

> Seed créé le 2026-07-18. À exécuter dans une nouvelle session, AVANT tout redeploy Ansible de Seko-VPN.
> Mémoire liée : `project_seko_telegram_bot_token_split.md` (memory Claude VPAI).

## Contexte (fait et vérifié le 2026-07-18)

- **Cause racine** : le token @Ekenge (`837900…` = `telegram_monitoring_bot_token` VPAI) était partagé entre
  le bot admin Seko `telegram-bot.service` (**polling** getUpdates) et le webhook n8n `memory-telegram-bot`
  (`https://mayi.ewutelo.cloud/webhook/memory-telegram-bot`, voulu, ré-armé idempotent par `roles/n8n-provision`
  côté VPAI). L'API Telegram interdit polling + webhook sur un même token → bot Seko mort en 409 Conflict
  du 2026-06-30 au 2026-07-18 (bot.log gonflé à 368M).
- **Fix live appliqué** : nouveau bot BotFather **@EkengeSekoBot** (id `8896825076`), token remplacé dans
  `/opt/services/telegram-bot/.env` sur Seko (600 root:root préservé), service restart, polling propre,
  0 Conflict, sendMessage OK. Webhook @Ekenge INTACT.
- **Récupérer le token @EkengeSekoBot** (ne pas le stocker en clair ailleurs) :
  `ssh -i ~/.ssh/seko-vpn-deploy mobuone@87.106.30.160 'sudo grep "^TELEGRAM_BOT_TOKEN" /opt/services/telegram-bot/.env'`

## 🔴 Le problème restant (régression automatique sinon)

Le `.env` Seko est **géré par Ansible** : `Seko-VPN/roles/telegram_bot/templates/.env.j2` est rendu depuis
`vault_telegram_bot_token` (`Seko-VPN/inventory/group_vars/all/vault.yml`, chiffré). Cette variable est
**partagée par 3 rôles** :

| Rôle | Fichier | Doit utiliser |
|---|---|---|
| `telegram_bot` | `templates/.env.j2` | **@EkengeSekoBot** (polling) |
| `monit` | `templates/telegram-alert.sh.j2` | @Ekenge (sendMessage only) |
| `uptime_kuma` | `templates/configure-monitors.py.j2` | @Ekenge (sendMessage only) |

Au prochain `ansible-playbook` Seko : `.env` régénéré avec @Ekenge → retour du 409 Conflict **et** le bot
ferait `deleteWebhook` sur @Ekenge à son boot (comportement automatique python-telegram-bot ≥21) →
**casserait le memory-bot n8n**.

## Étapes (repo `/home/mobuone/work/infra/Seko-VPN` sur waza)

1. **Gate humain — mot de passe vault Seko-VPN** : introuvable le 18/07 (pas de `.vault_password` dans le
   repo, rien dans `ansible.cfg`/`Makefile`, rien dans rbw — seul `ansible-vault-password-VPAI` existe,
   testé **incompatible**). Le retrouver (ou re-chiffrer le vault) est le prérequis.
   Une fois retrouvé : le sauvegarder dans Vaultwarden (`rbw`) comme `ansible-vault-password-Seko-VPN`
   (pattern du backup VPAI fait le 17/07, cf memory `reference_rbw_headless_add`).
2. `ansible-vault edit inventory/group_vars/all/vault.yml` → ajouter :
   `vault_telegram_bot_polling_token: "<token @EkengeSekoBot, cf commande ci-dessus>"`
   Ne PAS toucher `vault_telegram_bot_token` (reste @Ekenge pour monit + uptime_kuma).
3. `roles/telegram_bot/templates/.env.j2` : repointer `TELEGRAM_BOT_TOKEN` sur
   `{{ vault_telegram_bot_polling_token }}`. Pas de `default()` sur une var vault (règle REX-62).
4. Lint + commit ciblé (ces 2 fichiers uniquement — vérifier `git status` avant : ne pas embarquer
   d'autres modifs).
5. Test d'idempotence : rejouer le rôle `telegram_bot` (`--check --diff` d'abord) → le `.env` rendu doit
   être **identique** au live (0 changed au 2e run réel).

## Vérifications finales

- `systemctl is-active telegram-bot` = active, `sudo tail bot.log` : polling `bot8896825076…`, zéro `Conflict`.
- `getWebhookInfo` sur @Ekenge (token : `sudo grep TELEGRAM_MONITORING_BOT_TOKEN /opt/javisi/configs/n8n/n8n.env` sur Sese) :
  `url` toujours `https://mayi.ewutelo.cloud/webhook/memory-telegram-bot`, 0 pending, 0 erreur.
- Envoyer `/status` à @EkengeSekoBot depuis Telegram → réponse attendue.

## Pièges connus

- `python-telegram-bot` fait `deleteWebhook` automatiquement au démarrage : tout bot qui démarre en polling
  avec un token EFFACE le webhook de ce token. Ne jamais démarrer un bot polling avec le token @Ekenge.
- `rbw add` sans TTY crée un item vide (memory `reference_rbw_headless_add`) — utiliser `script -qec`.
- Commits locaux du 17-18/07 non poussés dans Seko-VPN : `8056c34` (fix hardening logrotate). À pousser
  ensemble le moment venu (`git@github-seko`).
