# Managed by roles/litellm (Ansible ansible.builtin.copy, static file — NOT a
# Jinja template, plain python, deployed verbatim to /app/guard_extra_body.py).
"""LiteLLM proxy custom callback — strip client-supplied provider pin overrides.

Contexte (gate technique Optimus B4, 2026-08-12, finding CRITIQUE (c)) :
un client du proxy peut ECRASER le pin fournisseur/ZDR configure cote serveur
(litellm_params.extra_body.provider dans litellm_config.yaml.j2) en passant
son propre "extra_body": {"provider": {...}} dans le corps de requete — LiteLLM
fait un merge SHALLOW ("**server, **client") au niveau de la cle "extra_body"
complete au niveau utils.py::get_optional_params, donc le dict "provider" du
client remplace integralement celui du serveur (pas de deep-merge).
Le vecteur top-level "provider": {...} est deja neutralise par drop_params:true
(non-openai/non supporte au top-level -> drop). Le vecteur extra_body.provider
NE L'EST PAS : "non-openai param" -> passe tel quel (comportement documente de
drop_params : il ne filtre QUE les params OpenAI standards non supportes,
jamais les kwargs provider-specific comme extra_body).

Aucun reglage LiteLLM natif (allowed_openai_params, drop_params,
additional_drop_params) ne permet de bloquer un sous-champ arbitraire d'un
dict extra_body cote proxy — verifie docs.litellm.ai (completion/input,
completion/drop_params) le 2026-08-12. allowed_openai_params est en outre
lui-meme surchargeable par le client via extra_body (elargit la surface, ne
la reduit pas). Seul mecanisme natif exploitable : un callback custom
CustomLogger.async_pre_call_hook, invoque par
ProxyLogging.pre_call_hook() (litellm/proxy/utils.py) AVANT tout merge de
litellm_params par le Router — verifie sur le wheel litellm==1.83.3 (version
pinnee production, cf. inventory/group_vars/all/versions.yml) :
  - proxy/common_request_processing.py: `self.data = await
    proxy_logging_obj.pre_call_hook(...)` s'execute dans
    common_processing_pre_call_logic(), avant la selection de deployment /
    le merge des litellm_params serveur.
  - proxy/utils.py ProxyLogging.pre_call_hook(): boucle `for callback in
    litellm.callbacks` et invoque async_pre_call_hook si surchargee sur la
    classe -- exactement notre cas.
  - proxy/types_utils/utils.py get_instance_fn(): resout un identifiant
    "module.instance" du config.yaml relatif a
    os.path.dirname(config_file_path) -- donc CE fichier doit vivre dans le
    MEME repertoire que /app/config.yaml dans le conteneur (mount explicite,
    voir roles/docker-stack/templates/compose/apps-core.yml.j2).

Ce module retire donc, sur CHAQUE requete entrante (peu importe le
call_type — completion, embeddings, anthropic_messages/v1/messages, etc.),
toute cle "provider" fournie par le client dans le corps top-level ET dans
extra_body, AVANT que ces donnees n'atteignent le merge Router. Le pin
serveur (litellm_params.extra_body.provider du config.yaml) est réinjecté
plus tard par LiteLLM lui-meme et n'est jamais touche par ce callback -- on
ne supprime QUE ce que le client a fourni.

Defense en profondeur : le top-level "provider" reste neutralise par
drop_params, mais on le retire aussi ici explicitement plutot que de
dependre d'un mecanisme qu'on ne controle pas dans le temps (bump de
version, config drift) — cf. revue.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("litellm.guard_extra_body")

_FORBIDDEN_KEYS = ("provider",)


def _strip_forbidden_provider(data: dict[str, Any]) -> dict[str, Any]:
    """Remove client-supplied provider pin overrides from a request payload.

    Pure function, no LiteLLM import required — testable standalone
    (`python3 -c "import guard_extra_body; ..."`) without the litellm
    package installed, so this logic can be proven offline before deploy.

    Mutates and returns `data`. Safe against:
    - top-level "provider" (belt-and-braces vs drop_params)
    - "extra_body" arriving as a dict (normal case)
    - "extra_body" arriving as a JSON string (observed elsewhere in the
      LiteLLM proxy request path for multipart/extra_body payloads —
      proxy_server.py chat_completion() guards the same shape for
      "metadata")
    - "extra_body" missing or not a dict/str (no-op)
    """
    stripped: list[str] = []

    for key in _FORBIDDEN_KEYS:
        if key in data:
            del data[key]
            stripped.append(f"top-level.{key}")

    extra_body = data.get("extra_body")
    if isinstance(extra_body, str):
        try:
            extra_body = json.loads(extra_body)
        except (TypeError, ValueError):
            extra_body = None
        else:
            data["extra_body"] = extra_body

    if isinstance(extra_body, dict):
        for key in _FORBIDDEN_KEYS:
            if key in extra_body:
                del extra_body[key]
                stripped.append(f"extra_body.{key}")

    if stripped:
        logger.warning(
            "guard_extra_body: stripped client-supplied provider override(s) %s "
            "(model=%s, litellm_call_id=%s) — pin serveur preserve",
            stripped,
            data.get("model"),
            data.get("litellm_call_id"),
        )

    return data


# Import of litellm's CustomLogger is best-effort at module load so that
# `_strip_forbidden_provider` above stays importable/testable in isolation
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
        return _strip_forbidden_provider(data)


# LiteLLM resolves "guard_extra_body.proxy_handler_instance" (see
# litellm_settings.callbacks in litellm_config.yaml.j2) to this instance.
proxy_handler_instance = ExtraBodyProviderGuard()
