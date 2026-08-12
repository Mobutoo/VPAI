# Managed by roles/litellm (Ansible ansible.builtin.copy, static file — NOT a
# Jinja template, plain python, deployed verbatim to /app/guard_extra_body.py).
"""LiteLLM proxy custom callback — enforce server provider pin, ignore client extra_body.

Contexte (gate technique Optimus B4, 2026-08-12, finding CRITIQUE (c)) :
un client du proxy peut ECRASER le pin fournisseur/ZDR configure cote serveur
(litellm_params.extra_body.provider dans litellm_config.yaml.j2) en passant
son propre "extra_body": {"provider": {...}} dans le corps de requete.
Le vecteur top-level "provider": {...} est neutralise par drop_params:true
(non-openai/non supporte au top-level -> drop). Le vecteur extra_body.provider
NE L'EST PAS : "non-openai param" -> passe tel quel (comportement documente de
drop_params : il ne filtre QUE les params OpenAI standards non supportes,
jamais les kwargs provider-specific comme extra_body).

Aucun reglage LiteLLM natif (allowed_openai_params, drop_params,
additional_drop_params) ne permet de bloquer un sous-champ arbitraire d'un
dict extra_body cote proxy — verifie docs.litellm.ai (completion/input,
completion/drop_params) le 2026-08-12. Seul mecanisme natif exploitable : un
callback custom CustomLogger.async_pre_call_hook, invoque par
ProxyLogging.pre_call_hook() (litellm/proxy/utils.py) AVANT tout merge de
litellm_params par le Router.

INCIDENT POST-DEPLOI (2026-08-13, corrige ici) : la 1ere version de ce
callback se contentait de SUPPRIMER data["extra_body"]["provider"] (laissant
"extra_body": {} present comme cle). Preuve empirique en prod : appel glm-52
AVEC extra_body.provider client -> fournisseur atteste "CoreWeave" (NI
l'override attaquant 'openai', NI le pin serveur 'digitalocean') ; appel
glm-52 NOMINAL (sans extra_body du tout) -> "DigitalOcean" (pin correct).

Cause racine confirmee dans le code du wheel PINNE litellm==1.83.3,
`router.py::Router._acompletion()` (~L2140-2148) :
    input_kwargs = {
        **litellm_params,   # SERVEUR (deployment litellm_params, config.yaml)
        "messages": messages,
        "caching": self.cache_responses,
        "client": model_client,
        **kwargs,            # CLIENT (request data) -- spread EN DERNIER, GAGNE
    }
Ce merge est un merge SHALLOW au niveau des cles de PREMIER NIVEAU de
`input_kwargs`, PAS un deep-merge sur le contenu d'"extra_body". Des que le
client envoie une cle "extra_body" -- MEME VIDE {} -- elle ecrase
INTEGRALEMENT `litellm_params["extra_body"]` (le pin serveur complet, pas
seulement la sous-cle "provider") avant meme que la logique de merge plus
fine documentee dans `litellm/utils.py::get_optional_params()` (~L4372,
`{**optional_params["extra_body"], **extra_body}`) n'ait la moindre chance
de s'executer -- ce merge plus fin ne voit jamais qu'UNE seule source
"extra_body" a ce stade, celle qui a survecu au merge Router ci-dessus.
Supprimer la sous-cle "provider" du cote client sans neutraliser la
PRESENCE de la cle "extra_body" elle-meme laisse donc le pin serveur
entierement efface des qu'un client envoie N'IMPORTE QUEL extra_body
(avec ou sans tentative d'override "provider" explicite) -> routage libre
cote OpenRouter (CoreWeave dans l'incident constate, ou tout autre
fournisseur non pinne).

Note historique (verifiee, PAS une coincidence) : l'attestation Google
observee juste apres le tout premier deploy (avant meme ce fix) portait
sur un appel claude-opus SANS aucune cle "extra_body" dans le corps client
-- le merge Router `{**litellm_params, **kwargs}` ne voit alors aucune cle
"extra_body" cote kwargs, donc `litellm_params["extra_body"]` (serveur)
survit intact. Le mecanisme "absence de cle = pin protege" est correct
mais FRAGILE (un client qui envoie un extra_body vide pour toute autre
raison legitime romprait quand meme le pin) -- d'ou la correction
ci-dessous qui n'en depend plus.

FIX : au lieu de supprimer la sous-cle "provider" cote client, ce callback
la REECRIT avec les valeurs SERVEUR exactes du modele appele, lues depuis
`litellm.proxy.proxy_server.llm_router` (le Router global du proxy,
peuple au chargement de la config, bien avant que des requetes ne soient
servies -- meme pattern que `litellm/proxy/hooks/batch_rate_limiter.py`
qui importe `llm_router` en lazy import dans le corps du hook).
`Router.get_model_list(model_name=...)` retourne les deployments
correspondant a l'alias appele avec leur `litellm_params` intact (verifie
empiriquement avec `litellm==1.83.3` reellement installe : le dict
`extra_body.provider` survit tel quel a l'enregistrement du Router).
Quel que soit le contenu de la cle "extra_body" envoyee par le client
(sous-cle "provider" absente, presente avec un override, ou "extra_body"
vide/avec d'autres sous-cles legitimes comme "transforms"), DES QUE cette
cle "extra_body" est PRESENTE dans la requete client, le dict Python
`data["extra_body"]` mute par ce callback contient, apres son passage, une
sous-cle "provider" egale a la config serveur -- donc quel que soit celui
des deux dicts ("litellm_params" serveur ou "kwargs" client) qui gagne au
merge Router shallow ci-dessus, le resultat effectif est IDENTIQUE au pin
serveur. Ceci ferme le trou de la 1ere version pour :
(a) une tentative d'override explicite ("provider" present cote client) ;
(b) un extra_body client SANS "provider" du tout (le trou de l'incident
    2026-08-13).

**Le cas nominal (AUCUNE cle "extra_body" du tout cote client) N'EST PAS
enforce -- delibere, corrige apres revue.** Injecter le pin
inconditionnellement (y compris quand le client n'a rien envoye) a ete
essaye puis ABANDONNE : `data` (le dict post pre_call_hook) est le MEME
objet kwargs reutilise tel quel par
`Router.async_function_with_fallbacks_common_utils()` pour les tentatives
de fallback (`input_kwargs = {..., **kwargs}`, verifie dans le wheel
pinne) -- SEULE la cle "model" change entre l'appel primaire et les
fallbacks, "extra_body" survit. Si le guard avait force
`data["extra_body"]["provider"] = {"order": ["google-vertex"], ...}` pour
un appel nominal `claude-opus` (pin google-vertex, `allow_fallbacks:
false`), et que ce modele echoue et bascule sur son fallback
`claude-sonnet` (SANS pin configure, litellm_params SANS extra_body) via
`fallbacks: [claude-opus: [claude-sonnet, gpt-codex]]` de
litellm_config.yaml.j2, le pin google-vertex + allow_fallbacks:false de
claude-opus aurait ete applique tel quel a l'appel claude-sonnet -- un
fournisseur qui ne sert probablement pas ce modele, avec interdiction
explicite de fallback -> echec dur du filet de secours lui-meme. Preserver
le comportement "absence de cle = pin protege" (verifie fonctionner,
c'est l'observation historique claude-opus -> Google) pour le cas nominal
evite ce risque : quand le client n'envoie aucun "extra_body", `kwargs`
n'a pas cette cle, le merge Router `{**litellm_params, **kwargs}` laisse
`litellm_params["extra_body"]` (celui du DEPLOYMENT REELLEMENT APPELE,
primaire ou fallback) intact a chaque tentative -- correct par
construction, y compris a travers un fallback.

Residu assume (a documenter au plan §5) : si le client envoie une cle
"extra_body" ET que l'appel tombe en fallback, le pin injecte pour le
modele PRIMAIRE rides toujours avec `kwargs` dans la tentative de
fallback (meme mecanisme que ci-dessus, non resolu pour ce sous-cas -- seul
`claude-opus` est concerne parmi les alias pinnes, c'est le seul present
dans la map `fallbacks:`). Seule la sous-cle "provider" est reecrite : si
un modele pinne avait un jour d'autres sous-cles `extra_body` server-side
en plus de "provider" (aucun cas actuel dans litellm_config.yaml.j2), un
client envoyant son propre `extra_body` sans ces autres sous-cles les
effacerait quand meme au meme merge Router -- hors perimetre de ce
finding (uniquement "provider" est demontre exploite).
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

logger = logging.getLogger("litellm.guard_extra_body")


def _get_server_provider_pin(model_name: Any) -> dict[str, Any] | None:
    """Look up the server-configured extra_body.provider pin for a model_name.

    Returns a deep copy of the pin dict if exactly ONE deployment is
    registered under `model_name` in the live Router AND that deployment
    defines `litellm_params.extra_body.provider` as a dict. Returns None
    otherwise (unpinned model, router unavailable/not yet initialized,
    ambiguous multi-deployment model_name — none of the pinned aliases in
    litellm_config.yaml.j2 currently have more than one deployment; if that
    ever changes, this function intentionally refuses to guess and the
    caller falls back to stripping instead of rewriting).

    Import of the live Router is deferred (function-local) — this keeps the
    module importable/testable without litellm installed (offline proof),
    and matches the pattern used by other LiteLLM proxy hooks (e.g.
    litellm/proxy/hooks/batch_rate_limiter.py) that read the module-level
    `llm_router` global set by proxy_server at config-load time.
    """
    if not isinstance(model_name, str) or not model_name:
        return None

    try:
        from litellm.proxy.proxy_server import llm_router  # noqa: PLC0415
    except ImportError:  # pragma: no cover — offline/standalone test environment
        return None

    if llm_router is None:
        return None

    try:
        deployments = llm_router.get_model_list(model_name=model_name)
    except Exception:  # noqa: BLE001 — never let a lookup failure break the request
        logger.exception(
            "guard_extra_body: get_model_list failed for model=%s — falling back to strip",
            model_name,
        )
        return None

    if not deployments or len(deployments) != 1:
        return None

    litellm_params = deployments[0].get("litellm_params") or {}
    extra_body = litellm_params.get("extra_body")
    if not isinstance(extra_body, dict):
        return None

    provider_pin = extra_body.get("provider")
    if not isinstance(provider_pin, dict):
        return None

    return copy.deepcopy(provider_pin)


def _enforce_provider_pin(data: dict[str, Any]) -> dict[str, Any]:
    """Force data["extra_body"]["provider"] to the server-configured pin.

    Pure-ish function (litellm Router lookup is isolated in
    `_get_server_provider_pin`, itself import-guarded) — testable standalone
    with a fake pin-lookup callable, without the litellm package installed.

    Mutates and returns `data`. Behaviour per case:
    - top-level "provider" (belt-and-braces vs drop_params) : always removed.
    - NO "extra_body" key at all in `data` : early return, untouched. Do
      NOT fabricate one — see module docstring "fallback poisoning" for why
      (this same `data`/kwargs dict is reused verbatim, only "model"
      changed, by Router.async_function_with_fallbacks_common_utils() for
      fallback attempts — injecting a pin unconditionally would ride along
      into a fallback deployment that has no such pin, or a different one,
      with allow_fallbacks:false attached, turning the filet de secours
      into a hard failure). The Router-level merge already protects this
      case: no client "extra_body" key -> server litellm_params.extra_body
      is never contested at `{**litellm_params, **kwargs}`.
    - "extra_body" key present (any content, including {} or a value
      without "provider"), as a dict OR as a JSON string (observed
      elsewhere in the LiteLLM proxy request path for multipart/extra_body
      payloads — proxy_server.py chat_completion() guards the same shape
      for "metadata") : model has a server pin (single deployment,
      litellm_params.extra_body.provider is a dict) -> data["extra_body"]
      ["provider"] is REWRITTEN to the server pin, unconditionally. This is
      what closes the top-level Router merge clobber (see module
      docstring) : whichever of {server litellm_params, client kwargs}
      wins that shallow merge, the "extra_body" value is now identical
      either way. Model has NO server pin (unpinned alias, or router/
      deployment lookup unavailable) : client-supplied "provider" is
      simply DELETED (deny by default — no safe value to reconstitute).
    """
    if "provider" in data:
        del data["provider"]

    if "extra_body" not in data:
        return data

    extra_body = data.get("extra_body")
    if isinstance(extra_body, str):
        try:
            extra_body = json.loads(extra_body)
        except (TypeError, ValueError):
            extra_body = None
        else:
            data["extra_body"] = extra_body

    server_pin = _get_server_provider_pin(data.get("model"))

    if server_pin is not None:
        if not isinstance(extra_body, dict):
            extra_body = {}
            data["extra_body"] = extra_body
        client_had_explicit_provider = "provider" in extra_body
        extra_body["provider"] = server_pin
        if client_had_explicit_provider:
            logger.warning(
                "guard_extra_body: OVERRIDE ATTEMPT — client-supplied "
                "extra_body.provider replaced with server pin for model=%s "
                "litellm_call_id=%s",
                data.get("model"),
                data.get("litellm_call_id"),
            )
        else:
            logger.warning(
                "guard_extra_body: client sent extra_body without a provider "
                "key — filled in server pin for model=%s litellm_call_id=%s "
                "(closes the 2026-08-13 clobber vector, not an override attempt)",
                data.get("model"),
                data.get("litellm_call_id"),
            )
    elif isinstance(extra_body, dict) and "provider" in extra_body:
        del extra_body["provider"]
        logger.warning(
            "guard_extra_body: stripped client-supplied extra_body.provider for "
            "unpinned/unresolved model=%s litellm_call_id=%s (no server pin to enforce)",
            data.get("model"),
            data.get("litellm_call_id"),
        )

    return data


# Import of litellm's CustomLogger is best-effort at module load so that
# `_enforce_provider_pin` above stays importable/testable in isolation
# (`python3 -c "import guard_extra_body; ..."`) without the litellm package
# present — that is the offline proof used pre-deploy. When litellm IS
# present (inside the proxy container, the only place this module is
# actually loaded by LiteLLM's get_instance_fn), _CustomLoggerBase is the
# real CustomLogger and ExtraBodyProviderGuard becomes a proper subclass
# whose async_pre_call_hook override is detected by
# ProxyLogging.pre_call_hook() (litellm/proxy/utils.py — checks
# `"async_pre_call_hook" in vars(_callback.__class__)`).
try:
    from litellm.integrations.custom_logger import CustomLogger as _CustomLoggerBase
except ImportError:  # pragma: no cover — offline/standalone test environment
    _CustomLoggerBase = object  # type: ignore[assignment,misc]


class ExtraBodyProviderGuard(_CustomLoggerBase):  # type: ignore[misc,valid-type]
    """CustomLogger subclass wired via litellm_settings.callbacks in config.yaml."""

    async def async_pre_call_hook(  # type: ignore[override]
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict[str, Any],
        call_type: str,
    ) -> dict[str, Any] | None:
        return _enforce_provider_pin(data)


# LiteLLM resolves "guard_extra_body.proxy_handler_instance" (see
# litellm_settings.callbacks in litellm_config.yaml.j2) to this instance.
proxy_handler_instance = ExtraBodyProviderGuard()
