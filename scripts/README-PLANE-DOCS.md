# Plane Documentation Indexer

Script pour télécharger et indexer toute la documentation Plane dans Qdrant pour recherche sémantique locale.

## Installation

```bash
# Depuis Waza (Workstation Pi)
cd /home/mobuone/VPAI/scripts

# Installer les dépendances
pip3 install qdrant-client requests beautifulsoup4 openai python-dotenv

# Ou utiliser le venv Ansible
source ../.venv/bin/activate
pip install qdrant-client requests beautifulsoup4 openai python-dotenv
```

## Configuration

```bash
# Copier le template d'environnement
cp .env.example .env

# Éditer avec les vraies valeurs (depuis PRD.md)
nano .env
```

Variables requises :
- `QDRANT_API_KEY` : Clé API Qdrant (depuis PRD.md)
- `LITELLM_API_KEY` : Clé master LiteLLM (depuis PRD.md)

## Usage

### 1. Dry Run (test de scraping sans indexation)

```bash
python3 index-plane-docs.py --dry-run --verbose
```

Résultat :
- Scrape docs.plane.so et developers.plane.so
- Sauvegarde dans `/tmp/plane_docs_scraped.json`
- Chunk en segments de 1000 chars
- Sauvegarde dans `/tmp/plane_docs_chunks.json`
- **N'indexe PAS** dans Qdrant

### 2. Indexation Complète

```bash
# Charger les variables d'environnement
export $(cat .env | xargs)

# Lancer l'indexation
python3 index-plane-docs.py --max-pages 200
```

Processus :
1. **Scrape** : Crawl BFS des sites de doc (max 200 pages)
2. **Chunk** : Découpe en segments de 1000 chars (overlap 200)
3. **Embed** : Génère embeddings via LiteLLM (text-embedding-3-small)
4. **Index** : Upload dans Qdrant collection `plane_docs`

Durée estimée : ~10-15 minutes (selon nombre de pages)

### 3. Test de Recherche

```bash
python3 index-plane-docs.py \
  --max-pages 50 \
  --test-search "How to create an issue via API?"
```

Résultat :
```
📊 Search Results:

1. [0.876] API Reference - Issues
   https://developers.plane.so/api/issues
   Create a new issue using POST /api/v1/issues...

2. [0.834] Getting Started - API Authentication
   https://developers.plane.so/getting-started
   Authenticate your requests using API tokens...
```

## Architecture

```
┌─────────────────────┐
│  Plane Docs Sites   │  docs.plane.so, developers.plane.so
└──────────┬──────────┘
           │ HTTP Scrape (BeautifulSoup)
           ↓
┌─────────────────────┐
│  Scraped Pages      │  JSON avec title, text, url, links
└──────────┬──────────┘
           │ Chunking (1000 chars, overlap 200)
           ↓
┌─────────────────────┐
│  Text Chunks        │  Segments sémantiques avec métadonnées
└──────────┬──────────┘
           │ Embedding (LiteLLM → text-embedding-3-small)
           ↓
┌─────────────────────┐
│  Vector Embeddings  │  1536-dim vectors
└──────────┬──────────┘
           │ Upload (batch 10)
           ↓
┌─────────────────────┐
│  Qdrant Collection  │  plane_docs (COSINE distance)
└─────────────────────┘
```

## Collection Qdrant

**Nom** : `plane_docs`
**Vecteurs** : 1536 dimensions (text-embedding-3-small)
**Distance** : COSINE
**Payload** :
```json
{
  "url": "https://docs.plane.so/...",
  "title": "API Authentication",
  "text": "Full text of the chunk...",
  "chunk_index": 0,
  "total_chunks": 3,
  "scraped_at": "2026-02-28T12:34:56Z",
  "source": "plane_docs"
}
```

## Utilisation par les Agents OpenClaw

Une fois indexé, les agents peuvent rechercher dans la doc Plane via :

```python
# Depuis un agent OpenClaw (skill plane-bridge)
from qdrant_client import QdrantClient

qdrant = QdrantClient(url="http://qdrant:6333", api_key=QDRANT_API_KEY)

# Recherche sémantique
results = qdrant.search(
    collection_name="plane_docs",
    query_vector=embed("How to create a cycle?"),
    limit=3
)

for hit in results:
    print(f"[{hit.score:.3f}] {hit.payload['title']}")
    print(f"→ {hit.payload['url']}")
    print(hit.payload['text'][:200])
```

Ou via MCP tool Palais :

```bash
curl -X POST http://plane-bridge:3400/api/mcp \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "plane.docs.search",
      "arguments": {"query": "How to assign issues to users?"}
    }
  }'
```

## Maintenance

### Re-indexation (après update doc Plane)

```bash
# Supprimer l'ancienne collection
python3 -c "
from qdrant_client import QdrantClient
q = QdrantClient(url='https://qd.ewutelo.cloud', api_key='$QDRANT_API_KEY')
q.delete_collection('plane_docs')
print('✅ Collection supprimée')
"

# Ré-indexer
python3 index-plane-docs.py --max-pages 200
```

### Vérifier la collection

```bash
# Nombre de points
curl -H "api-key: $QDRANT_API_KEY" \
  https://qd.ewutelo.cloud/collections/plane_docs

# Exemple de point
curl -H "api-key: $QDRANT_API_KEY" \
  https://qd.ewutelo.cloud/collections/plane_docs/points/scroll?limit=1
```

## Troubleshooting

### Erreur "QDRANT_API_KEY not set"

```bash
# Vérifier que .env est sourcé
export $(cat .env | xargs)
echo $QDRANT_API_KEY  # Doit afficher la clé
```

### Erreur "Failed to connect to Qdrant"

```bash
# Vérifier que Qdrant est accessible depuis Waza
curl -I https://qd.ewutelo.cloud/dashboard
# Attendu : 200 OK

# Vérifier VPN Tailscale actif
tailscale status
```

### Trop de pages scrapées (rate limit)

```bash
# Réduire max-pages
python3 index-plane-docs.py --max-pages 50

# Ou ajouter un delay entre requêtes (modifier le script)
# Dans PlaneDocsScraper.scrape_page(), ajouter :
import time
time.sleep(0.5)  # 500ms entre chaque page
```

## Coût Estimé

- **Scraping** : Gratuit
- **Embeddings** : ~200 pages × 3 chunks/page × $0.00002/1k tokens ≈ **$0.12**
- **Storage Qdrant** : Négligeable (~10MB)

## Exemple de Sortie

```
🚀 Plane Documentation Indexer
📚 Scraping: https://docs.plane.so/, https://developers.plane.so/
🎯 Target collection: plane_docs
🔢 Embedding model: text-embedding-3-small

📄 Scraping: https://docs.plane.so/
📄 Scraping: https://docs.plane.so/getting-started
📄 Scraping: https://docs.plane.so/features/issues
...
✅ Scraped 87 pages
💾 Saved scraped pages to /tmp/plane_docs_scraped.json

📦 Created 243 chunks from 87 pages
💾 Saved chunks to /tmp/plane_docs_chunks.json

✅ Collection exists: plane_docs
🔢 Embedding chunk 1/243: Getting Started...
🔢 Embedding chunk 2/243: Creating Your First Project...
...
✅ Uploaded batch of 10 points
✅ Uploaded batch of 10 points
...
✅ Uploaded final batch of 3 points

🎉 Indexed 243 chunks to Qdrant collection 'plane_docs'

✅ Done!
```
