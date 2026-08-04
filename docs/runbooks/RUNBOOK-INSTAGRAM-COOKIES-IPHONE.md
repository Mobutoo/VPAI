# Runbook — Export des cookies Instagram depuis un iPhone (gate CANARY-0)

> Destinataire : opérateur. Durée : ~15 min, dont l'installation de l'extension.
> But : fournir au worker d'acquisition Prisme les cookies de session du **compte Instagram
> autorisé**, au format Netscape, sans que le secret transite par un chat, un mail ou un canal
> public.
> Contexte : `~/work/saas/prisme/docs/2026-08-03-plan-canary-instagram.md` (phases CANARY-0→5).
> Après ce runbook, il ne reste qu'une action : l'activation via l'UI (attestation + handle).

## 0. Le piège central, à lire avant tout

Le cookie `sessionid` d'Instagram est **HttpOnly**. Aucun raccourci Siri, aucun bookmarklet, aucun
script lisant `document.cookie` ne peut le récupérer — ils ne voient que les cookies non-HttpOnly
et produiront un fichier **silencieusement incomplet**, refusé par le déploiement.

Il faut donc **une extension navigateur** disposant de la permission `cookies`. C'est la seule voie
possible depuis iOS.

## 1. Prérequis

| Prérequis | Détail |
|---|---|
| Compte Instagram | Le compte **dédié / sacrifiable** autorisé pour le canary. **Jamais** le compte principal — le risque de bannissement est assumé par design (plan §2, point de vigilance ToS) |
| Tailscale actif sur l'iPhone | Le coffre `https://fongola.ewutelo.cloud` est **VPN-only** (ACL Caddy `import vpn_only`, Seko). Hors tailnet : page d'erreur VPN, pas de connexion |
| App Bitwarden iOS | Configurée sur le serveur auto-hébergé — écran de connexion → engrenage **Paramètres du serveur** → URL du serveur : `https://fongola.ewutelo.cloud` |
| Navigateur avec extensions | Voir §2 |

## 2. Installer une extension d'export de cookies

**Voie A — Orion (Kagi), à privilégier.** C'est la plus fiable des deux : elle donne un export
Netscape natif via une extension dont le code est public.

1. Installer **Orion** (éditeur : Kagi Inc.) depuis l'App Store.
2. Menu → *Extensions* → installer **« Get cookies.txt LOCALLY »**.
   Éditeur à vérifier avant installation : le projet est open-source, dépôt
   `github.com/kairi003/Get-cookies.txt-LOCALLY`. Passer par le lien du dépôt plutôt que par une
   recherche par mot-clé.
3. Autoriser l'extension sur `instagram.com` uniquement.

**Voie B — Safari iOS**, si Orion ne convient pas : Réglages → Apps → Safari → Extensions →
installer une extension d'export de cookies → l'activer → sur la page Instagram, bouton `ᴀA` →
nom de l'extension → **Autoriser pour ce site web**.

### Vérifier une extension AVANT de lui donner tes cookies

Une extension à qui l'on accorde la permission `cookies` sur `instagram.com` **lit la session
complète** : mal choisie, elle peut l'exfiltrer. Aucune des deux voies n'a pu être testée depuis
l'infra — l'offre iOS bouge et les noms de l'App Store ne sont pas des garanties. Critères à
appliquer, dans l'ordre :

| Critère | Ce qu'on veut |
|---|---|
| Éditeur | Nommé, identifiable, avec un site ou un dépôt public. Un éditeur anonyme = refus |
| Code | Open-source vérifiable de préférence (cas de « Get cookies.txt LOCALLY ») |
| Permissions demandées | `cookies` + accès à `instagram.com`. Une extension qui réclame **tous les sites** ou un accès réseau sortant : refus |
| Fonctionnement | Export **local** (fichier / partage iOS). Toute extension qui propose un « compte », une « synchronisation cloud » ou un envoi vers un serveur : refus |
| Périmètre | Restreindre l'accès au seul domaine `instagram.com`, jamais « tous les sites web » |

Rappel qui limite la casse : ce compte est **sacrifiable par conception**. Si un doute subsiste sur
une extension, l'installer, exporter, puis **la supprimer immédiatement** après l'export.

## 3. Ouvrir la session Instagram

1. Dans **ce navigateur** (Orion ou Safari, celui qui porte l'extension), aller sur
   `https://www.instagram.com`.
2. Se connecter avec le compte autorisé, valider la 2FA si elle est active.
3. Ouvrir une page du compte (profil, ou un post) pour que la session soit complètement posée.
4. Rester connecté : **ne pas se déconnecter** ensuite, une déconnexion invalide le `sessionid`
   côté serveur Instagram et le fichier exporté devient inutilisable.

## 4. Exporter les cookies

1. Ouvrir l'extension **depuis la page Instagram** (elle exporte les cookies du site courant).
2. Choisir l'export du domaine `instagram.com` — format **Netscape / `cookies.txt`** si proposé.
   Si seul un export **JSON** est disponible, il n'est convertible que s'il s'agit du schéma
   courant « tableau d'objets », c'est-à-dire une liste dont chaque entrée porte au minimum
   `name`, `value`, `domain`, `path`, et une expiration (`expirationDate` ou `expires`), plus
   éventuellement `httpOnly` / `secure` — le schéma produit par Cookie-Editor et EditThisCookie.
   Tout autre schéma (objet unique, format propriétaire, champs renommés) est **refusé** : dans ce
   cas, réexporter depuis la voie A plutôt que tenter une conversion à l'aveugle.
3. Contrôler la présence de **`sessionid`**. Cookies attendus :

| Cookie | Statut |
|---|---|
| `sessionid` | **obligatoire**, expiration `0` ou date future |
| `csrftoken` | recommandé |
| `ds_user_id` | recommandé |
| `mid`, `ig_did` | facultatifs |

Format Netscape = 7 champs séparés par des **tabulations** (jamais des espaces) :

```
.instagram.com	TRUE	/	TRUE	1790000000	sessionid	<valeur>
```

Les lignes HttpOnly sortent préfixées `#HttpOnly_` : **c'est normal, ne pas les supprimer** — le
validateur de déploiement les traite comme des lignes de données (correctif de revue M3). Un
fichier dont le `sessionid` aurait été retiré parce qu'il « ressemblait à un commentaire » serait
rejeté.

## 5. Déposer dans le coffre

1. Récupérer le contenu du fichier exporté. **Éviter le presse-papier iOS autant que possible** :
   il est partagé entre apps, et le presse-papier universel (Handoff) le synchronise vers les
   autres appareils du même compte iCloud — un `sessionid` s'y retrouverait hors de l'iPhone.
   - **Voie sûre** : l'extension propose un partage → *Enregistrer dans Fichiers*, puis ouvrir le
     fichier depuis Fichiers et le lire dans Bitwarden (pièce jointe si ton offre le permet, sinon
     sélection du texte depuis Fichiers directement vers le champ Notes).
   - **Si le copier-coller est inévitable** : Réglages → Général → AirPlay et Handoff → désactiver
     **Handoff** avant la copie, puis, une fois la note enregistrée, copier n'importe quel texte
     anodin pour écraser le presse-papier, et réactiver Handoff.
2. App Bitwarden iOS → **+** → **Note sécurisée**.
3. Nom exact : `instagram-cookies-<compte>` — en remplaçant `<compte>` par le handle du compte
   autorisé, sans `@` (exemple : `instagram-cookies-monhandle`).
4. Coller le contenu dans le champ **Notes**. Enregistrer. Vérifier que la synchronisation est
   passée (tirer pour rafraîchir).
5. Me dire en session : **le nom du compte uniquement**. Jamais le contenu — ni dans le chat, ni
   par Telegram, ni par mail : ces canaux sont journalisés et un secret journalisé est un secret à
   roter.

## 6. Dépannage

| Symptôme | Cause probable | Action |
|---|---|---|
| Pas de `sessionid` dans l'export | Extension sans permission `cookies` (elle lit `document.cookie`) | Changer d'extension — c'est le piège §0, aucune autre solution |
| Export en JSON | Extension sans format Netscape | Le déposer tel quel **si** le schéma est celui décrit au §4 (tableau d'objets `name`/`value`/`domain`/`path`/expiration) ; sinon réexporter via la voie A |
| Champs séparés par des espaces | Copie via une app qui a converti les tabulations | Réexporter en passant par l'app Fichiers plutôt que par un copier-coller de texte affiché |
| Expiration passée sur `sessionid` | Session déjà expirée | Se reconnecter, réexporter |
| Instagram demande une vérification pendant la connexion | Challenge / checkpoint | Le résoudre **manuellement dans le navigateur**, puis réexporter. Rien dans le système ne contourne un challenge, par conception |
| Coffre injoignable depuis l'iPhone | Tailscale inactif | Activer le VPN, `fongola.ewutelo.cloud` est VPN-only |

## 7. Ce qui se passe ensuite (côté Claude, aucune action de ta part)

1. `rbw sync` puis lecture de la note — le contenu n'est jamais affiché.
2. Validation, alignée sur la règle réellement appliquée au déploiement
   (`roles/prisme-fetcher/tasks/main.yml:368-371`) : format Netscape (tabulations), présence d'une
   ligne `sessionid` pour `instagram.com` / `.instagram.com` / `www.instagram.com`, et expiration
   **soit `0` (cookie de session, jamais expiré), soit une date future** — les deux sont
   acceptées, c'est la même règle qu'au §4. Conversion JSON → Netscape d'abord si nécessaire.
3. Chiffrement dans `vault_prisme_instagram_cookies` (`ansible-vault`, `no_log` sur toutes les
   tâches qui le manipulent).
4. `prisme_instagram_enabled: true` + `prisme_instagram_allowed_handles: ["<compte>"]`, puis
   redéploiement du rôle `prisme-fetcher` sur waza.
5. Le heartbeat part vers le plan de contrôle. Le passage au vert du **gate 5 (disponibilité)**
   n'est pas supposé : il est vérifié explicitement avant de te rendre la main — état du service
   `prisme-fetcher` (`ExecMainStatus=0`), heartbeat reçu et frais côté serveur (fenêtre de 90 s),
   puis appel de `GET /api/v1/connectors/instagram/gates` qui doit renvoyer `missingGates: []`.
   Si l'un des trois échoue, je te le dis au lieu d'annoncer un gate vert.
6. Le bouton d'activation devient cliquable dans `/settings/connectors` : attestation légale +
   re-saisie du handle, en deux étapes. **C'est ton geste, il n'est pas automatisable.**

## 8. Rotation et révocation

- Les cookies expirent : quand l'acquisition tombe en `blocked:login_required`, refaire ce runbook
  et mettre à jour la même note du coffre.
- Révocation immédiate : bouton **Révoquer** dans `/settings/connectors` — il coupe l'autorisation,
  draine les jobs en attente et marque les cookies à re-fournir. Se déconnecter du compte
  Instagram depuis l'app invalide en plus le `sessionid` côté Instagram.
