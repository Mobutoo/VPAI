#!/usr/bin/env python3
"""run_eval.py — Harness d'éval retrieval mémoire (contrat RAG v3 2026-06-10).

Évalue une collection Qdrant contre le golden-set (golden.yml) :
recall@1, recall@5, MRR@10, breakdown par doc_kind.

Match = AU MOINS UN expected_path (`repo:relative_path`) présent dans le
top-k (payload Qdrant `repo` + `relative_path`).

Modes :
  - dense  : vecteur dense seul. Rétro-compat : détection auto du schéma de
    collection (vecteur unnamed = memory_v2 ; vecteur nommé "dense" = memory_v3).
  - hybrid : Query API `query_points` avec prefetch dense (limit 30,
    using="dense") + sparse BM25 (limit 30, using="bm25") -> fusion RRF.
    Requiert une collection à vecteurs nommés dense+bm25 (memory_v3) et
    `fastembed` installé (lazy-import — le mode dense n'en dépend pas).

Tourne sur le venv worker Waza :
  set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a
  /opt/workstation/ai-memory-worker/.venv/bin/python scripts/memory/eval/run_eval.py \
    --collection memory_v2 --mode dense

Comparaison : --baseline <eval.json> affiche le diff par métrique.
Sortie JSON : .planning/eval/ (défaut), STRICTEMENT lecture seule côté Qdrant.

Mode gate (garde-fou anti-dérive silencieuse, audit mémoire 2026-07-17) :
  --assert-thresholds fait échouer le run (exit 3) si recall@1 ou mrr@10 tombe
  sous un seuil. N'altère PAS le mode rapport par défaut (sans le flag, le
  comportement/exit-code est inchangé) — réservé au run automatique/CI.
  Seuils configurables via --min-recall1/--min-mrr10 ou env
  EVAL_MIN_RECALL_1/EVAL_MIN_MRR_10 (défauts 0.70/0.80, cf audit).

Extensions 2026-07-17 (restauration recall@1, ops/loops/reports/2026-07-17-*) :
  - --prefetch-limit N : top-K candidats par canal avant fusion (défaut 30, contrat).
  - --fusion rrf|dbsf : stratégie Qdrant native (mode hybrid, FusionQuery serveur).
  - --manual-fusion : bypass FusionQuery serveur -> 2 requêtes séparées (dense-only,
    sparse-only, top --prefetch-limit chacune) + RRF pondéré recalculé côté client
    avec --rrf-k et --dense-weight/--sparse-weight. Qdrant-client 1.16 n'expose PAS
    le k RRF serveur (FusionQuery n'a qu'un champ `fusion`) -> seul --manual-fusion
    permet de le faire varier.
  - --rerank-light : cross-encoder léger (fastembed TextCrossEncoder, défaut
    Xenova/ms-marco-MiniLM-L-6-v2, ~90MB ONNX) rerank les --rerank-candidates
    premiers hits fusionnés sur le TEXTE COMPLET du chunk (payload `text`, PAS le
    snippet 160 car. — un cross-encoder jugé sur 30 mots est aveugle). Latence par
    requête loggée (`rerank_timings` dans le rapport JSON, médiane/max) — objectif
    <1.5s/requête pour un usage R0 interactif (cf bge-reranker-v2-m3 : 9.8s médiane,
    disqualifié, AI-MEMORY-AGENT-PROTOCOL.md §3.6).
  Défaut (aucun de ces flags) : comportement STRICTEMENT identique à avant (RRF
  serveur, prefetch=30, pas de rerank) — sibling test de non-régression obligatoire
  après modif de ce fichier (LOI R4/R6) : rejouer sans flag doit reproduire le
  dernier rapport commité au point près.

Extension 2026-07-17 (bis) — retrieval SCOPÉ par métadonnée (expérience filtre
Qdrant repo/wing/topic, ops/loops/reports/2026-07-17-scoped-retrieval-proof.md) :
  - --scope-file PATH : JSON [{"query": str, "values": [str, ...]}, ...] — filtre
    PAR QUESTION (contrairement à --repo/--doc-kind/--topic globaux inexistants ici,
    volontairement absents avant cette extension). Valeurs vides/absentes -> pas de
    filtre pour cette question (log warning, comportement = variante globale).
  - --scope-field {repo,wing,topic} : champ Qdrant ciblé par --scope-file (requis
    conjointement). Filtre appliqué aux DEUX canaux du prefetch hybrid (dense+bm25),
    même pattern que search_memory.py build_filter().
  - Par question filtrée, calcule empiriquement "in_scope" (bool) via client.count()
    AVANT la recherche vectorielle : au moins un expected_path (repo+relative_path)
    a-t-il un point dans la collection sous ce filtre ? Rapport JSON expose
    "filter_miss_rate" (fraction de questions où in_scope=False, cf protocole
    "filtre-miss = la bonne réponse exclue du filtre").
  Défaut (--scope-file absent) : comportement byte-identique à avant (extra_filter
  reste None partout) — sibling test rejoué 2026-07-17 (cf rapport).

Extension 2026-07-18 (T0.2) — --scope-mode {filter,boost} (formalisation,
ops/loops/plans/2026-07-17-scoped-retrieval-implementation.md) :
  - --scope-mode filter (DÉFAUT) : comportement pré-existant ci-dessus — `must`
    Qdrant dur sur --scope-field/--scope-file. Borne haute mesurée (la preuve
    2026-07-17), mais un `must` exclusif PEUT exclure une réponse hors-scope
    (downside cross-wing non mesuré sur le golden VPAI-mono actuel, cf rapport
    §5). N'est PAS la conception retenue pour le pipeline live (cf T1.1).
  - --scope-mode boost : AUCUN filtre Qdrant. Récupère --scope-boost-candidates
    résultats GLOBAUX (non filtrés, même requête fusionnée DBSF/RRF que le
    contrôle) puis ADDITIONNE +--scope-boost-weight au score fusionné de chaque
    point dont payload[--scope-field] intersecte les valeurs --scope-file de la
    question, puis retrie (retri stable : égalités gardent l'ordre de fusion
    d'origine). Simule DANS LE HARNAIS le mécanisme pipeline de T1.1 (bonus
    additif post-fusion, PAS un filtre) — implémentation pipeline réelle
    (search_memory.py/mcp_search.py) hors périmètre de ce fichier. Un point
    hors-scope N'EST JAMAIS EXCLU : sans bonus, il reste classé selon son score
    fusionné d'origine et peut toujours l'emporter (contrainte de conception #1
    du plan — boost, jamais `must` exclusif). Une question dont la vraie réponse
    est hors-scope (in_scope=False) garde donc son rang GLOBAL en boost, alors
    qu'elle deviendrait un miss forcé en filter — c'est précisément l'écart de
    downside que ce mode existe pour mesurer plus tard sur un golden cross-wing
    (T0.1 + T2.1), pas pour l'annuler.
  - --scope-boost-weight FLOAT (défaut 0.2) : magnitude du bonus additif, à
    comparer à l'échelle des scores fusionnés DBSF exact=True observée (sonde
    2026-07-18, 10 questions golden, exact=True) : écarts inter-rangs typiques
    ~0.05-0.5, scores absolus ~0.5-2.5. 0.2 est un poids MODÉRÉ (peut faire
    remonter un candidat proche, pas déclasser un score largement dominant) —
    tuning fin réservé à T2.1 (sweep sur golden enrichi).
  - --scope-boost-candidates INT (défaut 30 = prefetch_limit contrat) : taille
    du pool global récupéré avant retri boost (doit être >= --limit pour laisser
    de la marge de réordonnancement ; sans ça le boost ne peut jamais faire
    remonter un candidat déjà hors de la fenêtre récupérée).
  Les DEUX modes rapportent "filter_miss_rate" identiquement (le calcul
  in_scope/check_in_scope est un ORACLE indépendant du mode de retrieval — même
  vérité-terrain, cf check_in_scope) ET un recall@1 HONNÊTE : aucun des deux
  modes ne credite artificiellement une question scope-miss — le rang utilisé
  pour recall@1/recall@5/mrr@10 est TOUJOURS le rang réel obtenu par la
  recherche (filtrée ou boostée), jamais un floor/override basé sur in_scope.
  Défaut (--scope-mode omis, ou --scope-file absent) : comportement byte-
  identique à avant (extra_filter reste None sauf si scope_mode=filter ET
  scope-file fourni — càd. l'ancien comportement pré-2026-07-18 exact).

Extension 2026-07-18 (T2.1) — --scope-field repo_wing (sweep MEMORY_SCOPE_BOOST_
WEIGHT sur golden enrichi, ops/loops/plans/2026-07-17-scoped-retrieval-
implementation.md §Phase 2) :
  - --scope-field repo_wing : --scope-file a le schéma [{"query":str,
    "repo":str|null,"wing":str|null}] (PAS "values") — le scope de CHAQUE
    question, dérivé de son asked_from (T1.2 derive_scope_from_cwd simulé), pas
    de la réponse attendue. Réplique FIDÈLEMENT mcp_search.py::_apply_scope_boost
    (T1.1, prod live) : bonus UNIQUE (+weight, pas +2*weight) si payload['repo']
    == repo OU payload['wing'] == wing, jamais les deux cumulés. Un scope-field
    "repo" seul (le mode pré-existant) sous-mesurerait le downside cross-wing —
    en prod le bonus wing profite à TOUT repo du même wing, plus large qu'un
    match repo exact (cf revue superviseur 2026-07-18 avant implémentation).
  - Fonctions dédiées (parallèles aux génériques existantes, aucune régression
    sur --scope-field {repo,wing,topic}) : load_scope_map_repo_wing,
    check_in_scope_repo_wing (oracle OR), apply_scope_boost_repo_wing (bonus OR).
  - Sibling test 2026-07-18 : rejeu sans --scope-file sur le golden 89q
    reproduit exactement le rapport committé (fixup2, 2026-07-17T23:09) —
    recall@1 0.6629 / recall@5 0.9775 / mrr@10 0.7897.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from qdrant_client import QdrantClient
from qdrant_client import models as qmodels

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[2]  # scripts/memory/eval -> racine VPAI
DEFAULT_GOLDEN = EVAL_DIR / "golden.yml"
DEFAULT_OUT_DIR = REPO_ROOT / ".planning" / "eval"
DEFAULT_CONFIG = "/opt/workstation/configs/ai-memory-worker/config.yml"
PREFETCH_LIMIT = 30  # contrat : prefetch dense/sparse limit 30 (défaut --prefetch-limit)
MRR_K = 10

# RRF k : Qdrant défaut = 2 (PAS 60, la valeur "standard" du papier Cormack et al. 2009
# reprise par la plupart des libs IR) — vérifié doc officielle
# https://qdrant.tech/documentation/concepts/hybrid-queries/ ("k is a constant, set to 2
# by default"), configurable côté serveur depuis v1.16.0 via query=RrfQuery(rrf=Rrf(k=N))
# (qdrant-client 1.16.2 expose bien RrfQuery/Rrf — vérifié introspection modèles pydantic).
# k=2 est TRÈS agressif (1/(2+0)=0.50 vs 1/(2+2)=0.25 : un doc qui glisse de 2 rangs sur UN
# canal perd déjà la moitié de son score de ce canal) -> hypothèse Piste B : un k plus grand
# lisse le bruit de classement introduit par la croissance du corpus (cf audit §3).
DEFAULT_RRF_K = 2  # défaut serveur Qdrant — PAS le "60" de la littérature générique
DEFAULT_RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
DEFAULT_FASTEMBED_CACHE = "/opt/workstation/data/ai-memory-worker/fastembed-cache"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Eval retrieval mémoire (golden-set).")
    parser.add_argument("--collection", required=True, help="Collection Qdrant cible")
    parser.add_argument("--mode", choices=["dense", "hybrid"], default="dense")
    parser.add_argument("--limit", type=int, default=10, help="top-k récupéré (>= 10 pour MRR@10)")
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN), help="Chemin golden.yml")
    parser.add_argument("--out", default=None, help="Fichier JSON de sortie (défaut .planning/eval/)")
    parser.add_argument("--baseline", default=None, help="JSON d'une éval précédente -> diff par métrique")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="config.yml worker (modèle/Qdrant)")
    parser.add_argument("--max-questions", type=int, default=None,
                        help="Sous-ensemble des N premières questions (smoke test)")
    parser.add_argument(
        "--assert-thresholds", action="store_true",
        help="Mode gate (CI/cron) : exit 3 si recall@1 ou mrr@10 sous seuil. "
             "N'altère pas le rapport JSON ni le mode par défaut.",
    )
    parser.add_argument(
        "--min-recall1", type=float,
        default=float(os.getenv("EVAL_MIN_RECALL_1", "0.70")),
        help="Seuil recall@1 pour --assert-thresholds (défaut 0.70, env EVAL_MIN_RECALL_1)",
    )
    parser.add_argument(
        "--min-mrr10", type=float,
        default=float(os.getenv("EVAL_MIN_MRR_10", "0.80")),
        help="Seuil mrr@10 pour --assert-thresholds (défaut 0.80, env EVAL_MIN_MRR_10)",
    )
    parser.add_argument("--prefetch-limit", type=int, default=PREFETCH_LIMIT,
                        help=f"top-K candidats par canal avant fusion (défaut {PREFETCH_LIMIT}).")
    parser.add_argument(
        "--fusion", choices=["rrf", "dbsf"],
        default=os.environ.get("MEMORY_FUSION_MODE", "dbsf").strip().lower(),
        help="Stratégie de fusion Qdrant native (mode hybrid uniquement). Défaut = "
             "MEMORY_FUSION_MODE (mcp_search.py/search_memory.py en prod), sinon 'dbsf' "
             "(restauration recall@1 2026-07-17). Override --fusion rrf pour le sibling "
             "test / rejeu du gate hebdo côté RRF.",
    )
    parser.add_argument("--rrf-k", type=int, default=None,
                        help=f"k RRF natif serveur (RrfQuery(rrf=Rrf(k=N))), Qdrant >=1.16. "
                             f"Défaut serveur = {DEFAULT_RRF_K} si omis (pas de override).")
    parser.add_argument("--manual-fusion", action="store_true",
                        help="Bypass FusionQuery serveur : 2 requêtes séparées (dense/sparse) "
                             "+ RRF pondéré client (--rrf-k/--dense-weight/--sparse-weight). "
                             "Seul moyen de pondérer les CANAUX (RRF serveur est rank-only).")
    parser.add_argument("--dense-weight", type=float, default=1.0,
                        help="Poids canal dense pour --manual-fusion (défaut 1.0).")
    parser.add_argument("--sparse-weight", type=float, default=1.0,
                        help="Poids canal sparse/BM25 pour --manual-fusion (défaut 1.0).")
    parser.add_argument("--rerank-light", action="store_true",
                        help="Rerank cross-encoder léger (fastembed TextCrossEncoder) sur le "
                             "texte complet des --rerank-candidates premiers hits fusionnés.")
    parser.add_argument("--rerank-light-model", default=DEFAULT_RERANK_MODEL,
                        help=f"Modèle fastembed TextCrossEncoder (défaut {DEFAULT_RERANK_MODEL}).")
    parser.add_argument("--rerank-candidates", type=int, default=20,
                        help="Nombre de hits fusionnés (top-N) soumis au rerank léger (défaut 20).")
    parser.add_argument("--rerank-max-chars", type=int, default=None,
                        help="Tronque le texte payload à N caractères avant rerank (défaut : "
                             "texte complet jusqu'à chunk_size=1600 — coûteux en latence CPU "
                             "ARM, cf découverte 2026-07-17 : 9-11s/requête à texte complet, "
                             "quasi identique au modèle lourd malgré 23M vs 568M params).")
    parser.add_argument("--fastembed-cache", default=os.getenv("FASTEMBED_CACHE_PATH", DEFAULT_FASTEMBED_CACHE),
                        help="Cache modèles fastembed (défaut FASTEMBED_CACHE_PATH ou config worker).")
    parser.add_argument("--exact", action="store_true",
                        help="Recherche HNSW EXACTE (SearchParams(exact=True), pas d'approximation) "
                             "sur chaque canal. Découverte 2026-07-17 : deux rejeux identiques "
                             "(même collection gelée, même code) donnent des recall@1 différents "
                             "de plusieurs points (8/76 questions instables) — approximation HNSW, "
                             "PAS un bug de thread ni de corpus. --exact élimine cette source de "
                             "bruit pour des comparaisons Piste A/B fiables (plus lent, usage éval "
                             "uniquement, jamais en prod interactif).")
    parser.add_argument("--scope-file", default=None,
                        help="JSON [{\"query\":str,\"values\":[str,...]}] — filtre Qdrant PAR "
                             "QUESTION sur --scope-field (expérience retrieval scopé, cf docstring "
                             "module). Défaut absent -> aucun filtre, comportement inchangé.")
    parser.add_argument("--scope-field", choices=["repo", "wing", "topic", "repo_wing"], default=None,
                        help="Champ Qdrant ciblé par --scope-file (requis si --scope-file fourni). "
                             "'repo_wing' (T2.1) : --scope-file a le schéma "
                             "[{\"query\":str,\"repo\":str|null,\"wing\":str|null}] — OR repo/wing, "
                             "réplique fidèlement le boost prod (mcp_search.py::_apply_scope_boost).")
    parser.add_argument(
        "--scope-mode", choices=["filter", "boost"], default="filter",
        help="Mode d'application de --scope-file/--scope-field (T0.2, cf docstring module). "
             "'filter' (défaut) = must Qdrant dur, comportement pré-existant 2026-07-17. "
             "'boost' = bonus de score additif post-fusion sur candidats globaux, jamais "
             "d'exclusion. No-op si --scope-file absent.",
    )
    parser.add_argument(
        "--scope-boost-weight", type=float, default=0.2,
        help="Bonus additif appliqué au score fusionné des points in-scope en "
             "--scope-mode boost (défaut 0.2, cf docstring module pour la calibration).",
    )
    parser.add_argument(
        "--scope-boost-candidates", type=int, default=PREFETCH_LIMIT,
        help=f"Taille du pool global (non filtré) récupéré avant retri boost "
             f"(défaut {PREFETCH_LIMIT} = prefetch_limit contrat). Doit être >= --limit.",
    )
    return parser.parse_args()


def load_scope_map(path: str) -> dict[str, list[str]]:
    """Charge --scope-file -> dict query(str) -> values(list[str]). Pure — pas de Qdrant."""
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    return {e["query"]: e.get("values") or [] for e in entries}


def load_scope_map_repo_wing(path: str) -> dict[str, dict]:
    """Charge --scope-file (schéma --scope-field repo_wing) -> dict query(str) ->
    {"repo": str|None, "wing": str|None}. Pure — pas de Qdrant.

    Extension T2.1 (sweep boost, plan ops/loops/plans/2026-07-17-scoped-retrieval-
    implementation.md §Phase 2) : réplique FIDÈLEMENT le scope tel que dérivé par
    T1.2 (memory_core.derive_scope_from_cwd) et consommé par T1.1
    (mcp_search.py::_apply_scope_boost) — repo ET wing, PAS un seul champ. Un
    scope-field unique ("repo" seul) sous-mesurerait le downside cross-wing : en
    prod, le bonus wing (plus large qu'un repo) profite à TOUT le wing d'où la
    question est posée, pas seulement au repo exact — cf. revue superviseur
    2026-07-18 (advisor, avant implémentation)."""
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    return {e["query"]: {"repo": e.get("repo"), "wing": e.get("wing")} for e in entries}


def check_in_scope(client: QdrantClient, collection: str, scope_filter: "qmodels.Filter",
                    expected_paths: list[str]) -> bool:
    """True si AU MOINS UN expected_path (repo:relative_path) a >=1 point dans la
    collection sous scope_filter — vérité empirique (count exact), indépendante du
    classement retourné par la recherche vectorielle. Lecture seule (client.count)."""
    for ep in expected_paths:
        repo, _, rel_path = ep.partition(":")
        conditions = list(scope_filter.must or [])
        conditions.append(qmodels.FieldCondition(key="repo", match=qmodels.MatchValue(value=repo)))
        conditions.append(qmodels.FieldCondition(key="relative_path", match=qmodels.MatchValue(value=rel_path)))
        result = client.count(
            collection_name=collection,
            count_filter=qmodels.Filter(must=conditions),
            exact=True,
        )
        if result.count > 0:
            return True
    return False


def check_in_scope_repo_wing(
    client: QdrantClient, collection: str, repo: str | None, wing: str | None,
    expected_paths: list[str],
) -> bool:
    """Variante OR de check_in_scope pour --scope-field repo_wing (T2.1) : True si
    AU MOINS UN expected_path a >=1 point sous (repo==repo OU wing==wing) — même
    sémantique OR que mcp_search.py::_apply_scope_boost (in_scope()), pour que
    filter_miss_rate reste une mesure honnête de ce que le boost considère
    in-scope (pas juste le repo)."""
    if not repo and not wing:
        return False
    should: list[qmodels.FieldCondition] = []
    if repo:
        should.append(qmodels.FieldCondition(key="repo", match=qmodels.MatchValue(value=repo)))
    if wing:
        should.append(qmodels.FieldCondition(key="wing", match=qmodels.MatchValue(value=wing)))
    for ep in expected_paths:
        ep_repo, _, rel_path = ep.partition(":")
        conditions = [
            qmodels.FieldCondition(key="repo", match=qmodels.MatchValue(value=ep_repo)),
            qmodels.FieldCondition(key="relative_path", match=qmodels.MatchValue(value=rel_path)),
            qmodels.Filter(should=should),
        ]
        result = client.count(
            collection_name=collection,
            count_filter=qmodels.Filter(must=conditions),
            exact=True,
        )
        if result.count > 0:
            return True
    return False


def check_thresholds(metrics: dict, min_recall1: float, min_mrr10: float) -> list[str]:
    """Seuils franchis (liste vide = gate OK). Pure — testable sans Qdrant."""
    failures = []
    recall1 = metrics.get("recall@1", 0.0)
    mrr10 = metrics.get("mrr@10", 0.0)
    if recall1 < min_recall1:
        failures.append(f"recall@1 {recall1:.4f} < seuil {min_recall1:.4f}")
    if mrr10 < min_mrr10:
        failures.append(f"mrr@10 {mrr10:.4f} < seuil {min_mrr10:.4f}")
    return failures


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def make_client(config: dict) -> QdrantClient:
    return QdrantClient(
        url=os.getenv("QDRANT_URL", config["qdrant_url"]),
        api_key=os.getenv("QDRANT_API_KEY"),
        timeout=int(os.getenv("QDRANT_TIMEOUT", config.get("qdrant_timeout", 30))),
        verify=str(os.getenv("QDRANT_VERIFY_TLS", config.get("qdrant_verify_tls", True))).lower() == "true",
        check_compatibility=False,  # serveur 1.18 vs client 1.16 — warning inutile
    )


def detect_schema(client: QdrantClient, collection: str) -> dict:
    """Détecte le schéma de la collection : vecteur unnamed (v2) ou nommés (v3).

    Retourne {"named": bool, "dense_name": str|None, "sparse_names": [str...]}.
    """
    info = client.get_collection(collection)
    vectors = info.config.params.vectors
    sparse = info.config.params.sparse_vectors or {}
    if isinstance(vectors, dict):
        return {
            "named": True,
            "dense_name": "dense" if "dense" in vectors else next(iter(vectors), None),
            "sparse_names": sorted(sparse.keys()),
        }
    return {"named": False, "dense_name": None, "sparse_names": sorted(sparse.keys())}


class DenseEncoder:
    """Encodeur de requêtes dense — mêmes invariants que search_memory.py."""

    def __init__(self, config: dict) -> None:
        from sentence_transformers import SentenceTransformer  # lazy: import lourd

        emb = config["embedding"]
        self.model = SentenceTransformer(emb["model_name"])
        self.prompt_name = emb["query_prompt_name"]
        self.normalize = bool(emb["normalize_embeddings"])

    def encode_queries(self, queries: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            queries,
            prompt_name=self.prompt_name,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]


class SparseEncoder:
    """Encodeur sparse BM25 (FastEmbed Qdrant/bm25) — requêtes uniquement.

    Lazy : fastembed n'est importé qu'en mode hybrid. Côté requête le texte
    sparse est la query brute (build_sparse_text du contrat concerne les
    documents : relative_path + section + chunk_text).
    """

    MODEL_NAME = "Qdrant/bm25"

    def __init__(self) -> None:
        try:
            from fastembed import SparseTextEmbedding  # lazy import
        except ImportError as exc:  # message actionnable, pas de crash obscur
            raise SystemExit(
                "mode hybrid: paquet `fastembed` absent du venv. "
                "Installer fastembed (sibling test /tmp d'abord — contrat RAG v3) "
                f"ou utiliser --mode dense. ({exc})"
            )
        self.model = SparseTextEmbedding(model_name=self.MODEL_NAME)

    def encode_query(self, query: str) -> "qmodels.SparseVector":
        emb = next(iter(self.model.query_embed(query)))
        return qmodels.SparseVector(
            indices=emb.indices.tolist(), values=emb.values.tolist()
        )


PAYLOAD_FIELDS = ["repo", "relative_path", "doc_kind", "section", "text", "title", "wing", "topic"]
# wing/topic ajoutés 2026-07-18 (T0.2) : requis par apply_scope_boost() pour lire
# payload[scope_field] quand scope_field != "repo" (repo était déjà présent). N'affecte
# pas evaluate()/aggregate() (lisent uniquement repo+relative_path) ni le JSON de sortie
# ("details" ne stocke pas le payload complet) -> non-régression métriques inchangée.


def run_query(
    client: QdrantClient,
    collection: str,
    mode: str,
    schema: dict,
    dense_vector: list[float],
    sparse_vector: "qmodels.SparseVector | None",
    limit: int,
    prefetch_limit: int = PREFETCH_LIMIT,
    fusion: str = "rrf",
    rrf_k: int | None = None,
    exact: bool = False,
    extra_filter: "qmodels.Filter | None" = None,
):
    """Une requête top-k. Dense legacy (unnamed) ET v3 (nommé) supportés.

    with_payload inclut désormais `text` (chunk complet) — nécessaire au rerank léger
    (un cross-encoder jugé sur le snippet 160 car. est aveugle, cf docstring module).
    Coût : payload plus lourd sur le réseau, négligeable pour un harnais d'éval 76 q.

    extra_filter (extension 2026-07-17 bis) : filtre appliqué aux DEUX canaux du
    prefetch hybrid (dense+bm25) — expérience retrieval scopé. None par défaut
    (comportement inchangé).
    """
    search_params = qmodels.SearchParams(exact=True) if exact else None
    if mode == "hybrid":
        prefetch = [
            qmodels.Prefetch(query=dense_vector, using="dense", limit=prefetch_limit,
                              params=search_params, filter=extra_filter),
            qmodels.Prefetch(query=sparse_vector, using="bm25", limit=prefetch_limit,
                              params=search_params, filter=extra_filter),
        ]
        if fusion == "dbsf":
            fusion_query: object = qmodels.FusionQuery(fusion=qmodels.Fusion.DBSF)
        elif rrf_k is not None:
            # k RRF natif serveur (Qdrant >=1.16, défaut serveur k=2 — cf DEFAULT_RRF_K).
            fusion_query = qmodels.RrfQuery(rrf=qmodels.Rrf(k=rrf_k))
        else:
            fusion_query = qmodels.FusionQuery(fusion=qmodels.Fusion.RRF)
        response = client.query_points(
            collection_name=collection,
            prefetch=prefetch,
            query=fusion_query,
            limit=limit,
            with_payload=PAYLOAD_FIELDS,
            with_vectors=False,
        )
    else:
        kwargs = {}
        if schema["named"]:
            kwargs["using"] = schema["dense_name"]
        response = client.query_points(
            collection_name=collection,
            query=dense_vector,
            limit=limit,
            with_payload=PAYLOAD_FIELDS,
            with_vectors=False,
            search_params=search_params,
            query_filter=extra_filter,
            **kwargs,
        )
    return response.points


def run_channel_query(
    client: QdrantClient,
    collection: str,
    using: str,
    vector,
    limit: int,
    exact: bool = False,
):
    """Requête mono-canal (dense OU sparse seul, PAS de fusion serveur) — brique de
    --manual-fusion. Payload complet (cf PAYLOAD_FIELDS) pour permettre le rerank léger
    en aval sans requête supplémentaire."""
    response = client.query_points(
        collection_name=collection,
        query=vector,
        using=using,
        limit=limit,
        with_payload=PAYLOAD_FIELDS,
        with_vectors=False,
        search_params=qmodels.SearchParams(exact=True) if exact else None,
    )
    return response.points


def manual_rrf_fusion(
    dense_points, sparse_points, k: float, dense_weight: float, sparse_weight: float, limit: int,
):
    """RRF pondéré par canal recalculé côté client (rang 0-based, comme Qdrant —
    cf doc officielle : 'Qdrant uses zero-based rank positions'). Seul moyen de faire
    varier k ET pondérer dense vs sparse indépendamment (FusionQuery serveur ne pondère
    pas les canaux, RrfQuery ne fait varier QUE k, pas de poids par canal).

    Dédup par point id (un même chunk peut apparaître dans les deux canaux) ; le point
    "gagnant" conservé pour le payload est celui du canal dense s'il est présent (score
    dense_score aval en dépend), sinon sparse.
    """
    scores: dict[str, float] = {}
    point_by_id: dict[str, object] = {}
    for rank, point in enumerate(dense_points):
        pid = str(point.id)
        scores[pid] = scores.get(pid, 0.0) + dense_weight / (k + rank)
        point_by_id[pid] = point
    for rank, point in enumerate(sparse_points):
        pid = str(point.id)
        scores[pid] = scores.get(pid, 0.0) + sparse_weight / (k + rank)
        if pid not in point_by_id:
            point_by_id[pid] = point
    ordered_ids = sorted(scores, key=lambda pid: scores[pid], reverse=True)
    return [point_by_id[pid] for pid in ordered_ids[:limit]]


def apply_scope_boost(points: list, scope_field: str, values: list[str], weight: float) -> list:
    """Bonus de score ADDITIF post-fusion (T0.2, PAS un filtre Qdrant) : les points dont
    payload[scope_field] intersecte `values` reçoivent +weight, puis retri décroissant.
    Le tri Python est stable -> à score égal (deux points sans bonus, ou deux points
    boostés à égalité), l'ordre de fusion DBSF/RRF d'origine est conservé.

    Hors-scope JAMAIS exclus (contrainte de conception #1 du plan) : ils restent dans la
    liste, non bonifiés, et peuvent toujours dominer si leur score fusionné d'origine est
    plus haut que in-scope+weight -- c'est le comportement voulu (downside cross-wing
    évité, contrairement à --scope-mode filter)."""
    values_set = set(values)

    def bonus(point) -> float:
        raw = (point.payload or {}).get(scope_field)
        candidates = raw if isinstance(raw, list) else [raw]
        return weight if values_set.intersection(v for v in candidates if v is not None) else 0.0

    scored = [(p.score + bonus(p), p) for p in points]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in scored]


def apply_scope_boost_repo_wing(points: list, repo: str | None, wing: str | None, weight: float) -> list:
    """Port FIDÈLE de mcp_search.py::_apply_scope_boost (T1.1, prod live) : bonus
    additif UNIQUE (+weight, PAS +2*weight) aux points dont payload['repo']==repo
    OU payload['wing']==wing, puis retri stable décroissant. Utilisé par T2.1
    (--scope-field repo_wing) pour que le sweep mesure exactement le mécanisme
    qui sera déployé — un scope_field unique ('repo' seul via apply_scope_boost)
    sous-mesurerait le downside cross-wing (bonus wing plus large qu'un repo)."""
    if not repo and not wing:
        return points

    def in_scope(point) -> bool:
        payload = point.payload or {}
        return (repo is not None and payload.get("repo") == repo) or \
               (wing is not None and payload.get("wing") == wing)

    scored = [(p.score + (weight if in_scope(p) else 0.0), p) for p in points]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in scored]


class LightCrossEncoder:
    """Rerank cross-encoder léger (fastembed TextCrossEncoder, ONNX CPU) — alternative
    à rerank.py (bge-reranker-v2-m3, 568M params, 9.8s médiane/requête sur Pi — cf
    AI-MEMORY-AGENT-PROTOCOL.md §3.6, disqualifié pour R0 interactif).

    Défaut Xenova/ms-marco-MiniLM-L-6-v2 (~23M params, ~90MB ONNX) — anglais MS MARCO,
    PAS multilingue par design. golden.yml est ~35% FR/65% EN (heuristique mots-outils
    FR sur les 76 questions) — à valider empiriquement sur les questions FR avant tout
    usage prod (cf rapport final, sibling test toy FR/EN concluant mais non exhaustif).
    """

    def __init__(self, model_name: str, cache_dir: str) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder  # lazy: import lourd

        self.model = TextCrossEncoder(model_name=model_name, cache_dir=cache_dir)

    def score(self, query: str, documents: list[str]) -> list[float]:
        return list(self.model.rerank(query, documents))


def rerank_light_points(
    encoder: LightCrossEncoder, query: str, points: list, top_n: int,
    max_chars: int | None = None,
):
    """Rerank les top_n premiers `points` (chunks) sur le texte du payload (`text`,
    fallback `title`) — PAS le snippet 160 car. de search_memory.py. `max_chars`
    (optionnel) tronque pour limiter le coût CPU (cf docstring param CLI)."""
    if not points:
        return points, 0.0
    head = points[:top_n]
    tail = points[top_n:]
    documents = [
        (p.payload or {}).get("text") or (p.payload or {}).get("title") or "" for p in head
    ]
    if max_chars:
        documents = [d[:max_chars] for d in documents]
    t0 = time.monotonic()
    scores = encoder.score(query, documents)
    elapsed = time.monotonic() - t0
    order = sorted(range(len(head)), key=lambda i: scores[i], reverse=True)
    reranked_head = [head[i] for i in order]
    return reranked_head + tail, elapsed


def evaluate(points, expected: set[str]) -> dict:
    """Rang (1-based) du premier hit (repo:relative_path ∈ expected), hits dédupliqués.

    Les chunks successifs d'un même fichier comptent pour UN seul rang :
    le rang est compté sur les fichiers distincts rencontrés.
    """
    seen_files: list[str] = []
    first_hit_rank = None
    for point in points:
        payload = point.payload or {}
        key = f"{payload.get('repo')}:{payload.get('relative_path')}"
        if key not in seen_files:
            seen_files.append(key)
        if first_hit_rank is None and key in expected:
            first_hit_rank = seen_files.index(key) + 1
    return {"rank": first_hit_rank, "top_files": seen_files[:MRR_K]}


def aggregate(results: list[dict]) -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0}
    recall_1 = sum(1 for r in results if r["rank"] == 1) / n
    recall_5 = sum(1 for r in results if r["rank"] is not None and r["rank"] <= 5) / n
    mrr_10 = sum(
        1.0 / r["rank"] for r in results if r["rank"] is not None and r["rank"] <= MRR_K
    ) / n
    return {
        "n": n,
        "recall@1": round(recall_1, 4),
        "recall@5": round(recall_5, 4),
        "mrr@10": round(mrr_10, 4),
    }


def print_diff(current: dict, baseline_path: Path) -> None:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    base_metrics = baseline.get("metrics", {})
    cur_metrics = current.get("metrics", {})
    print(f"\n=== Diff vs baseline {baseline_path} "
          f"({baseline.get('collection')}/{baseline.get('mode')}) ===")
    for key in ("recall@1", "recall@5", "mrr@10"):
        old = base_metrics.get(key)
        new = cur_metrics.get(key)
        if old is None or new is None:
            print(f"{key:>10}: n/a")
            continue
        delta = new - old
        arrow = "=" if abs(delta) < 1e-9 else ("UP" if delta > 0 else "DOWN")
        print(f"{key:>10}: {old:.4f} -> {new:.4f}  ({delta:+.4f} {arrow})")
    base_kinds = baseline.get("by_doc_kind", {})
    for kind, metrics in sorted(current.get("by_doc_kind", {}).items()):
        old = base_kinds.get(kind, {}).get("recall@5")
        new = metrics.get("recall@5")
        if old is not None and new is not None:
            print(f"{('recall@5['+kind+']'):>18}: {old:.4f} -> {new:.4f}  ({new-old:+.4f})")


def main() -> int:
    args = parse_args()
    if args.limit < MRR_K:
        print(f"[warn] --limit {args.limit} < {MRR_K} : MRR@10 sera tronqué au top-{args.limit}",
              file=sys.stderr)

    golden = load_yaml(Path(args.golden))
    questions = golden.get("questions", []) or []
    if args.max_questions:
        questions = questions[: args.max_questions]
    if not questions:
        print("golden.yml vide — rien à évaluer", file=sys.stderr)
        return 1

    config = load_yaml(Path(args.config))
    client = make_client(config)
    schema = detect_schema(client, args.collection)

    if args.mode == "hybrid":
        if not schema["named"] or schema["dense_name"] != "dense" or "bm25" not in schema["sparse_names"]:
            print(
                f"mode hybrid impossible sur '{args.collection}' : schéma "
                f"named={schema['named']} dense={schema['dense_name']} "
                f"sparse={schema['sparse_names']} (requis: dense + bm25). "
                "Utiliser --mode dense.",
                file=sys.stderr,
            )
            return 2
        sparse_encoder = SparseEncoder()
    else:
        sparse_encoder = None

    if args.manual_fusion and args.mode != "hybrid":
        print("--manual-fusion requiert --mode hybrid", file=sys.stderr)
        return 2

    if bool(args.scope_file) != bool(args.scope_field):
        print("--scope-file et --scope-field vont ensemble (les deux ou aucun)", file=sys.stderr)
        return 2
    is_repo_wing = args.scope_field == "repo_wing"
    if is_repo_wing:
        scope_map_rw: dict[str, dict] = load_scope_map_repo_wing(args.scope_file) if args.scope_file else {}
        scope_map: dict[str, list[str]] = {}  # non utilisé en repo_wing, garde le type existant intact
    else:
        scope_map = load_scope_map(args.scope_file) if args.scope_file else {}
        scope_map_rw = {}

    rerank_encoder = None
    if args.rerank_light:
        rerank_encoder = LightCrossEncoder(args.rerank_light_model, args.fastembed_cache)

    has_scope = bool(scope_map) or bool(scope_map_rw)
    effective_rrf_k = args.rrf_k if args.rrf_k is not None else DEFAULT_RRF_K
    fetch_limit = max(args.limit, args.rerank_candidates) if args.rerank_light else args.limit
    if has_scope and args.scope_mode == "boost":
        fetch_limit = max(fetch_limit, args.scope_boost_candidates)

    print(f"[eval] collection={args.collection} mode={args.mode} schema="
          f"{'named' if schema['named'] else 'unnamed'} questions={len(questions)} "
          f"limit={args.limit} prefetch_limit={args.prefetch_limit} fusion={args.fusion} "
          f"manual_fusion={args.manual_fusion} rrf_k={effective_rrf_k if (args.manual_fusion or args.rrf_k) else 'server-default'} "
          f"rerank_light={args.rerank_light}"
          + (f" rerank_model={args.rerank_light_model} rerank_candidates={args.rerank_candidates}"
             if args.rerank_light else "")
          + (f" scope_field={args.scope_field} scope_mode={args.scope_mode}"
             + (f" scope_boost_weight={args.scope_boost_weight} "
                f"scope_boost_candidates={args.scope_boost_candidates}"
                if args.scope_mode == "boost" else "")
             if has_scope else ""))

    encoder = DenseEncoder(config)
    t_encode = time.monotonic()
    dense_vectors = encoder.encode_queries([q["query"] for q in questions])
    encode_s = time.monotonic() - t_encode

    results: list[dict] = []
    rerank_timings: list[float] = []
    t_search = time.monotonic()
    for question, dense_vector in zip(questions, dense_vectors):
        sparse_vector = (
            sparse_encoder.encode_query(question["query"]) if sparse_encoder else None
        )
        extra_filter = None
        in_scope = None
        boost_values: list[str] | None = None  # non-None seulement si scope_mode=boost applicable
        boost_repo_wing: tuple[str | None, str | None] | None = None  # idem, variante repo_wing
        if is_repo_wing and scope_map_rw:
            entry = scope_map_rw.get(question["query"])
            repo_val = (entry or {}).get("repo")
            wing_val = (entry or {}).get("wing")
            if not repo_val and not wing_val:
                print(f"  [warn] pas de repo/wing scope pour {question['query'][:60]!r} "
                      "-> question non filtrée", file=sys.stderr)
            else:
                # in_scope = oracle OR (repo OU wing) — même vérité-terrain que le boost.
                in_scope = check_in_scope_repo_wing(client, args.collection, repo_val, wing_val,
                                                     question["expected_paths"])
                if args.scope_mode == "filter":
                    should: list[qmodels.FieldCondition] = []
                    if repo_val:
                        should.append(qmodels.FieldCondition(key="repo", match=qmodels.MatchValue(value=repo_val)))
                    if wing_val:
                        should.append(qmodels.FieldCondition(key="wing", match=qmodels.MatchValue(value=wing_val)))
                    extra_filter = qmodels.Filter(should=should)  # OR dur (borne haute repo_wing)
                else:
                    boost_repo_wing = (repo_val, wing_val)  # scope_mode=boost : bonus OR post-fusion
        elif scope_map:
            values = scope_map.get(question["query"])
            if not values:
                print(f"  [warn] pas de valeurs scope pour {question['query'][:60]!r} "
                      "-> question non filtrée", file=sys.stderr)
            else:
                scope_filter = qmodels.Filter(
                    must=[qmodels.FieldCondition(key=args.scope_field, match=qmodels.MatchAny(any=values))]
                )
                # in_scope = oracle indépendant du mode (check_in_scope ne fait qu'un
                # client.count() sous scope_filter -- même vérité-terrain filter/boost).
                in_scope = check_in_scope(client, args.collection, scope_filter,
                                           question["expected_paths"])
                if args.scope_mode == "filter":
                    extra_filter = scope_filter  # must Qdrant dur (comportement pré-existant)
                else:
                    boost_values = values  # scope_mode=boost : pas de filtre, bonus post-fusion
        if args.manual_fusion:
            dense_points = run_channel_query(
                client, args.collection, "dense", dense_vector, args.prefetch_limit,
                exact=args.exact,
            )
            sparse_points = run_channel_query(
                client, args.collection, "bm25", sparse_vector, args.prefetch_limit,
                exact=args.exact,
            )
            points = manual_rrf_fusion(
                dense_points, sparse_points, effective_rrf_k,
                args.dense_weight, args.sparse_weight, fetch_limit,
            )
        else:
            points = run_query(
                client, args.collection, args.mode, schema, dense_vector, sparse_vector,
                fetch_limit, prefetch_limit=args.prefetch_limit, fusion=args.fusion,
                rrf_k=args.rrf_k, exact=args.exact, extra_filter=extra_filter,
            )

        if args.rerank_light:
            points, rerank_s = rerank_light_points(
                rerank_encoder, question["query"], points, args.rerank_candidates,
                max_chars=args.rerank_max_chars,
            )
            rerank_timings.append(rerank_s)

        if boost_repo_wing is not None:
            points = apply_scope_boost_repo_wing(
                points, boost_repo_wing[0], boost_repo_wing[1], args.scope_boost_weight
            )
        elif boost_values is not None:
            points = apply_scope_boost(points, args.scope_field, boost_values, args.scope_boost_weight)

        expected = set(question["expected_paths"])
        outcome = evaluate(points, expected)
        results.append(
            {
                "query": question["query"],
                "doc_kind": question.get("doc_kind", "doc"),
                "expected_paths": sorted(expected),
                "rank": outcome["rank"],
                "top_files": outcome["top_files"],
                "note": question.get("note", ""),
                "in_scope": in_scope,
            }
        )
        status = f"rank={outcome['rank']}" if outcome["rank"] else "MISS"
        scope_suffix = "" if in_scope is None else (" [OUT-OF-SCOPE]" if not in_scope else "")
        rerank_suffix = f" ({rerank_timings[-1]:.2f}s)" if args.rerank_light else ""
        print(f"  [{status:>8}]{rerank_suffix}{scope_suffix} {question['query'][:80]}")
    search_s = time.monotonic() - t_search

    by_kind: dict[str, list[dict]] = {}
    for result in results:
        by_kind.setdefault(result["doc_kind"], []).append(result)

    rerank_stats = None
    if args.rerank_light and rerank_timings:
        sorted_t = sorted(rerank_timings)
        mid = len(sorted_t) // 2
        median_t = sorted_t[mid] if len(sorted_t) % 2 else (sorted_t[mid - 1] + sorted_t[mid]) / 2
        rerank_stats = {
            "model": args.rerank_light_model,
            "candidates": args.rerank_candidates,
            "median_s": round(median_t, 3),
            "max_s": round(max(sorted_t), 3),
            "min_s": round(min(sorted_t), 3),
        }

    scoped_results = [r for r in results if r["in_scope"] is not None]
    filter_miss_rate = (
        round(sum(1 for r in scoped_results if r["in_scope"] is False) / len(scoped_results), 4)
        if scoped_results else None
    )

    report = {
        "schema_version": "eval-v1",
        "collection": args.collection,
        "mode": args.mode,
        "limit": args.limit,
        "golden": str(Path(args.golden).resolve()),
        "questions": len(results),
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "params": {
            "prefetch_limit": args.prefetch_limit,
            "fusion": args.fusion,
            "manual_fusion": args.manual_fusion,
            "rrf_k": effective_rrf_k if (args.manual_fusion or args.rrf_k is not None) else None,
            "dense_weight": args.dense_weight if args.manual_fusion else None,
            "sparse_weight": args.sparse_weight if args.manual_fusion else None,
            "rerank_light": args.rerank_light,
            "exact": args.exact,
            "scope_field": args.scope_field,
            "scope_file": args.scope_file,
            "scope_mode": args.scope_mode if has_scope else None,
            "scope_boost_weight": args.scope_boost_weight if (has_scope and args.scope_mode == "boost") else None,
            "scope_boost_candidates": (
                args.scope_boost_candidates if (has_scope and args.scope_mode == "boost") else None
            ),
        },
        "filter_miss_rate": filter_miss_rate,
        "rerank_timings": rerank_stats,
        "timings": {"encode_s": round(encode_s, 2), "search_s": round(search_s, 2)},
        "metrics": aggregate(results),
        "by_doc_kind": {kind: aggregate(items) for kind, items in sorted(by_kind.items())},
        "misses": [
            {"query": r["query"], "expected": r["expected_paths"], "top_files": r["top_files"][:5]}
            for r in results
            if r["rank"] is None
        ],
        "details": results,
    }

    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = DEFAULT_OUT_DIR / f"eval-{args.collection}-{args.mode}-{stamp}.json"
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        # Copie déployée sous /opt : parents[2] -> /opt/.planning (non inscriptible).
        # Fail-safe : ne jamais perdre un rapport d'éval déjà calculé.
        fallback = Path.cwd() / out_path.name
        print(f"[warn] écriture {out_path} impossible ({exc}) -> {fallback}", file=sys.stderr)
        out_path = fallback
        out_path.write_text(rendered, encoding="utf-8")

    metrics = report["metrics"]
    print(f"\n=== {args.collection} / {args.mode} — {metrics['n']} questions ===")
    if filter_miss_rate is not None:
        n_miss = sum(1 for r in scoped_results if r["in_scope"] is False)
        print(f"  filter_miss_rate = {filter_miss_rate:.4f} ({n_miss}/{len(scoped_results)} questions "
              f"scope={args.scope_field})")
    print(f"  recall@1 = {metrics['recall@1']:.4f}")
    print(f"  recall@5 = {metrics['recall@5']:.4f}")
    print(f"  mrr@10   = {metrics['mrr@10']:.4f}")
    for kind, kind_metrics in report["by_doc_kind"].items():
        print(f"  [{kind}] n={kind_metrics['n']} r@1={kind_metrics['recall@1']:.4f} "
              f"r@5={kind_metrics['recall@5']:.4f} mrr@10={kind_metrics['mrr@10']:.4f}")
    print(f"  encode={report['timings']['encode_s']}s search={report['timings']['search_s']}s")
    if rerank_stats:
        print(f"  rerank[{rerank_stats['model']}] median={rerank_stats['median_s']}s "
              f"max={rerank_stats['max_s']}s min={rerank_stats['min_s']}s "
              f"(n={len(rerank_timings)}, candidates={rerank_stats['candidates']})")
    print(f"  -> {out_path}")

    if args.baseline:
        print_diff(report, Path(args.baseline))

    if args.assert_thresholds:
        failures = check_thresholds(metrics, args.min_recall1, args.min_mrr10)
        if failures:
            print("\n[GATE FAIL] dérive mémoire détectée :", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            print(f"  rapport complet -> {out_path}", file=sys.stderr)
            return 3
        print(
            f"\n[GATE OK] recall@1={metrics['recall@1']:.4f} (>= {args.min_recall1:.4f})  "
            f"mrr@10={metrics['mrr@10']:.4f} (>= {args.min_mrr10:.4f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
