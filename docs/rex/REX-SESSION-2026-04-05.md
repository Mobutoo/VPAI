# REX Session 20 — StoryEngine Inspector UX (2026-04-05)

## Objectif

Premiere session post-pipeline dediee a un **projet applicatif** issu de l'App Factory :
**StoryEngine** (IDE narratif, monorepo Next.js + FastAPI + Hocuspocus).

Iterer sur l'experience Inspector du scene editor pour fermer trois manques
remontes par l'utilisateur en francais :

> "il manque la detection des objets et des lieux. car lorsque je surligne
> Ewutelo je dois pouvoir indiquer que c'est un lieu. Il manque un bouton
> auto-link pour qu'il lie tous les caracteres et entites presentes. On doit
> ensuite avoir la possibilite de corriger les erreurs ou de supprimer le link"

Objectifs derives :

1. Permettre de choisir le **type** (character / location / object / arc / pivot)
   lors de la creation d'une entite via autocomplete `@`.
2. Ajouter un bouton **Auto-link** qui scanne le draft et lie toutes les
   occurrences de noms d'entites connues en un seul undo.
3. Ajouter une action **Unlink** ciblee sur la mention cliquee (pas toutes
   les occurrences).

## Ce qui a ete fait

### v1.4.2 — Cast chips + ghost text opt-in

| Fix | Commit | Detail |
|-----|--------|--------|
| Match par token pour Cast | `841e1b9` | Les noms multi-mots ("Baat Bindfal") ne matchaient pas. Nouveau helper `entityNameMatches` : tokenise le nom, garde les tokens >= 3 chars, match word-boundary Unicode-aware (`\p{L}\p{N}` lookaround) avec fallback `\b` ASCII |
| Ghost text toggle opt-in | `841e1b9` | Les suggestions inline auto-generees genent l'ecriture. Ajout d'un toggle dans `scene-toolbar.tsx` + store `ai.store` (`ghostEnabled`, persist localStorage) |

### v1.4.3 — Draft scan + right-click wrap + fact display

| Fix | Commit | Detail |
|-----|--------|--------|
| Detection des noms dans le draft | `2477740` | Ajout de `draftText` dans `editor.store` (synchro debounced avec `editor.getText()`). Cast split en 3 sections : *Planned* (dans summary), *Also in draft* (linke), *Detected (unlinked)* |
| Right-click wrap mode | `2477740` | Clic droit sur une selection ouvre l'autocomplete en mode "wrap existing text". Sur Enter, applique un entityMention a la selection au lieu de taper |
| Back button dans Inspector | `2477740` | `inspector-shell.tsx` gagne un bouton "Back" qui efface le focus et restaure la vue scene summary |
| Fact display regression | `2477740` | `extractFactText()` dans `inspector-fact-row.tsx` gere maintenant `{text}`, `{value}`, `{content}`, `{description}`, `{label}` et single-key shapes |

### v1.4.4 — Type picker + Auto-link + Unlink

| Fix | Commit | Detail |
|-----|--------|--------|
| Type picker sur Create | `fed8955` | Autocomplete `@Ewutelo` propose maintenant 5 chips colorees (character/location/object/arc/pivot). ←/→ cyclent le type, mouseenter previsualise, click cree directement. Signature changee : `onCreate(name, type)` |
| Bouton Auto-link | `fed8955` | Scanne `doc.descendants()`, skip les text nodes deja marques, matche chaque nom d'entite par regex Unicode word-boundary, resout les overlaps (sort by pos asc + length desc, greedy accept), applique tous les marks dans **une seule transaction** (= un seul Ctrl+Z) |
| Action Unlink ciblee | `fed8955` | Le click sur une mention etend la range a gauche/droite tant que le meme `entityId` est actif (`doc.resolve(p).marks()`), puis `unsetEntityMention()` sur cette range exacte. Supprime le lien **uniquement sur la mention cliquee**, pas sur toutes les occurrences |
| Module-singleton `editor-ref.ts` | `fed8955` | Panels hors du subtree EditorPanel (Inspector, EntityPopover) ont besoin d'un acces imperatif au TipTap Editor. Zustand inadapte (editor referentiellement stable, pas de re-render voulu). Pattern : module-level singleton `currentEditor` + getter/setter |

### v1.4.5 — Pronom wrap + Cmd+K unblock + search 503 fix + auto-version

| Fix | Commit | Detail |
|-----|--------|--------|
| Dedup entite par nom + 409 dialog | `85e8f5a` | Creation `@Baat` alors qu'il existe deja en type different → 409 avec liste des existants. Modal `EntityConflictDialog` propose **Use existing** (link direct) ou **Create anyway** (`?force=true`). Store dedup par id a la reception |
| Link pronoms sans reecrire | `75524c1` | Wrap mode : on surligne "Il", Cmd+K ouvre l'autocomplete qui prefixe "Link « Il » → …" puis lie la selection a l'entite existante. Le texte n'est pas reecrit, seul le mark `entityMention` est pose sur la range |
| Cmd+K double-popup | `3d0f03e` | Le handler scene-page et le `SearchModal` global s'abonnaient tous deux au keydown, ouvrant deux popups. Scene-page s'enregistre maintenant sur `document` en **phase capture** + `stopImmediatePropagation` → bat le bubble du SearchModal. N'intercepte que si selection non-vide ; selection vide → SearchModal normal |
| Version auto via `git describe` | `3d0f03e` | `next.config.ts` execute `git describe --tags --always --dirty` au load → topbar affiche `v1.4.5` sur un tag, `v1.4.5-N-<sha>` entre releases. Env var prod gagne (Docker build arg via Ansible) |
| Search RRF 503 systematique | `b4b5493` | Tous les `/api/v1/projects/:id/search` renvoyaient 503. Cause : `text(":query_embedding::vector(1536)")` — la regex bind-param de SQLAlchemy `:(\w+)(?!:)` refuse un `:name` suivi de `::` (le cast PG). Le placeholder restait litteral, PG rejetait `syntax error at or near ":"`. Fix : `CAST(:query_embedding AS vector(1536))`. Bonus : `logger.exception()` avant le 503 au lieu de swallow silencieux |

## Etat actuel

- Type checking OK (`apps/web tsc --noEmit` clean).
- Deploy v1.4.5 : `ok=12 changed=5 failed=0` sur story.ewutelo.cloud.
- Tous les objectifs utilisateur (types, auto-link, unlink, pronom-link) livres.
- Autocomplete `@` + right-click wrap + Cmd+K-pronom + auto-link + unlink + search hybride forment la
  boucle complete de gestion des entites dans l'editeur.
- Version UI auto-derivee de git : plus de divergence entre tag et topbar.

## Architecture validee

### Module-singleton pour l'editeur TipTap

Besoin : exposer les commandes imperatives (`autoLink`, `unsetEntityMention`)
a des panels qui vivent **hors du subtree** de `<EditorPanel>`.

**Non retenu** :
- Zustand store → provoque des re-renders sur tous les consumers a chaque changement, inadapte pour une reference referentiellement stable.
- Context + useRef → necessite un Provider qui englobe Inspector + EditorPanel, refactor trop intrusif.
- Prop drilling → chaque panel devrait recevoir l'editor via toute la chaine de composants.

**Retenu** : singleton module-level (`apps/web/src/lib/editor-ref.ts`), avec
`setCurrentEditor(editor)` appele dans `useEffect` de la page scene +
cleanup a l'unmount. Les consumers font `const editor = getCurrentEditor()`
avec null-check systematique.

Pattern applicable a tout besoin "ref stable + acces imperatif cross-tree".

### Token-based matching pour les noms d'entites

Les noms multi-mots ("Baat Bindfal", "Marie de Ewutelo") ne sont presents
dans le texte que partiellement. On tokenise le nom (split whitespace), on
garde les tokens >= 3 chars, et on matche **au moins un token** avec
word-boundary Unicode-aware.

```javascript
new RegExp(`(?<![\\p{L}\\p{N}])${token}(?![\\p{L}\\p{N}])`, "iu")
```

Fallback ASCII `\b` si le runtime ne supporte pas les Unicode property
escapes. Compatible Safari 13+, Firefox 78+, Chrome 64+.

### Single-transaction mark batching (auto-link)

ProseMirror permet de chainer plusieurs `tr.addMark()` sur la meme
transaction avant un unique `view.dispatch(tr)`. Consequence : **un seul
Ctrl+Z revient en arriere sur tous les marks appliques**. UX propre si
l'utilisateur veut defaire l'auto-link apres coup.

```typescript
let tr = editor.state.tr
for (const m of accepted) {
  tr = tr.addMark(m.from, m.to, markType.create({...}))
}
editor.view.dispatch(tr)
```

### Unlink precis via range extension

Click position → range complete de la mention en etendant gauche/droite
tant que `doc.resolve(p).marks()` contient le meme `entityId`. Evite le
probleme "toutes les occurrences de Ewutelo sont delinkees" — seule la
mention cliquee est delinkee.

### Capture-phase event listener pour battre un listener global

**Probleme** : deux composants ecoutent `Cmd+K` sur `document` en phase
bubble (scene-page handler + SearchModal). L'ordre d'enregistrement
determine qui gagne → fragile, race de mount.

**Solution** : le handler qui doit gagner s'enregistre en **phase capture**
(`addEventListener(evt, fn, { capture: true })`) + appelle
`stopImmediatePropagation()` quand il consomme l'evenement. La phase
capture se declenche **avant** toute phase bubble, quelle que soit
l'ordre d'enregistrement. Pattern applicable partout ou un handler
contextuel doit preempter un handler global (Cmd+S, Cmd+Enter, Escape).

### SQLAlchemy text() + PG cast `::type` → piege

La regex bind-param de SQLAlchemy est
`(?<![:\w\$\x5c]):(\w+)(?!:)` — le negative lookahead `(?!:)` signifie
**qu'un `:name` immediatement suivi de `:` n'est PAS un bind param**.
Donc `:query_embedding::vector(1536)` se retrouve avec `:query_embedding`
litteral dans le prepared statement → `syntax error at or near ":"`.

**Regle** : ne jamais combiner `:bind` et `::cast` dans `text()`.
Utiliser `CAST(:bind AS type)` a la place. Vrai pour tous les types
PG qui ont du sens en cast (`::int`, `::uuid`, `::jsonb`, `::vector`, …).

### Git describe comme source de version UI

`next.config.ts` peut executer `child_process.execSync("git describe …")`
au load (cote build ou cote dev server). Resultat : la version affichee
reflete **exactement** l'arbre git au moment de la build/start, sans
maintenance manuelle d'un `package.json.version`. Format :
- `v1.4.5` sur un tag exact
- `v1.4.5-3-3d0f03e` a 3 commits d'un tag (g-prefix strippe pour la lisibilite)
- `v1.4.5-dirty` sur working tree sale

Env var (`NEXT_PUBLIC_APP_VERSION`) wins pour les builds Docker ou on
veut forcer la string (ex. Ansible passe `story_engine_version` depuis
son propre `git describe` pour avoir le SHA de la copie clonee cote VM).

## Fichiers critiques

| Fichier | Role |
|---------|------|
| `apps/web/src/lib/editor-ref.ts` | Singleton du TipTap Editor — cross-component imperatif |
| `apps/web/src/components/ide/entity-autocomplete.tsx` | Autocomplete `@` + type picker (5 chips) + ←/→ cycle + wrap-mode (`selectionLabel`, `allowCreate`) |
| `apps/web/src/components/ide/entity-conflict-dialog.tsx` | Modal 409 — Use existing / Create anyway / Cancel |
| `apps/web/src/components/ide/entity-popover.tsx` | Popover hover sur mention + action Unlink via `mentionRange` |
| `apps/web/src/components/ide/inspector-scene-summary.tsx` | Cast chips (planned/linked/detected) + `autoLinkEntities()` |
| `apps/web/src/app/(app)/projects/[id]/scenes/[sceneId]/page.tsx` | Register editor + Cmd+K capture-phase + wrap-mode handler |
| `apps/web/src/components/search-modal.tsx` | Cmd+K global (bubble phase) — preempte par scene-page si selection |
| `apps/web/src/stores/editor.store.ts` | `draftText` (debounced) pour detection entites dans le draft |
| `apps/web/src/stores/entity.store.ts` | `createEntity(name, type, force?)` + dedup par id a la reception |
| `apps/web/src/stores/ai.store.ts` | `ghostEnabled` toggle (localStorage persist) |
| `apps/web/next.config.ts` | `resolveAppVersion()` via `git describe` + env var override |
| `apps/api/src/story_engine/services/search.py` | RRF hybrid search — `CAST(:query_embedding AS vector(1536))` |
| `apps/api/src/story_engine/api/routes/search.py` | `logger.exception()` avant 503 pour diagnosticabilite |

## Leçons transversales App Factory

1. **Pattern singleton editor-ref** : candidat pour `app-factory-patterns`
   Qdrant collection. Reutilisable pour tout IDE-like app ayant besoin de
   commandes imperatives cross-panel.
2. **Token-based Unicode matching** : reutilisable pour n'importe quel
   systeme de detection d'entites dans du texte libre (chat, notes,
   scripts).
3. **Single-transaction mark batching** : pattern ProseMirror a documenter
   car non-intuitif pour les devs React habitues a batch via setState.
4. **Type picker via mouseenter + click** : UX pattern efficace pour les
   choix enumeres avec feedback visuel immediat, sans modal.
5. **Capture-phase preemption** : quand deux listeners globaux se
   disputent une touche (Cmd+K, Cmd+S), enregistrer le contextuel en
   `{ capture: true }` + `stopImmediatePropagation()`. Plus robuste que
   l'ordre de mount. Pattern a promouvoir pour tout raccourci partage.
6. **SQLAlchemy `text()` + PG cast `::`** : documenter comme piege
   recurrent. Chaque fois qu'on utilise pgvector, jsonb, uuid, etc.
   avec un bind param, utiliser `CAST(:bind AS type)`. Candidat pour
   une regle lint custom ou un snippet SQL partage.
7. **Auto-version via git describe** : pattern general pour tout app Web
   qui veut afficher sa version sans build step separe. Reutilisable
   tel-quel pour Next.js/Vite/Remix. Ansible peut override via env var
   pour forcer la string cote VM.
8. **Swallow-exception 503** : **anti-pattern confirme** — `except
   Exception: raise HTTPException(503)` sans log a masque un bug 503
   prod pendant toute la session d'init du search. Regle : TOUJOURS
   `logger.exception()` avant de degrader en 503/500/503. Candidat
   pour une regle ruff/bandit custom.

## Prochaines etapes

1. **Indexer ce REX** dans Qdrant `app-factory-rex` via webhook `af-rex-indexer` (source=`story-engine`, project_name=`StoryEngine`, phase=`inspector-ux-v1.4`).
2. **Extraire les patterns** reutilisables vers `app-factory-patterns` :
   `editor-ref-singleton`, `token-unicode-match`, `proseMirror-tx-batch`,
   `capture-phase-preemption`, `sqlalchemy-cast-bind`, `git-describe-version`.
3. **Tester E2E** (Playwright) : scenarios auto-link + unlink + create-with-type + **Cmd+K pronom wrap + search hybrid**. Le script E2E existe pour V2-04 mais pas encore pour ces fonctions.
4. **Cote backend** : exposer un endpoint `POST /api/v1/entities/batch` pour creer plusieurs entites en un coup (utile apres auto-link si l'utilisateur veut creer les "Detected (unlinked)" en batch).
5. **Ecrire un test d'integration search** qui frappe l'endpoint HTTP reel avec un embedding mocke — aurait attrape le bug SQL bind avant prod.
6. **Monitoring** : alerte Grafana si le taux de 503 sur `/api/v1/projects/*/search` depasse 5% sur 5min → aurait detecte le bug RRF des le deploy.
7. **Retour App Factory** : valider avec l'utilisateur que ces 6 patterns meritent d'etre indexes comme patterns reutilisables pour les futures apps.
