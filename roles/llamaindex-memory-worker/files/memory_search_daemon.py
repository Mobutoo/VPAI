#!/usr/bin/env python3
"""Démon de recherche mémoire résident — une seule copie du modèle pour toutes les sessions.

SOURCE OF TRUTH : repo VPAI roles/llamaindex-memory-worker/files/memory_search_daemon.py
(le déploiement du rôle recopie ce fichier vers /opt/workstation/ai-memory-worker/).

POURQUOI
--------
`mcp_search.py` est un serveur MCP stdio : Claude Code en démarre UNE INSTANCE PAR
SESSION, et chacune charge google/embeddinggemma-300m en fp32 -> **1,1 Go RSS par
session ouverte** (mesuré sur waza le 2026-07-31). Trois sessions = 3,3 Go au repos
sur une machine de 15 Go, ce qui a contribué au reclaim mémoire de l'incident de
charge du 28-31/07 (cf docs/design + memoire projet). Aucun horaire de worker ne
corrige ça : le coût est porté par les sessions, pas par l'indexation.

Ce démon garde UNE copie du modèle et sert les recherches sur une socket UNIX ;
`mcp_search.py` devient un client mince (~50 Mo). Le gain est net dès 2 sessions,
et l'empreinte devient CONSTANTE au lieu de croître linéairement.

CONTRAT
-------
- Le démon n'implémente AUCUNE logique de recherche : il importe `mcp_search` et
  appelle son `_do_search()`. Zéro duplication -> le comportement de recherche est
  garanti byte-identique au chemin historique (fusion DBSF, floor, boost de scope,
  rerank...). Toute évolution du contrat de recherche se fait dans mcp_search.py.
- Protocole : JSON par ligne sur la socket. Requête `{"op":"search","args":{...}}`,
  réponse `{"ok":true,"text":"..."}` ou `{"ok":false,"error":"..."}`.
  `{"op":"ping"}` -> `{"ok":true,"loaded":bool,"idle_sec":int}` (sonde, ne charge rien).
- Le client DOIT retomber sur un chargement en propre si la socket est absente ou
  muette : démon arrêté = dégradation de performance, jamais perte de fonction.
- Chargement PARESSEUX : rien n'est chargé au démarrage du démon, seulement à la
  première recherche. Déchargement après MEMORY_SEARCH_IDLE_UNLOAD_SEC sans requête
  (défaut 2 h) -> la RAM est rendue la nuit, notamment AVANT le run du worker à
  02:00 qui a besoin de 3 Go.
- Les recherches sont sérialisées par un verrou : SentenceTransformer.encode n'est
  pas garanti thread-safe, et une requête dure ~1-3 s.
"""
from __future__ import annotations

import gc
import json
import os
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcp_search  # noqa: E402  — importé, pas exécuté : main() seul déclenche le chargement

SOCKET_PATH = Path(
    os.environ.get(
        "MEMORY_SEARCH_SOCKET",
        "/opt/workstation/data/ai-memory-worker/run/memory-search.sock",
    )
)
IDLE_UNLOAD_SEC = int(os.environ.get("MEMORY_SEARCH_IDLE_UNLOAD_SEC", "7200"))
IDLE_CHECK_SEC = 60

_search_lock = threading.Lock()
_last_used = time.monotonic()
_state_lock = threading.Lock()


def _log(msg: str) -> None:
    print(f"[memory-search-daemon] {msg}", file=sys.stderr, flush=True)


def _is_loaded() -> bool:
    return mcp_search._model is not None


def _ensure_loaded() -> None:
    """Charge le modèle via mcp_search._load() si besoin. Appelé sous _search_lock."""
    if _is_loaded():
        return
    _log("chargement du modèle (première recherche ou reprise après déchargement)")
    t0 = time.monotonic()
    mcp_search._ready.clear()
    mcp_search._load()
    if _is_loaded():
        _log(f"modèle chargé en {time.monotonic() - t0:.1f}s")
    else:
        _log("ÉCHEC du chargement du modèle — les clients retomberont en propre")


def _unload() -> None:
    """Rend la RAM en SORTANT du processus ; systemd (Restart=always) en relance un neuf.

    MESURÉ le 2026-07-31 : annuler les références (`_model = None` + gc.collect())
    ne fait retomber le RSS que de 1486 Mo à 1065 Mo — torch/numpy conservent leurs
    arènes et ne les rendent pas à l'OS. Un déchargement « logique » aurait donc
    laissé 1 Go résident en permanence, ce qui vide de son sens l'inactivité :
    l'objectif est précisément de rendre la RAM avant le run du worker à 02:00.
    Sortir remet le processus à ~14 Mo, sans état à reconstruire (le modèle est
    rechargé paresseusement à la première requête suivante).

    La socket disparaît le temps du redémarrage (~5 s, RestartSec) : les clients
    retombent alors sur un chargement en propre — dégradation de perf, jamais
    perte de fonction. Le chemin « socket résiduelle » est celui déjà validé au
    test kill -9 : le nouveau processus ne trouve personne à l'écoute, délie et
    rebinde.
    """
    if not _is_loaded():
        return
    _log(f"inactif depuis {IDLE_UNLOAD_SEC}s — sortie pour rendre la RAM "
         "(systemd relance un processus neuf)")
    SOCKET_PATH.unlink(missing_ok=True)
    sys.stderr.flush()
    gc.collect()
    os._exit(0)


def _idle_watcher() -> None:
    while True:
        time.sleep(IDLE_CHECK_SEC)
        if IDLE_UNLOAD_SEC <= 0:
            continue
        with _state_lock:
            idle = time.monotonic() - _last_used
        if idle < IDLE_UNLOAD_SEC:
            continue
        # Ne jamais décharger pendant une recherche : le verrou est pris par le
        # thread qui sert la requête, on repasse au tour suivant.
        if _search_lock.acquire(blocking=False):
            try:
                _unload()
            finally:
                _search_lock.release()


def _handle_request(req: dict) -> dict:
    global _last_used
    op = req.get("op", "search")
    if op == "ping":
        with _state_lock:
            idle = int(time.monotonic() - _last_used)
        return {"ok": True, "loaded": _is_loaded(), "idle_sec": idle}
    if op != "search":
        return {"ok": False, "error": f"unknown op: {op}"}
    args = req.get("args") or {}
    if not args.get("query"):
        return {"ok": False, "error": "missing query"}
    with _search_lock:
        _ensure_loaded()
        if not _is_loaded():
            # Pas de dégradation silencieuse : le client doit pouvoir retomber
            # sur son propre chargement plutôt que de rendre un "not found" faux.
            return {"ok": False, "error": "model unavailable in daemon"}
        with _state_lock:
            _last_used = time.monotonic()
        try:
            # _do_search_local, PAS _do_search : ce dernier interroge la socket
            # et se rappellerait lui-même en boucle.
            text = mcp_search._do_search_local(args)
        except Exception as exc:  # noqa: BLE001 — jamais fatal pour le démon
            return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}
        with _state_lock:
            _last_used = time.monotonic()
    return {"ok": True, "text": text}


class _Handler(socketserver.StreamRequestHandler):
    timeout = 300

    def handle(self) -> None:
        for raw in self.rfile:
            raw = raw.strip()
            if not raw:
                continue
            try:
                req = json.loads(raw)
            except json.JSONDecodeError:
                resp = {"ok": False, "error": "invalid json"}
            else:
                resp = _handle_request(req)
            try:
                self.wfile.write((json.dumps(resp, ensure_ascii=True) + "\n").encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return


class _Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Socket résiduelle d'un démon tué sans nettoyage : bind échouerait sinon.
    # On ne supprime QUE si plus personne n'écoute (sinon on couperait un démon vivant).
    if SOCKET_PATH.exists():
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.settimeout(2)
            probe.connect(str(SOCKET_PATH))
            _log(f"un démon écoute déjà sur {SOCKET_PATH} — sortie")
            return 1
        except OSError:
            SOCKET_PATH.unlink(missing_ok=True)
        finally:
            probe.close()

    server = _Server(str(SOCKET_PATH), _Handler)
    os.chmod(SOCKET_PATH, 0o600)
    threading.Thread(target=_idle_watcher, daemon=True).start()
    _log(
        f"à l'écoute sur {SOCKET_PATH} — chargement paresseux, "
        f"déchargement après {IDLE_UNLOAD_SEC}s d'inactivité"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        SOCKET_PATH.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
