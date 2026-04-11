# ComfyUI Studio v0.7.0 — Montage Bridge

> Date: 2026-03-23 | Status: Draft | Prerequisite: v0.5.0 (Series Engine) + v0.6.0
> Auteur: mobuone + Claude Code

## 1. Vision

Connecter le pipeline de generation (ComfyUI Studio MCP) au montage final (Remotion + OpenCut) via un format pivot bidirectionnel, et permettre des ajustements en langage naturel sur le montage.

**Objectif:** Avoir les deux — pipeline automatique ET timeline interactive — avec un round-trip sans perte.

### Positionnement vs Mosaic.so

| Capacite | Mosaic | Notre stack sans bridge | Avec bridge v0.7.0 |
|----------|--------|------------------------|---------------------|
| Pipeline auto (brief -> assets) | Non | Oui (ComfyUI Studio MCP) | Oui |
| Brand/style system | Basique | Oui (Style DNA + Scene Graph) | Oui |
| Serie N episodes | Non | Oui (Series Engine) | Oui |
| Timeline visuelle | Oui | OpenCut isole | OpenCut connecte |
| Agent sur montage | Oui | Non | Oui (`montage_adjust`) |
| Round-trip pipeline <-> timeline | Oui | Non | Oui |
| Production tracking | Non | Oui (Kitsu) | Oui |
| Self-hosted | Non ($9-119/mois) | Oui | Oui |

## 2. Architecture

```
ComfyUI Studio MCP v0.5+              Remotion (Waza)              OpenCut (Waza)
+----------------------------+    +---------------------+    +---------------------+
| Style DNA                  |    | Montage.tsx         |    | Timeline editor     |
| Scene Graph                |    | 5x Reel templates   |    | (Next.js, on-demand)|
| Series Engine              |    | Subtitles, Audio    |    |                     |
| generate_image / workflow  |    | Color grade, Grain  |    |                     |
+----------------------------+    +---------------------+    +---------------------+
             |                            ^    |                    ^    |
             |  (1) build MontageProps    |    |                    |    |
             +--------------------------->|    |                    |    |
                                          |    | (2) render MP4    |    |
                                          |    | or preview URL    |    |
                                          |    v                    |    |
                                     +----------+                  |    |
                                     | MP4/URL  |                  |    |
                                     +----------+                  |    |
                                                                   |    |
             +--- (3) MontageProps JSON ----->  import timeline ---+    |
             |                                                          |
             +<--- (4) MontageProps modifie --- export timeline --------+
             |
             v
      (5) re-render partiel (seules les scenes modifiees)
```

### Format pivot : MontageProps

Le format existe deja dans Remotion (`roles/remotion/files/remotion/Montage/types.ts`). C'est le contrat d'interface entre tous les composants.

```typescript
interface MontageProps {
  scenes: MontageScene[];       // clips sur la timeline
  fps: number;
  width: number;
  height: number;
  direction: {
    pacing: string;
    defaultTransition: string;
    defaultTransitionDurationFrames: number;
    colorGrade: { preset, contrast, saturation, brightness };
    grain: number;
    typography: { fontFamily, accentColor, textColor };
    subtitleStyle: string;
    sceneOverrides?: Record<number, {...}>;
  };
  title?: TitleCardProps;
  outro?: TitleCardProps;
  subtitles?: SubtitleLine[];
  audio?: AudioConfig;
}

interface MontageScene {
  durationInFrames: number;
  asset_url: string;            // image, video, ou composition
  text?: string;                // overlay text
  effect?: string;
  kenBurns?: {...};
}
```

## 3. Composants

### 3.1 MCP Tool: `montage_build` (Pipeline -> MontageProps)

Assemble les assets generes par le pipeline en un MontageProps pret a render.

**Input:**
- `series_id` + `episode_num` (ou liste d'assets manuelle)
- `brand_name` (pour injecter Style DNA dans direction/typography/colorGrade)
- `format` : "reel_9_16", "landscape_16_9", "square_1_1"
- `pacing` : "fast", "medium", "slow"

**Logic:**
1. Recupere les assets de l'episode (Series Engine + Asset Cache)
2. Recupere le Style DNA du brand -> mappe sur `direction`
3. Recupere les subtitles (si voiceover existe -> Whisper -> SRT -> SubtitleLine[])
4. Calcule les durees par scene selon le pacing
5. Retourne un `MontageProps` JSON complet

**Output:** MontageProps JSON

### 3.2 MCP Tool: `montage_render`

Envoie un MontageProps a Remotion et retourne le resultat.

**Input:**
- `montage_props` : MontageProps JSON
- `output` : "preview" (URL Remotion Player) | "mp4" (fichier rendu)
- `quality` : "draft" (720p, fast) | "final" (1080p/4K)

**Logic:**
1. POST MontageProps vers l'API Remotion (localhost:3200)
2. Si `output=preview` : retourne l'URL du Remotion Player avec les props en query
3. Si `output=mp4` : declenche `npx remotion render` et retourne le chemin du fichier

**Output:** URL preview ou chemin MP4

### 3.3 MCP Tool: `montage_adjust` (Agent sur timeline)

Modifie un MontageProps existant via instructions en langage naturel.

**Input:**
- `montage_props` : MontageProps JSON existant
- `instruction` : texte libre ("raccourcis la scene 3 de 2 secondes", "ajoute un fade entre 4 et 5", "remplace la musique", "rends le color grade plus chaud")
- `brand_name` (optionnel, pour valider la coherence style)

**Logic:**
1. Envoie le MontageProps + l'instruction a LiteLLM
2. Le LLM retourne un MontageProps modifie (structured output / JSON mode)
3. Valide les modifications (durees > 0, transitions valides, assets existent)
4. Optionnel : `style_dna.check_drift()` pour signaler si les changements s'ecartent du brand

**Output:** MontageProps modifie + diff lisible des changements

### 3.4 MCP Tool: `montage_diff`

Compare deux MontageProps et retourne un diff lisible.

**Input:** `before` (MontageProps), `after` (MontageProps)

**Output:** Liste des changements (scene ajoutee/supprimee/modifiee, transition changee, etc.)

### 3.5 OpenCut Bridge (etape 2 — optionnelle)

Pont bidirectionnel OpenCut <-> MontageProps. Deux approches possibles :

**Option A : Plugin OpenCut (prefere)**
- Endpoint API dans OpenCut : `POST /api/import-montage` (recoit MontageProps, cree un projet timeline)
- Endpoint API : `GET /api/export-montage/:projectId` (exporte le projet en MontageProps)
- Necessite un fork ou PR sur OpenCut

**Option B : Fichier intermediaire**
- Le MCP ecrit un `montage.json` dans un volume partage
- OpenCut surveille le dossier et importe automatiquement
- L'export ecrit un `montage-edited.json` que le MCP lit
- Plus simple, moins elegant

## 4. Workflow utilisateur

### Mode automatique (pipeline pur)

```
User: "Genere l'episode 3 de la serie Paul Taff"
  -> series_get_brief(series_id, 3)
  -> generate_image/execute_workflow (assets)
  -> montage_build(series_id, 3, "paul-taff", "reel_9_16")
  -> montage_render(props, "mp4", "final")
  -> Upload preview vers Kitsu
```

### Mode hybride (pipeline + ajustements)

```
User: "Genere l'episode 3"
  -> montage_build(...) -> MontageProps
  -> montage_render(props, "preview") -> URL preview

User regarde le preview, puis:
  "La scene 2 est trop longue, coupe 3 secondes"
  -> montage_adjust(props, "raccourcis scene 2 de 3 secondes")
  -> montage_render(new_props, "preview") -> nouveau preview

User: "OK c'est bon, rends le final"
  -> montage_render(new_props, "mp4", "final")
```

### Mode timeline (OpenCut)

```
User: "Envoie le montage dans OpenCut pour que je puisse l'ajuster"
  -> montage_build(...) -> MontageProps
  -> POST OpenCut /api/import-montage (MontageProps)
  -> User edite dans OpenCut (trim, reordonne, transitions)
  -> GET OpenCut /api/export-montage -> MontageProps modifie
  -> montage_render(edited_props, "mp4", "final")
  -> Kitsu mis a jour
```

## 5. Remotion API

### Endpoint necessaire (a creer)

Remotion tourne sur Waza (localhost:3200). Il faut un petit serveur API :

```
POST /api/render
  Body: { compositionId: "Montage", inputProps: MontageProps, format: "mp4"|"preview" }
  Response: { output_path: "/path/to/output.mp4" } ou { preview_url: "http://..." }

GET /api/preview?props=<base64(MontageProps)>
  -> Redirige vers Remotion Player avec les props
```

**Implementation:** Un serveur Express minimal (~50 lignes) devant Remotion qui :
1. Recoit les props
2. Appelle `npx remotion render Montage --props <json>` (ou l'API programmatique `renderMedia`)
3. Retourne le resultat

Ce serveur peut vivre dans le role `remotion` existant.

## 6. Fichiers a creer/modifier

### Nouveau dans ComfyUI Studio

| Fichier | Responsabilite |
|---------|---------------|
| `comfyui_cli/montage.py` | MontageBuilder (assemble assets -> MontageProps) |
| `comfyui_cli/montage_agent.py` | MontageAgent (ajustements LLM sur MontageProps) |
| `tests/test_montage.py` | Tests montage builder |
| `tests/test_montage_agent.py` | Tests agent ajustement |

### Nouveau dans Remotion (role Ansible)

| Fichier | Responsabilite |
|---------|---------------|
| `roles/remotion/files/api/server.ts` | Serveur Express API render |
| `roles/remotion/files/api/package.json` | Dependencies serveur |

### Modifie

| Fichier | Changement |
|---------|-----------|
| `mcp/mcp_server.py` | +4 MCP tools (montage_build, montage_render, montage_adjust, montage_diff) |
| `comfyui_cli/config.py` | +1 config key : `remotion_api_url` |
| `roles/remotion/tasks/main.yml` | Deploiement du serveur API |
| `roles/remotion/templates/docker-compose-remotion.yml.j2` | Ajout service API (ou integration dans le service existant) |

### MCP Tools (4 nouveaux)

| Tool | Input | Output |
|------|-------|--------|
| `montage_build` | series_id, episode_num, brand_name, format, pacing | MontageProps JSON |
| `montage_render` | montage_props, output (preview/mp4), quality | URL ou chemin fichier |
| `montage_adjust` | montage_props, instruction, brand_name | MontageProps modifie + diff |
| `montage_diff` | before, after | Liste des changements |

## 7. Implementation Order

```
Wave 1: Remotion API server (render endpoint)
        + montage_build (assets -> MontageProps)
        + tests
        |
Wave 2: montage_adjust (LLM agent sur MontageProps)
        + montage_render (appel Remotion API)
        + montage_diff
        + tests
        |
Wave 3: OpenCut bridge (optionnel)
        + import/export MontageProps
        + round-trip verification
```

## 8. Contraintes

| Contrainte | Impact |
|------------|--------|
| RPi5 16GB (Waza) | Remotion render = CPU-bound. Draft 720p ~30s, Final 1080p ~2-5min selon duree |
| Pas de GPU | Le render Remotion est du compositing (pas de ML), donc OK sur CPU |
| OpenCut = fork necessaire | L'import/export MontageProps necessite des modifications dans OpenCut. Option B (fichier) en fallback |
| LLM pour montage_adjust | Un appel LiteLLM par ajustement (~$0.01-0.05 selon modele). Budget OK dans le $5/jour |
| MontageProps = contrat stable | Toute modification du format Remotion doit etre retrocompatible |

## 9. Success Criteria

- [ ] SC-1: `montage_build` produit un MontageProps valide depuis un episode Series Engine
- [ ] SC-2: `montage_render` produit un MP4 lisible via l'API Remotion
- [ ] SC-3: `montage_adjust` modifie correctement un MontageProps via instruction naturelle
- [ ] SC-4: Round-trip `build -> adjust -> render` fonctionne end-to-end
- [ ] SC-5: Preview URL accessible via navigateur (Remotion Player)
- [ ] SC-6: (Optionnel) Import/export MontageProps dans OpenCut

## 10. Relation avec les versions precedentes

```
v0.4.0  ComfyUI Studio MCP (generation, workflows, RAG, assets)
v0.5.0  Series Engine (Style DNA, Scene Graph, series N episodes)
v0.6.0  [a definir]
v0.7.0  Montage Bridge (ce document)
        - Depend de v0.5.0 (Series Engine pour montage_build)
        - Depend de Remotion existant (Montage.tsx, compositions)
        - OpenCut bridge optionnel
```
