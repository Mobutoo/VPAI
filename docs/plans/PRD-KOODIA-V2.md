# PRD Koodia v2 — Food Intelligence Platform

**Version** : 2.1
**Date** : 2026-03-12
**Status** : Draft
**Auteur** : Erwin + Claude

---

## 1. Vision

Koodia est le cockpit alimentaire ultime : une interface unique, mobile-first, qui orchestre recettes (Mealie), stock (Grocy), calendrier (Ase), budget (Zimboo/Firefly III) et intelligence nutritionnelle. L'app est **proactive** : elle ne se contente pas de stocker, elle anticipe, suggere, alerte et optimise.

**Objectif** : 0 gaspillage, nutrition optimale, budget maitrise — sans effort cognitif.

---

## 2. Stack Infrastructure

| Service | Role | URL interne | Donnees |
|---------|------|-------------|---------|
| **Mealie** | Recettes, meal plans, shopping lists | `http://mealie:9000` | Recettes, plans, listes |
| **Grocy** | Stock, produits, emplacements, codes-barres | `http://grocy:80` | Inventaire, DLC, quantites |
| **Ase** | Calendrier (CalDAV/REST) | `http://ase:8000` | Evenements repas, rappels |
| **Zimboo** | Dashboard financier + budget repas + fidelite + coupons | `http://zimboo:3000` | Budgets, transactions, objectifs, points fidelite, coupons |
| **Firefly III** | Moteur comptable (backend Zimboo) | `http://firefly-iii:8080` | Transactions, categories, tags |
| **Activepieces** | Orchestration workflows (30 flows) | `http://activepieces:8080` | Automatisations, triggers, logs |
| **LiteLLM** | Gateway IA multi-modeles | `http://litellm:4000` | Routage intelligent par cas d'usage |
| **Qdrant** | Base vectorielle (memoire culinaire) | `http://qdrant:6333` | Embeddings recettes, profils, CIQUAL |
| **PostgreSQL** | Donnees structurees | `postgresql:5432` | CIQUAL, profils, allergies, medicaments |
| **Redis** | Cache + temps reel (PubSub) | `redis:6379` | Sessions, cache stock, sync shopping |
| **VictoriaMetrics** | Metriques time-series | `victoria-metrics:8428` | Nutrition, budget, stock, gaspillage |
| **Grafana** | Dashboards embarques | `grafana:3000` | Visualisation nutrition/budget/stock |
| **OpenClaw** | Agent IA raisonnement complexe | `http://openclaw:18789` | Cas limites uniquement |

### Principe de routage Activepieces vs OpenClaw

| Critere | Activepieces | OpenClaw |
|---------|-------------|----------|
| Workflows lineaires, previsibles | Oui | Non |
| Retry, logs, versionning | Natif | Limite |
| Raisonnement multi-contraintes (>5 variables) | Non | Oui |
| Volume (>20 executions/jour) | Oui | Non |

**Regle** : Activepieces par defaut. OpenClaw uniquement pour 3 cas : menu therapeutique, diagnostic nutritionnel, resolution conflits multi-profils.

---

## 3. Pages Koodia

### 3.1 Dashboard

**Objectif** : Vue proactive en un coup d'oeil.

| Widget | Source | Description |
|--------|--------|-------------|
| Suggestion du soir | LiteLLM + Qdrant + Grocy | "Ce soir je vous suggere : Risotto champignons" (basee sur stock, saison, historique) |
| Expiration urgente | Grocy volatile | Badge rouge "3 items expirent demain" + liens directs |
| Budget repas | Zimboo API | Jauge "72% du budget mensuel utilise" + tendance |
| Listes actives | Mealie shopping | "2 listes actives, 14 articles" |
| Stock bas | Grocy volatile | "5 articles a reapprovisionner" |
| Prochain repas | Ase + Mealie | "Diner dans 2h30 : Poulet roti" avec rappel |
| Score anti-gaspi | VictoriaMetrics | "Ce mois : 0.3kg gaspille (-40% vs mois dernier)" |
| Quick Actions | — | Ajouter stock, nouvelle recette, planifier, scanner |

### 3.2 Recipes

**Objectif** : Trouver, explorer, cuisiner.

| Fonctionnalite | Source | Details |
|----------------|--------|---------|
| Liste paginee | Mealie `/recipes` | Cards avec image, temps, difficulte |
| Recherche semantique | Qdrant `recipes` | "Quelque chose de reconfortant" → resultats pertinents |
| Recherche texte | Mealie search | Recherche par nom, ingredient |
| Filtres | Client-side | Tous, Favoris, Rapide <30min, Vegetarien, Riche proteines |
| Badge faisabilite | Grocy stock cross-ref | "7/10 ingredients en stock" avec couleur vert/orange/rouge |
| Badge nutrition | CIQUAL lookup | Calories, proteines par portion |
| Badge cout estime | Firefly historique | "~4.50 EUR/portion" |
| Import par URL | Mealie scraper | Coller URL → scrape → enrichissement CIQUAL auto |
| Favoris | Mealie API | Toggle coeur |
| Ratings | Mealie API | 1-5 etoiles |
| Detail recette | Mealie `/recipes/{slug}` | Ingredients, instructions, tags, temps, nutrition |
| Equivalents economiques | LiteLLM + Firefly | Si objectif Zimboo = epargne → "Remplacer saumon par maquereau (-40%)" |

### 3.3 Cook Mode (nouveau)

**Objectif** : Cuisiner mains-libres, etape par etape.

| Fonctionnalite | Implementation | Details |
|----------------|---------------|---------|
| Plein ecran | CSS fullscreen API | Pas de distraction, police grande |
| Step-by-step | Swipe gauche/droite | Navigation etapes avec animation |
| WakeLock | Navigator.wakeLock API | Ecran ne s'eteint jamais pendant la cuisson |
| Timers inline | Web Timer API | Chaque etape avec timer integre, notification a la fin |
| TTS narration | Web Speech API | Lecture vocale de l'etape courante |
| Adaptation niveau | LiteLLM | Debutant = explications detaillees, Expert = concis |
| Mode enfant | LiteLLM | Vocabulaire simple, encouragements, emojis |
| Multi-recettes | Activepieces workflow #6 | Orchestrer 2-3 recettes en parallele, timeline optimisee |
| Session tracking | PostgreSQL + Redis | Enregistrer debut/fin, note, pour memoire culinaire |

### 3.4 Planner

**Objectif** : Planifier la semaine intelligemment.

| Fonctionnalite | Source | Details |
|----------------|--------|---------|
| Vue semaine | Mealie mealplans | 7 jours x 3 repas (petit-dej, dejeuner, diner) |
| Navigation | date-fns + locale | Semaine precedente/suivante, aujourd'hui |
| Jours traduits | next-intl + date-fns locale | Lundi, Mardi... dans la langue active |
| AI Planner | Activepieces workflow #4 | Generer plan hebdo base sur stock + nutrition + budget + preferences |
| Conflits calendrier | Ase `getCalendarEvents()` | Si RDV ce soir → forcer recette rapide |
| Badge nutrition jour | VictoriaMetrics + CIQUAL | Vert/Orange/Rouge selon equilibre macros du jour |
| Alerte allergie | Activepieces workflow #10 | Warning inline si ingredient conflit avec profil membre |
| Drug-food check | Activepieces workflow #11 | Alerte si interaction medicament detectee |
| Invites | Activepieces workflow #19 | Bouton "+2 invites" → recalcul portions + shopping delta |
| Sync calendrier | Ase `createWeeklyMealEvents()` | Plan valide → evenements crees dans Ase automatiquement |
| Cout estime semaine | Activepieces workflow #27 | "Plan estime a ~62 EUR" basee sur historique Firefly |
| Batch cooking | Activepieces workflow #6 | Identifier recettes batch-ables le weekend |
| FIFO priorite | Grocy volatile + Activepieces #2 | Prioriser ingredients qui expirent bientot |

### 3.5 Shopping

**Objectif** : Listes intelligentes, collaboratives, economiques.

| Fonctionnalite | Source | Details |
|----------------|--------|---------|
| Listes Mealie | Mealie shopping lists | Tabs Actives / Terminees |
| Ajouter item inline | Mealie POST item | Input + Enter |
| Cocher/decocher | Mealie PATCH item | Optimistic update |
| Supprimer item | Mealie DELETE item | Swipe gauche |
| Grouper par categorie | Mealie label.name | Fruits, Legumes, Epicerie... |
| Generer depuis plan | Activepieces workflow #5 | Diff plan vs stock → liste auto |
| Generer depuis recettes | Agent POST | Selection recettes → liste |
| Collaboration temps reel | Redis PubSub + SSE | Multi-devices sync instantane |
| Prix estimes | Firefly historique | Afficher prix moyen par item |
| Total estime | Somme prix | "~47 EUR pour cette liste" |
| Substitutions economiques | LiteLLM + Firefly + Zimboo | Si objectif = epargne : "Penne au lieu de Fusilli (-0.80 EUR, meme recette)" |
| Suggestions anti-gaspi | Grocy volatile + LiteLLM | "Ajoutez X pour utiliser le Y qui expire demain" |
| **Multi-magasins** | Firefly stores + Zimboo fidelite | Vue par magasin avec split liste, prix compares, trajet optimise |
| Routage multi-magasin | Activepieces workflow #30 | Repartir items par magasin selon meilleur prix + coupons + proximite |
| **Coupons & bons plans** | Zimboo API `/coupons/match` | Badge sur item : "Coupon -0.50 EUR (Carrefour, expire J+3)" |
| Total economies coupons | Zimboo coupons matched | "4 coupons applicables, -3.80 EUR potentiel" |
| **Points fidelite** | Zimboo API `/loyalty/balances` | Afficher solde par enseigne, seuils de remise atteints |
| Notification Zimboo | `notifyShoppingCompleted()` | Fin de courses → Zimboo auto-tag transaction + deduire coupons utilises |

### 3.6 Inventory

**Objectif** : Savoir exactement ce qu'on a, ou, et quand ca expire.

| Fonctionnalite | Source | Details |
|----------------|--------|---------|
| Stock complet | Grocy `/stock` | Produit, quantite, emplacement, DLC |
| Filtrer par emplacement | Grocy locations | Tous, Frigo, Congelateur, Placard... |
| Recherche | Client-side filter | Par nom de produit |
| Badge expiration | Grocy volatile + date calc | Rouge (expire), Orange (J-3), Vert (OK), Gris (pas de DLC) |
| FIFO rotation | Activepieces workflow #2 | "Utiliser d'abord : Lait (expire J+1), Yaourt (expire J+2)" |
| Quick Stats | Grocy stock + volatile | Total, expirant cette semaine, stock bas |
| Ajouter produit | Grocy POST products | Formulaire basique |
| Scan barcode | Camera API + OpenFoodFacts | Scan → identification → creation produit auto |
| Photo frigo | LiteLLM vision | Photo → identification produits → stock update |
| Consommer | Grocy POST consume | Bouton -1 sur chaque item |
| Transferer | Grocy POST transfer | Deplacer du frigo au congelateur |
| Historique | Grocy stock journal | Voir entrees/sorties |
| Prix d'achat | Grocy product prices | Tracker prix par produit/magasin |
| Auto-stock from receipt | Activepieces workflow #26 | Zimboo envoie ticket → stock mis a jour |

### 3.7 Nutrition (nouveau)

**Objectif** : Nutrition personnalisee, multi-profils, securisee.

| Fonctionnalite | Source | Details |
|----------------|--------|---------|
| Profils famille | PostgreSQL `family_members` | Nom, age, poids, taille, activite, objectif |
| Objectifs individuels | PostgreSQL + Qdrant | Prise de masse, perte poids, performance, grossesse, senior, croissance |
| Allergies 3 niveaux | PostgreSQL `allergies` | Anaphylaxie IgE (blocage), Intolerance (alerte), Preference (info) |
| Medicaments | PostgreSQL `medications` | Warfarine/vitK, IMAO/tyramine, statines/pamplemousse... |
| Drug-food alerts | Activepieces workflow #11 | Warning avant ajout recette si interaction detectee |
| Cures nutritionnelles | PostgreSQL `nutrition_cures` | Fer, Zinc, VitD, Magnesium, Omega-3, Folates, Calcium, B12 |
| Suivi cure | Activepieces workflow #9 | Progression quotidienne vs objectif |
| Base CIQUAL | PostgreSQL `ciqual_foods` + `ciqual_components` | 3185 aliments, 67 composants nutritionnels |
| Matching ingredients | Qdrant `ingredients-ciqual` | Fuzzy match ingredient Mealie ↔ aliment CIQUAL |
| Calcul auto par repas | Activepieces workflow #7 | Meal plan du jour → lookup CIQUAL → macros/micros |
| Tracker quotidien | VictoriaMetrics | Calories, proteines, glucides, lipides, fibres, vitamines |
| Dashboard nutrition | Grafana embeddé | Graphes semaine/mois, jauges vs objectifs, tendances |
| Rapport hebdo | Activepieces workflow #8 | Notification dimanche avec resume + recommandations |
| Multi-profil reconciliation | OpenClaw agent | 4 membres, 4 profils, 1 repas → trouver le compromis optimal |
| PDF export | Koodia API | Bilan mensuel exportable (medecin, nutritionniste) |

### 3.8 Budget (widget + section)

**Objectif** : Maitriser les depenses alimentaires avec intelligence.

| Fonctionnalite | Source | Details |
|----------------|--------|---------|
| Budget repas Zimboo | Zimboo API | Lire budget repas configure dans Zimboo |
| Jauge budget mensuel | Zimboo + Firefly | "456 / 600 EUR (76%)" avec couleur progressive |
| Historique depenses | Firefly transactions tag "food" | Graphe mensuel via Grafana embed |
| Depenses par magasin | Firefly transactions + store tag | Repartition Carrefour / Lidl / Marche |
| Depenses par categorie | Firefly categories | Viandes, Legumes, Epicerie, Boissons... |
| Cout par repas | CIQUAL + Firefly prix moyens | "Ce diner a coute ~5.20 EUR pour 4 personnes" |
| Alerte seuil | Activepieces workflow #13 | Notification si >80% du budget mensuel |
| Substitutions economiques | LiteLLM + Firefly | Pendant shopping : suggerer alternatives moins cheres |
| Objectif epargne Zimboo | Zimboo API objectifs | Si objectif = epargne → mode actif sur substitutions |
| Score economie | VictoriaMetrics | "Ce mois vous avez economise 23 EUR grace aux substitutions" |
| Economies coupons | VictoriaMetrics + Zimboo | "12.50 EUR economises via coupons ce mois" |
| Points fidelite | Zimboo API | Solde par enseigne + "Plus que 15 pts → bon de 5 EUR chez Lidl" |
| Estimation avant validation | Activepieces workflow #27 | Avant valider le plan : "Cout estime : 58 EUR (budget restant : 144 EUR)" |
| Tendance annuelle | Grafana embeddé | Evolution depenses food mois par mois |

---

## 4. Collections Qdrant

| Collection | Contenu | Usage |
|-----------|---------|-------|
| `recipes` | Embedding titre + description + ingredients + tags par recette | Recherche semantique ("quelque chose de chaud avec des legumes"), recettes similaires |
| `culinary-memory` | Historique : recettes cuisinees + notes + preferences par membre | Personnalisation : "Tu as adore le risotto" |
| `nutrition-profiles` | Profils nutritionnels vectorises (objectifs, restrictions, cures) | Matching profil ↔ recette compatible |
| `ingredients-ciqual` | 3185 aliments CIQUAL avec composants nutritionnels embeddes | Matching fuzzy ingredient Mealie ↔ donnee CIQUAL |

---

## 5. Schema PostgreSQL (nouvelles tables)

```sql
-- Profils nutritionnels par membre du foyer
CREATE TABLE family_members (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     TEXT NOT NULL DEFAULT 'default',
  name          TEXT NOT NULL,
  birth_date    DATE,
  weight_kg     REAL,
  height_cm     REAL,
  sex           TEXT CHECK (sex IN ('M', 'F', 'other')),
  activity_level TEXT CHECK (activity_level IN ('sedentary','light','moderate','active','very_active')),
  objective     TEXT CHECK (objective IN ('maintain','lose','gain','performance','growth','pregnancy','senior')),
  avatar_url    TEXT,
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now()
);

-- Allergies et intolerances (3 niveaux)
CREATE TABLE allergies (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  member_id   UUID REFERENCES family_members(id) ON DELETE CASCADE,
  allergen    TEXT NOT NULL,
  severity    TEXT NOT NULL CHECK (severity IN ('anaphylaxis','intolerance','preference')),
  notes       TEXT,
  detected_at DATE,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Medicaments et interactions alimentaires
CREATE TABLE medications (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  member_id         UUID REFERENCES family_members(id) ON DELETE CASCADE,
  drug_name         TEXT NOT NULL,
  interactions_json JSONB DEFAULT '[]',
  start_date        DATE,
  end_date          DATE,
  created_at        TIMESTAMPTZ DEFAULT now()
);

-- Cures nutritionnelles actives
CREATE TABLE nutrition_cures (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  member_id       UUID REFERENCES family_members(id) ON DELETE CASCADE,
  cure_type       TEXT NOT NULL CHECK (cure_type IN ('iron','zinc','vitD','magnesium','omega3','folates','calcium','B12')),
  target_daily_mg REAL NOT NULL,
  start_date      DATE NOT NULL,
  end_date        DATE,
  status          TEXT DEFAULT 'active' CHECK (status IN ('active','completed','paused')),
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- CIQUAL referentiel (3185 aliments x 67 composants)
CREATE TABLE ciqual_foods (
  id         SERIAL PRIMARY KEY,
  code       TEXT UNIQUE NOT NULL,
  name_fr    TEXT NOT NULL,
  name_en    TEXT,
  group_code TEXT,
  group_name TEXT
);

CREATE TABLE ciqual_components (
  food_id        INT REFERENCES ciqual_foods(id) ON DELETE CASCADE,
  component_id   INT NOT NULL,
  component_name TEXT NOT NULL,
  value_per_100g REAL,
  unit           TEXT,
  PRIMARY KEY (food_id, component_id)
);

-- Sessions cooking mode
CREATE TABLE cooking_sessions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  member_id   UUID REFERENCES family_members(id),
  recipe_slug TEXT NOT NULL,
  started_at  TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  rating      INT CHECK (rating BETWEEN 1 AND 5),
  notes       TEXT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Budget alimentaire (cache local, source = Zimboo/Firefly)
CREATE TABLE food_budget_cache (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       TEXT NOT NULL DEFAULT 'default',
  month           TEXT NOT NULL,
  planned_amount  REAL,
  spent_amount    REAL,
  currency        TEXT DEFAULT 'EUR',
  synced_at       TIMESTAMPTZ DEFAULT now(),
  UNIQUE (tenant_id, month)
);
```

---

## 6. Redis — Cles et Channels

| Cle / Channel | Usage | TTL |
|----------------|-------|-----|
| `cache:stock:{tenant}` | Stock Grocy complet | 60s |
| `cache:recipes:{tenant}:{page}` | Liste recettes paginee | 120s |
| `cache:nutrition:{date}:{member}` | Calcul nutrition du jour | 5min |
| `cache:budget:{tenant}:{month}` | Budget Zimboo du mois | 10min |
| `cache:prices:{tenant}` | Prix moyens Firefly par ingredient | 1h |
| `cache:coupons:{tenant}` | Coupons actifs Zimboo | 30min |
| `cache:loyalty:{tenant}` | Soldes fidelite par enseigne | 1h |
| `pubsub:shopping:{listId}` | Sync temps reel shopping collaboratif | — |
| `pubsub:cooking:{sessionId}` | Etat cooking mode (step, timers) | — |
| `queue:vision-process` | File attente photos frigo | — |
| `session:cooking:{userId}` | Etat WakeLock + etape courante | 4h |

---

## 7. LiteLLM — Routage par Cas d'Usage

| Cas d'usage | Modele | Raison |
|-------------|--------|--------|
| Suggestions quotidiennes | `deepseek-v3` | Frequent, simple → eco |
| Planification hebdo AI | `claude-sonnet-4-6` | Raisonnement multi-contraintes |
| Narration cooking TTS | `gpt-4o-mini` | Rapide, TTS-optimized |
| Vision frigo (photo) | `gpt-4o` | Vision multimodale |
| Substitutions economiques | `claude-sonnet-4-6` | Nutrition + prix + gout |
| Drug-food interactions | `claude-opus-4-6` | Securite critique → fiabilite max |
| Chat conversationnel | `deepseek-v3` | Eco, suffisant pour Q&A |
| Adaptation niveau cuisson | `gpt-4o-mini` | Rapide, contextuel |

---

## 8. Activepieces Workflows (30)

### 8.1 Alertes & Anti-Gaspi (#1-#3)

| # | Nom | Trigger | Actions | Output |
|---|-----|---------|---------|--------|
| 1 | `expiry-daily-scan` | Cron 8h | Grocy volatile → filtre J-3 | Notification + badge dashboard |
| 2 | `fifo-rotation-alert` | Cron lundi 9h | Stock par location, tri DLC | "Utiliser d'abord : X, Y, Z" |
| 3 | `leftover-detector` | Webhook Grocy (consumed) | Si reste < portion → LiteLLM recette | Suggestion recette anti-gaspi |

### 8.2 Planification (#4-#6)

| # | Nom | Trigger | Actions | Output |
|---|-----|---------|---------|--------|
| 4 | `weekly-plan-generator` | Bouton Koodia / Cron dim 18h | Stock + Favoris + Profils nutrition + Budget Zimboo → LiteLLM | Plan 7j → POST Mealie + Ase events |
| 5 | `auto-shopping-from-plan` | Apres workflow #4 | Diff plan vs stock | Shopping list Mealie auto |
| 6 | `batch-cooking-planner` | Bouton Koodia | Recettes selectionnees + creneaux Ase libres → LiteLLM | Planning batch + liste consolidee |

### 8.3 Nutrition (#7-#11)

| # | Nom | Trigger | Actions | Output |
|---|-----|---------|---------|--------|
| 7 | `daily-nutrition-tracker` | Cron 22h | Meal plan jour → CIQUAL lookup → calcul macros/micros | Push VictoriaMetrics + alerte deficit |
| 8 | `weekly-nutrition-report` | Cron dim 20h | VictoriaMetrics query 7j + profils | Resume + recommandations |
| 9 | `cure-progress-tracker` | Cron quotidien | Profil cure actif → intake reel vs objectif | Progression % |
| 10 | `allergy-guard` | Avant ajout recette au plan | Ingredients recette vs allergies profils | Alerte si conflit (3 niveaux) |
| 11 | `drug-food-interaction-check` | Avant ajout recette au plan | Ingredients vs medicaments declares | Warning si interaction |

### 8.4 Budget & Economies (#12-#14)

| # | Nom | Trigger | Actions | Output |
|---|-----|---------|---------|--------|
| 12 | `budget-weekly-snapshot` | Cron dimanche | Transactions Firefly tag "food" semaine | Push VictoriaMetrics |
| 13 | `budget-alert` | Apres workflow #12 | Si > seuil budget Zimboo | Notification + mode economique active |
| 14 | `smart-substitution-finder` | Pendant generation shopping list | Pour chaque ingredient : Firefly prix historique + CIQUAL profil nutri + objectif Zimboo | Si objectif = epargne → alternatives moins cheres preservant nutrition |

### 8.5 Intelligence & Memoire (#15-#17)

| # | Nom | Trigger | Actions | Output |
|---|-----|---------|---------|--------|
| 15 | `semantic-recipe-indexer` | Webhook Mealie (nouvelle recette) | Embedding recette → Qdrant upsert | Index semantique a jour |
| 16 | `culinary-memory-update` | Fin cooking mode | Note + recette + duree + rating → Qdrant | Preferences enrichies |
| 17 | `smart-suggestion-engine` | Cron 11h + 17h | Stock + saison + meteo + historique Qdrant + budget restant → LiteLLM | "Ce soir je sugere..." |

### 8.6 Collaboration & Sync (#18-#19)

| # | Nom | Trigger | Actions | Output |
|---|-----|---------|---------|--------|
| 18 | `shopping-sync-broadcast` | Webhook Mealie (list item change) | Redis PubSub → SSE Koodia | Real-time multi-devices |
| 19 | `guest-meal-adapter` | Bouton "Invites ce soir" | Nb convives + profils → recalcul portions | Portions + shopping delta |

### 8.7 Import & Enrichissement (#20-#23)

| # | Nom | Trigger | Actions | Output |
|---|-----|---------|---------|--------|
| 20 | `recipe-url-importer` | POST depuis Koodia | URL → Mealie scrape → Qdrant index → CIQUAL enrichment | Recette importee + nutrition |
| 21 | `barcode-product-enricher` | Scan barcode Koodia | OpenFoodFacts API → Grocy create → CIQUAL match | Produit ajoute avec nutrition |
| 22 | `fridge-vision-processor` | Photo upload Koodia | Image → LiteLLM vision → produits identifies → Grocy stock update | Stock mis a jour |
| 23 | `calendar-meal-sync` | Webhook Ase (event modifie) | Si event meal deplace/supprime → adapter meal plan Mealie | Sync calendrier ↔ planner |

### 8.8 Ase & Zimboo Integration (#24-#27)

| # | Nom | Trigger | Actions | Output |
|---|-----|---------|---------|--------|
| 24 | `calendar-conflict-checker` | Avant planification repas | `getCalendarEvents()` → si RDV 19h-21h | Forcer recette <20min |
| 25 | `meal-reminder-push` | Webhook Ase `event.reminder` | Notification "Preparez le diner dans 30min" | Push Koodia |
| 26 | `receipt-to-stock` | Webhook Zimboo `receipt.processed` | Parse items ticket → match Grocy products → stock add | Inventaire auto-maj |
| 27 | `budget-estimation-on-plan` | Apres plan hebdo genere | Items plan → prix historique Firefly → objectif Zimboo | "Cout estime : 58 EUR (reste 144 EUR)" |

### 8.9 Coupons, Fidelite & Multi-Magasins (#28-#30)

| # | Nom | Trigger | Actions | Output |
|---|-----|---------|---------|--------|
| 28 | `coupon-matcher` | Shopping list generee ou modifiee | Items liste → Zimboo `GET /api/coupons/match?items=[...]` → enrichir items | Badge coupon sur chaque item eligible + total economies potentielles |
| 29 | `coupon-expiry-alert` | Cron quotidien 9h | Zimboo `GET /api/coupons?expiring_within=3d` | Notification "Utilisez votre coupon -2 EUR chez Lidl avant vendredi" |
| 30 | `multi-store-optimizer` | Shopping list finalisee | Pour chaque item : comparer prix par magasin (Firefly historique) + coupons dispo (Zimboo) + points fidelite proches d'un seuil → LiteLLM optimise la repartition | Vue "Split magasin" : Lidl (12 items, ~28 EUR, 1 coupon), Carrefour (8 items, ~19 EUR, 2 coupons) |

**Flux detaille du multi-magasins :**
```
Shopping list finalisee (20 items)
    │
    ▼
Activepieces #30 multi-store-optimizer :
    │
    ├─ 1. Firefly historique : prix moyen par item par magasin
    │     Lait: Lidl 0.89, Carrefour 1.05, Auchan 0.95
    │     Saumon: Lidl 11.90, Carrefour 12.50, Picard 10.90
    │
    ├─ 2. Zimboo coupons match : coupons actifs par magasin
    │     Carrefour: -0.50 EUR rayon frais (expire J+3)
    │     Lidl: -2 EUR des 20 EUR d'achat
    │
    ├─ 3. Zimboo fidelite : soldes points par enseigne
    │     Carrefour: 180 pts (seuil 200 = bon 5 EUR) → 20 pts manquants
    │     Lidl: 45 pts (seuil 100 = bon 3 EUR)
    │
    ├─ 4. LiteLLM optimise :
    │     - Objectif Zimboo = epargne → minimiser cout total
    │     - Bonus si achat rapproche d'un seuil fidelite
    │     - Penalite si trop de magasins (temps trajet)
    │
    └─ 5. Output : split par magasin
          Magasin A : [items], total estime, coupons applicables, pts fidelite gagnes
          Magasin B : [items], total estime, coupons applicables, pts fidelite gagnes
          Total : XX EUR (vs YY EUR sans optimisation = ZZ EUR economises)
```

---

## 9. VictoriaMetrics — Metriques

```
# Nutrition (par membre, par jour)
koodia_nutrition_calories{member="alice",date="2026-03-11"} 1850
koodia_nutrition_protein_g{member="alice",date="2026-03-11"} 72
koodia_nutrition_carbs_g{member="alice",date="2026-03-11"} 220
koodia_nutrition_fat_g{member="alice",date="2026-03-11"} 65
koodia_nutrition_fiber_g{member="alice",date="2026-03-11"} 28

# Cures (progression quotidienne)
koodia_cure_intake_mg{member="alice",cure="iron",date="2026-03-11"} 14
koodia_cure_target_mg{member="alice",cure="iron"} 18

# Budget (par mois, par magasin)
koodia_budget_planned_eur{month="2026-03"} 600
koodia_budget_spent_eur{month="2026-03"} 456
koodia_budget_spent_store_eur{month="2026-03",store="carrefour"} 280
koodia_budget_saved_substitutions_eur{month="2026-03"} 23
koodia_budget_saved_coupons_eur{month="2026-03"} 12.50
koodia_budget_saved_multistore_eur{month="2026-03"} 8.30

# Fidelite (par enseigne)
koodia_loyalty_points{store="carrefour"} 180
koodia_loyalty_threshold{store="carrefour"} 200
koodia_loyalty_points{store="lidl"} 45
koodia_loyalty_threshold{store="lidl"} 100
koodia_coupons_used_count{month="2026-03"} 7
koodia_coupons_expired_unused{month="2026-03"} 1

# Stock
koodia_stock_items_total{location="fridge"} 23
koodia_stock_expired_count 2
koodia_stock_expiring_3d_count 5

# Anti-gaspi
koodia_waste_kg{month="2026-03"} 0.3
koodia_waste_items_count{month="2026-03"} 2
koodia_fifo_compliance_pct{month="2026-03"} 87

# Usage
koodia_cooking_sessions_total{month="2026-03"} 12
koodia_suggestions_accepted{month="2026-03"} 8
koodia_substitutions_accepted{month="2026-03"} 15
```

---

## 10. Grafana Dashboards (3 embarques)

| Dashboard | Panels | Source |
|-----------|--------|--------|
| **Nutrition Tracker** | Calories jour (bar), Macros semaine (stacked area), Micros (heatmap), Jauges vs objectif, Progression cure (gauge) | VictoriaMetrics `koodia_nutrition_*` + `koodia_cure_*` |
| **Budget Alimentaire** | Depenses mois (bar), Par magasin (pie), Par categorie (treemap), Tendance 12 mois (line), Economies totales : substitutions + coupons + multi-magasin (counters), Points fidelite par enseigne (gauge vers seuil) | VictoriaMetrics `koodia_budget_*` + `koodia_loyalty_*` + `koodia_coupons_*` |
| **Anti-Gaspi & Stock** | Gaspillage mensuel (bar), FIFO compliance (gauge), Items expirant (table), Rotation stock (heatmap), Score global (stat) | VictoriaMetrics `koodia_waste_*` + `koodia_stock_*` |

Embed dans Koodia via `<iframe>` Grafana avec `authProxyEnabled` ou token service account (lecture seule).

---

## 11. Boucle Vertueuse Fermee

```
        PLANIFIER                        ACHETER
    ┌──────────────┐              ┌──────────────────┐
    │ Koodia Plan  │              │ Koodia Shopping   │
    │ + LiteLLM AI │──── auto ───▶│ + Substitutions  │
    │ + Stock Grocy│  shopping    │ + Prix Firefly    │
    │ + Budget Zimb│  list #5     │ + Coupons Zimboo  │
    │ + Ase conflit│              │ + Multi-magasins  │
    │              │              │ + Points fidelite │
    └──────┬───────┘              └────────┬──────────┘
           │                               │
     Ase events                     notifyShoppingCompleted()
     + Mealie plan                         │
           │                               ▼
           │                     ┌──────────────────┐
           │                     │ Zimboo: auto-tag  │
           │                     │ transaction food  │
           │                     │ + budget update   │
           │                     │ + coupons deduits │
           │                     │ + pts fidelite +  │
           │                     └────────┬──────────┘
           │                              │
           │                     receipt.processed
           │                     webhook #26
           │                              │
           ▼                              ▼
    ┌──────────────┐              ┌──────────────────┐
    │ CUISINER     │              │ STOCKER           │
    │ Koodia Cook  │              │ Grocy auto-update │
    │ + WakeLock   │◀── rappel ──│ + Barcode scan    │
    │ + TTS        │   Ase #25   │ + Photo vision    │
    │ + Timers     │              │ + FIFO alerts #2  │
    └──────┬───────┘              └──────────────────┘
           │
     Grocy consume
     + Qdrant memory #16
     + VictoriaMetrics
           │
           ▼
    ┌──────────────┐
    │ ANALYSER     │
    │ Grafana dash │
    │ + Nutrition  │
    │ + Budget     │──── feedback ──▶ PLANIFIER (boucle)
    │ + Gaspillage │                  Smart suggestion #17
    │ + Rapports   │                  adapte le prochain plan
    └──────────────┘
```

**Chaque etape nourrit la suivante.** Le systeme apprend et s'ameliore :
- Plus tu cuisines → mieux Qdrant connait tes gouts
- Plus tu achetes → mieux Firefly connait tes prix
- Plus tu planifies → mieux LiteLLM calibre les suggestions
- Plus tu suis ta nutrition → mieux les cures s'ajustent

---

## 12. Integrations Zimboo Detaillees

### 12.1 Budget Repas

Zimboo expose un systeme de budgets par categorie. Le budget "Repas" (ou "Alimentation") est la source de verite.

**Flux :**
1. L'utilisateur configure un budget repas dans Zimboo (ex: 600 EUR/mois)
2. Koodia lit ce budget via `GET /api/budgets?category=food` (Zimboo API ou Firefly API directe)
3. Koodia affiche la jauge dans Dashboard et Planner
4. Activepieces workflow #13 alerte a 80% et 90%
5. Si objectif Zimboo = "epargne" → Activepieces workflow #14 active les substitutions economiques partout

### 12.2 Substitutions Economiques Intelligentes

Quand l'objectif utilisateur dans Zimboo est d'epargner :

**Pendant la generation de shopping list :**
```
Pour chaque ingredient de la liste :
  1. Lookup prix moyen (Firefly historique)
  2. Trouver alternatives meme categorie (CIQUAL)
  3. Comparer nutrition (macros/micros similaires)
  4. Comparer prix (Firefly transactions passees)
  5. Si alternative -20%+ et nutrition equivalente → proposer

Exemple :
  Saumon frais (12.90 EUR/kg) → Maquereau frais (7.50 EUR/kg)
  -42% | Omega-3: +15% | Proteines: equivalent
  "Economie estimee : 2.70 EUR sur cette liste"
```

**Pendant la planification :**
```
Si budget restant < 30% du mois :
  → LiteLLM genere un plan "mode economique"
  → Privilegier legumineuses, oeufs, legumes de saison
  → Afficher estimation cout vs plan normal
```

### 12.3 Receipt → Stock Automatique

```
Zimboo scanne ticket de caisse
    → webhook receipt.processed vers Koodia
    → Activepieces workflow #26 :
        1. Parse items : [{name: "Lait demi-ecreme", qty: 2, price: 1.15}, ...]
        2. Match fuzzy → Grocy products (Qdrant ingredient similarity)
        3. Pour chaque match : POST /api/grocy/stock/{productId}/add
        4. Items non matches → notification "3 articles non reconnus"
    → Stock Grocy a jour sans saisie manuelle
```

### 12.4 Coupons, Bons Plans & Points Fidelite

La gestion des coupons et de la fidelite est **dans Zimboo** (domaine financier). Koodia est consommateur en lecture seule.

**Responsabilites Zimboo (source de verite) :**
- Scanner / saisir / importer des coupons de reduction
- Stocker : montant, magasin, date expiration, conditions (rayon, seuil minimum)
- Gerer les points fidelite par enseigne (solde, historique, seuils de remise)
- Detecter les bons plans (promos, catalogues, API enseignes si dispo)
- API exposee : `GET /api/coupons/match?items=[...]`, `GET /api/coupons?expiring_within=3d`, `GET /api/loyalty/balances`
- Apres courses : deduire coupons utilises, crediter points fidelite

**Responsabilites Koodia (affichage contextuel) :**
- Appeler Zimboo via Activepieces #28 quand une shopping list est generee
- Afficher badges coupons sur les items concernes dans la shopping list
- Afficher total economies potentielles en haut de la liste
- Afficher solde points fidelite par enseigne dans le widget Budget
- Alerter quand un coupon expire bientot (Activepieces #29)

**Flux coupon-to-savings :**
```
Zimboo (gestion)                     Koodia (affichage)
┌───────────────────┐                ┌───────────────────┐
│ Coupons DB        │                │ Shopping List      │
│ ┌───────────────┐ │    match API   │                   │
│ │-0.50 Carrefour│─┼───────────────▶│ Lait     -0.50 EUR│
│ │ rayon frais   │ │                │ [badge coupon]    │
│ │ expire 15/03  │ │                │                   │
│ └───────────────┘ │                │ Saumon            │
│ ┌───────────────┐ │                │ [pas de coupon]   │
│ │-2 EUR Lidl    │─┼───────────────▶│                   │
│ │ des 20 EUR    │ │                │ Total: ~47 EUR    │
│ └───────────────┘ │                │ Coupons: -3.80 EUR│
│                   │                │ Net: ~43.20 EUR   │
│ Fidelite          │                │                   │
│ ┌───────────────┐ │                │ Carrefour: 180pts │
│ │ Carrefour     │─┼───────────────▶│ (20 pts → bon 5€) │
│ │ 180/200 pts   │ │                │                   │
│ └───────────────┘ │                └───────────────────┘
└───────────────────┘
         │
         │ Apres courses
         ▼
┌───────────────────┐
│ Coupons utilises  │
│ -0.50 → deduit    │
│ Points +12 pts    │
│ → 192/200 pts     │
└───────────────────┘
```

### 12.5 Multi-Magasins Intelligent

La liste de courses peut etre splitee par magasin pour maximiser les economies.

**Criteres d'optimisation (Activepieces #30) :**
1. **Prix** : Firefly historique prix par item par magasin
2. **Coupons** : Zimboo coupons actifs par magasin
3. **Fidelite** : Proximite d'un seuil de remise (ex: 20 pts → bon 5 EUR = go chez Carrefour)
4. **Praticite** : Penalite si >2 magasins (temps trajet), bonus si 1 seul magasin
5. **Objectif Zimboo** : Si epargne → optimiser cout ; si confort → minimiser magasins

**Affichage dans Koodia Shopping :**
- Toggle "Vue magasin" en haut de la liste
- Cards par magasin avec : items, total estime, coupons applicables, pts fidelite gagnes
- Barre recapitulative : "Economie totale : 8.30 EUR vs achat tout chez Carrefour"
- Option "Un seul magasin" pour desactiver le split

---

## 13. Integrations Ase Detaillees

### 13.1 Sync Bidirectionnelle

```
Koodia → Ase :
  Plan valide → createWeeklyMealEvents()
  Evenements : "Diner: Risotto champignons" 19h00-19h45
  Categories : [meal, koodia, dinner]

Ase → Koodia :
  Webhook event.reminder (30min avant)
  → Koodia notification "C'est l'heure de preparer le Risotto"
  → Afficher recette en 1 tap → lancer Cook Mode
```

### 13.2 Detection Conflits

```
Avant planification :
  1. getCalendarEvents(lundi, dimanche)
  2. Pour chaque soir avec RDV apres 18h :
     → Marquer comme "soiree chargee"
     → Forcer recette rapide (<20min prep) ou plat prepare la veille
  3. Weekend sans evenements :
     → Suggerer session batch cooking
```

### 13.3 Historique Reel

Les evenements Ase deviennent le journal de ce qui a **reellement** ete cuisine (vs le plan theorique dans Mealie). Difference plan vs reel → insights :
- "Vous avez suivi 80% du plan cette semaine"
- "Le mercredi soir est souvent saute → planifier des repas plus simples"

---

## 14. Differenciation

| Ce qui rend Koodia unique | Pourquoi personne ne le fait | Comment |
|---------------------------|-------------------------------|---------|
| **Proactivite** | Apps food passives (tu cherches) | Activepieces push suggestions basees sur stock + saison + budget + historique |
| **Anti-gaspi intelligent** | Au mieux une date d'expiry | FIFO + leftover detector + substitution → near-zero waste |
| **Budget-aware planning** | Finance et food dans des silos | Zimboo budget repas + Firefly prix → planning adapte au portefeuille |
| **Substitutions eco-nutrition** | Soit prix soit nutrition, jamais les deux | LiteLLM croise Firefly prix + CIQUAL nutrition → alternatives optimales |
| **Nutrition multi-profils** | Aucune app reconcilie une famille | CIQUAL + Qdrant profils + OpenClaw reasoning → 1 repas, 4 profils |
| **Drug-food safety** | Existe en pharma, pas en food | PostgreSQL medications x CIQUAL x Activepieces guard |
| **Receipt → Stock auto** | Saisie manuelle partout | Zimboo scan ticket → Activepieces → Grocy stock update |
| **Vision frigo** | Concept mais jamais integre | Photo → LiteLLM vision → Grocy update → suggestion recette |
| **Calendrier-aware** | Planning deconnecte du quotidien | Ase conflits → adapter complexite repas |
| **Self-hosted & souverain** | Tout est cloud | 100% on-prem, donnees jamais partagees, AI via LiteLLM |
| **Cooking mode mains-libres** | Apps recettes basiques | WakeLock + TTS + swipe + timers + voice feedback |
| **Coupons + fidelite contextuels** | Apps coupons separees du food | Zimboo coupons matche auto sur shopping list + alerte expiration + fidelite seuils |
| **Multi-magasins optimise** | Liste unique sans intelligence prix | Split par magasin basee sur prix + coupons + fidelite + praticite |
| **Boucle fermee** | Chaque app fait son truc | Planifier → Acheter → Cuisiner → Analyser → mieux Planifier |

---

## 15. Roadmap

### Phase 1 — Wire Complet API (2 semaines)

Cabler les hooks manquants aux APIs Mealie et Grocy existantes.

| Feature | Hook/API | Status actuel |
|---------|----------|---------------|
| Import recette par URL | Mealie POST `/recipes/create-url` | Non cable |
| Toggle favoris | Mealie PUT `/recipes/{slug}/favorites` | Non cable |
| Ratings | Mealie PUT `/recipes/{slug}/ratings` | Non cable |
| Delete shopping item | Mealie DELETE item | Non cable |
| Stock transfer | Grocy POST `/stock/transfer` | Non cable |
| CRUD produits | Grocy POST/PUT/DELETE `/objects/products` | Non cable |
| Barcode lookup | Grocy GET `/stock/products/by-barcode/{barcode}` | Non cable |
| Stock journal | Grocy GET `/stock/journal` | Non cable |
| Product prices | Grocy GET `/objects/product_barcodes` | Non cable |
| Consume recipe | Grocy POST `/recipes/{id}/consume` | Non cable |
| QU conversions | Grocy GET `/objects/quantity_unit_conversions` | Non cable |
| Labels/categories | Mealie GET `/organizers/categories` | Non cable |
| Planner rules | Mealie GET `/households/mealplans/rules` | Non cable |
| Meal plan CRUD | Mealie POST/PUT/DELETE mealplans | Partiel (GET only) |
| Shopping list CRUD | Mealie POST/DELETE lists | Partiel (GET + PATCH) |

**Resultat : 32/133 features (24%)**

### Phase 2 — Mode Cuisine MVP + Intelligence (3 semaines)

| Composant | Description |
|-----------|-------------|
| Cook Mode page | Fullscreen, step-by-step, WakeLock, timers, swipe |
| Qdrant setup | 4 collections, recipe indexer, CIQUAL embeddings |
| Recherche semantique | Barre de recherche Qdrant dans recipes |
| Activepieces #1-#6 | Alertes expiry, FIFO, plan AI, auto-shopping, batch cooking |
| Activepieces #15-#17 | Indexer recettes, memoire culinaire, suggestions proactives |
| Fridge vision scan | Upload photo → LiteLLM vision → Grocy stock |
| Ase sync complet | createWeeklyMealEvents + conflit checker + rappels |

**Resultat : 65/133 features (49%)**

### Phase 3 — Nutrition & Budget (3 semaines)

| Composant | Description |
|-----------|-------------|
| PostgreSQL schema | Tables family_members, allergies, medications, cures, CIQUAL |
| CIQUAL import | Script import 3185 aliments, 67 composants |
| Page Nutrition | Profils, allergies, medicaments, cures, graphes |
| Activepieces #7-#11 | Tracker nutrition, rapport hebdo, cure, allergie guard, drug-food |
| Zimboo integration | Budget repas, jauge dashboard, API objectifs |
| Activepieces #12-#14 | Budget snapshot, alertes, substitutions economiques |
| Activepieces #26-#27 | Receipt→stock, estimation cout plan |
| Coupons & fidelite | Zimboo API coupons/match + loyalty/balances → badges Koodia Shopping |
| Multi-magasins | Activepieces #28-#30 : coupon matcher, expiry alert, store optimizer |
| Grafana dashboards | Nutrition + Budget + Anti-gaspi (3 dashboards) + economies coupons |
| VictoriaMetrics | Push metriques nutrition/budget/stock/gaspillage/coupons/fidelite |

**Resultat : 106/133 features (80%)**

### Phase 4 — Excellence & Polish (2 semaines)

| Composant | Description |
|-----------|-------------|
| Shopping collab | Redis PubSub + SSE real-time multi-devices |
| TTS cooking | Web Speech API narration etapes |
| Activepieces #18-#19 | Shopping sync, guest adapter |
| Activepieces #20-#23 | URL importer, barcode enricher, vision processor, calendar sync |
| Activepieces #24-#25 | Conflict checker, meal reminder push |
| Multi-profil reconciliation | OpenClaw agent pour repas famille complexe |
| Offline mode | Service Worker + IndexedDB (PWA) |
| Portions dynamiques | Scaling recette + guest mode |
| PDF export nutrition | Bilan mensuel exportable |
| Score anti-gaspi gamification | Badges, streaks, comparaison mois precedent |

**Resultat : 126/133 features (95%)**

Les 7 features restantes (voice commands avances, micro-batch label printing, mode split ecran, calendrier Baikal avance, multi-device cooking sync, export ICAL, API enseignes promos auto) sont du polish post-launch.

---

## 16. Matrice Feature ↔ Infrastructure

| Feature | Mealie | Grocy | Ase | Zimboo | Firefly | ActiveP | LiteLLM | Qdrant | PG | Redis | VM | Grafana | OClaw |
|---------|--------|-------|-----|--------|---------|---------|---------|--------|-----|-------|-----|---------|-------|
| Recettes liste | X | | | | | | | | | | | | |
| Recherche semantique | | | | | | | | X | | | | | |
| Faisabilite stock | X | X | | | | | | | | | | | |
| Import URL | X | | | | | X | | X | | | | | |
| Cook Mode | X | X | | | | | X | | X | X | | | |
| Meal plan AI | X | X | X | X | X | X | X | X | | | | | |
| Conflit calendrier | | | X | | | X | | | | | | | |
| Shopping auto | X | X | | | | X | | | | | | | |
| Shopping collab | X | | | | | X | | | | X | | | |
| Substitutions eco | | | | X | X | X | X | | | X | | | |
| Budget jauge | | | | X | X | | | | | X | X | X | |
| Inventory | | X | | | | | | | | | | | |
| Scan barcode | | X | | | | X | | | | | | | |
| Vision frigo | | X | | | | X | X | | | | | | |
| Receipt→stock | | X | | X | | X | | X | | | | | |
| Profils nutrition | | | | | | | | X | X | | | | |
| Calcul CIQUAL | | | | | | X | | X | X | | X | | |
| Allergies guard | X | | | | | X | | | X | | | | |
| Drug-food check | X | | | | | X | | | X | | | | |
| Cures | | | | | | X | | | X | | X | X | |
| Dashboard nutrition | | | | | | | | | | | X | X | |
| Dashboard budget | | | | X | X | | | | | | X | X | |
| Anti-gaspi | | X | | | | X | X | | | | X | X | |
| Menu therapeutique | X | X | | | | | | X | X | | | | X |
| Multi-profil repas | X | X | | | | | | X | X | | | | X |
| Coupons shopping | | | | X | | X | | | | X | | | |
| Points fidelite | | | | X | | X | | | | X | X | X | |
| Multi-magasins | | | | X | X | X | X | | | | X | | |

---

## 17. Securite

| Risque | Mitigation |
|--------|-----------|
| Drug-food interaction faux negatif | Double validation : Activepieces rule-based + LiteLLM AI | Disclaimer "consulter medecin" |
| Allergie non detectee | 3 niveaux severite, anaphylaxie = blocage dur (pas de bypass) |
| Donnees medicales | PostgreSQL chiffre, pas de cloud, VPN-only |
| Budget expose | Zimboo API authentifiee, Koodia cache local |
| LiteLLM hallucination nutrition | CIQUAL = source de verite (base officielle ANSES), LiteLLM = suggestions uniquement |
| Webhook forgery | Tous les webhooks valides par `X-Webhook-Key` |
| Vision frigo erreur | Resultats en "suggestion" avec confirmation manuelle avant stock update |
| Coupons frauduleux | Zimboo valide authenticite, Koodia affiche uniquement (pas de saisie) |
| Points fidelite desync | Cache Redis 1h, fallback Zimboo API, jamais de modification depuis Koodia |

---

## 18. KPIs de Succes

| KPI | Cible | Mesure |
|-----|-------|--------|
| Gaspillage alimentaire | < 1kg/mois | `koodia_waste_kg` VictoriaMetrics |
| Adherence plan repas | > 80% | Events Ase completes / planifies |
| Budget respecte | < 100% budget Zimboo | `koodia_budget_spent / planned` |
| Couverture nutritionnelle | > 90% AJR pour chaque membre | `koodia_nutrition_*` vs objectifs |
| Economies substitutions | > 10% du budget | `koodia_budget_saved_substitutions_eur` |
| Economies coupons | > 5% du budget | `koodia_budget_saved_coupons_eur` |
| Economies multi-magasins | > 3% du budget | `koodia_budget_saved_multistore_eur` |
| Coupons utilises / expires | > 85% utilisation | `koodia_coupons_used / (used + expired_unused)` |
| FIFO compliance | > 85% | `koodia_fifo_compliance_pct` |
| Cooking sessions / mois | > 15 | `koodia_cooking_sessions_total` |
| Temps moyen planning hebdo | < 2 min | Timer AI Planner |
