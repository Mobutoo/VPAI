# Health Page v2 — Design Document

**Date :** 2026-02-25
**Session :** 14
**Périmètre :** `roles/palais/files/app/src/`

---

## Problèmes identifiés

| # | Problème | Root cause |
|---|---|---|
| 1 | Nodes toujours "offline" | Le statut DB n'est mis à jour que via webhook n8n (non configuré). La VPN topology Headscale est récupérée mais pas utilisée pour mettre à jour le statut. |
| 2 | IPs manquantes sur les cards | Variables Ansible `vpn_server_ip` et `workstation_pi_local_ip` absentes de `main.yml` → seed.ts reçoit des chaînes vides |
| 3 | Pas d'UI pour éditer les nodes | Le backend `PATCH /api/v1/health/nodes/[name]` existe mais aucun formulaire dans le frontend |

---

## Décisions design

| Question | Choix |
|---|---|
| Source de vérité pour le statut | Headscale (sync automatique au page load) |
| Fallback si Headscale injoignable | Status `degraded` pour tous les nodes |
| UX édition | Modal inline par node card |
| Icône édition | SVG crayon (pas d'emoji) |

---

## Architecture — Data flow

```
+page.server.ts → load():
  1. allNodes = db.select().from(nodes)
  2. vpnResult = await fetchVPNTopology()
     → retourne { nodes: VPNNode[], error: boolean }
     → error: true si Headscale unreachable/timeout

  3. Si error: true
       → UPDATE tous les nodes SET status='degraded'
     Sinon
       → Pour chaque node ayant un tailscaleIp :
           vpnMatch = vpnTopology.find(v => v.ip === node.tailscaleIp)
           si match.online === true  → SET status='online', lastSeenAt=match.lastSeen
           si match.online === false → SET status='offline'
           si pas de match           → SET status='offline'
     → UPDATE en batch (une requête par node modifié)

  4. allNodes = db.select().from(nodes) — re-fetch après sync
  5. return { nodes: nodesWithHealth, vpnTopology, headscaleOk: !error }
```

---

## Fichiers modifiés

### Backend

#### 1. `src/lib/server/health/headscale.ts`
- Modifier le type de retour : `{ nodes: VPNNode[], error: boolean }`
- Retourner `{ nodes: [], error: true }` en cas d'erreur (au lieu de `[]`)
- Retourner `{ nodes: [], error: false }` si API répond vide
- Retourner `{ nodes: [...], error: false }` si succès

#### 2. `src/routes/health/+page.server.ts`
- Après `fetchVPNTopology()`, sync des statuts en DB
- Si `error: true` → UPDATE tous les nodes à `'degraded'`
- Sinon → UPDATE chaque node matché par tailscaleIp
- Re-fetch après sync
- Ajouter `headscaleOk` dans le retour (pour affichage UI)
- Note: `busy` status n'est pas écrasé par la sync Headscale (respecter le status webhook n8n si `busy`)

#### 3. `inventory/group_vars/all/main.yml`
- Ajouter `workstation_pi_local_ip: "{{ vault_workstation_pi_local_ip | default('') }}"`
- Ajouter `vpn_server_ip: "{{ vpn_server_public_ip | default('') }}"` (alias)

### Frontend

#### 4. `src/routes/health/+page.svelte`
**Ajouts :**
- État local `editingNode: NodeRow | null = null` (Svelte `$state`)
- Fonction `openEdit(node)` et `closeEdit()`
- Fonction `saveEdit(name, fields)` → fetch PATCH → invalide cache → reload

**Bouton édition sur chaque card :**
```html
<!-- Icône SVG crayon, top-right du header de card -->
<button onclick={() => openEdit(node)}
  style="color: var(--palais-gold); opacity: 0.5; hover: opacity-100">
  <svg><!-- crayon 16x16 --></svg>
</button>
```

**Modal édition :**
```
glass-panel + hud-bracket overlay
Champs (JetBrains Mono, border gold 0.3):
  - Description (text)
  - Tailscale IP (text, placeholder "100.x.x.x")
  - IP locale / LAN (text, placeholder "192.168.x.x")
Boutons: ANNULER (ghost) | ENREGISTRER (gold filled)
```

**Header amélioré :**
- Indicateur "HEADSCALE SYNC" avec timestamp si `headscaleOk: true`
- Badge "VPN UNREACHABLE" amber pulsant si `headscaleOk: false`
- Pill `degraded` en amber dans les compteurs de status

**Pill `degraded` dans les status badges :**
```
status === 'degraded' → amber pulse, texte "DEGRADED"
```

---

## Comportement fin de sync

| Cas | Action DB | Badge UI |
|---|---|---|
| Headscale répond, node `online: true` | `status = 'online'` | vert ONLINE |
| Headscale répond, node `online: false` | `status = 'offline'` | rouge OFFLINE |
| Node pas dans Headscale | `status = 'offline'` | rouge OFFLINE |
| Headscale unreachable | `status = 'degraded'` | amber pulsant DEGRADED |
| Node status = `busy` (webhook n8n) | **non écrasé** par sync Headscale | gold BUSY |

---

## Fix Ansible IPs

```yaml
# main.yml — à ajouter
workstation_pi_local_ip: "{{ vault_workstation_pi_local_ip | default('') }}"
vpn_server_ip: "{{ vpn_server_public_ip | default('') }}"  # alias
```

Note: `vault_workstation_pi_local_ip` devra être ajouté au vault si pas déjà présent (ex: `192.168.1.8`).

---

## Périmètre release

- v1.9.2 — feat(palais): health page v2 — Headscale sync + node edit modal
- 5 fichiers modifiés : `headscale.ts`, `+page.server.ts`, `+page.svelte`, `main.yml` (+ possiblement vault)
- Pas de migration DB nécessaire (schéma `degraded` déjà dans l'enum `nodeStatusEnum`)
