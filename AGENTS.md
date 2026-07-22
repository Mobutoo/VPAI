# AGENTS.md — VPAI (Codex CLI)

Portage partiel de la LOI OPÉRATIONNELLE de ce repo (référence complète : `CLAUDE.md`,
section "LOI OPÉRATIONNELLE"). Seule la règle R0 est portée ici pour l'instant — le
reste (R1-R11, hooks, autres serveurs MCP) suit plus tard, ne le suppose pas actif.

## R0 — MEMORY FIRST (obligatoire, non négociable)

Avant toute modification de code ou toute action sur un sujet déjà documenté dans ce
projet (n8n, Caddy, LiteLLM, Kitsu, Ansible, webhook, Qdrant, etc.) :

1. Appelle l'outil de recherche du serveur MCP `qdrant` avec une requête en langage
   naturel décrivant le sujet, AVANT d'écrire ou modifier du code.
2. Cite le chemin de fichier source retourné par la recherche dans ta réponse.
3. Ne dis jamais "je pense que..." sur un sujet du projet sans l'avoir vérifié par
   cette recherche d'abord.
4. Si la recherche ne retourne rien de pertinent (ou un score trop faible), dis-le
   explicitement — n'invente jamais une réponse à sa place.
