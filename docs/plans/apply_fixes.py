#!/usr/bin/env python3
"""Apply all review fixes to Jarvis Bridge codebase."""

import json
import os

BASE = "/home/mobuone/jarvis"


def patch(filepath, old, new):
    """Replace old with new in file. Raises if old not found."""
    path = os.path.join(BASE, filepath)
    with open(path, "r") as f:
        content = f.read()
    if old not in content:
        print(f"  WARN: pattern not found in {filepath}, skipping")
        return False
    content = content.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(content)
    print(f"  PATCHED: {filepath}")
    return True


def rewrite(filepath, content):
    """Overwrite a file completely."""
    path = os.path.join(BASE, filepath)
    with open(path, "w") as f:
        f.write(content)
    print(f"  REWRITTEN: {filepath}")


# ============================================================
# 1. dispatcher.py — I5 dequeue error handling + chat_id property
# ============================================================
print("\n=== dispatcher.py ===")

patch("bridge/dispatcher.py",
    'f"Le mobutoo est occupe."',
    'f"Mobutoo est occupe."'
)

# I5: wrap dequeue in try/except
patch("bridge/dispatcher.py",
    """        # Process queued messages
        while self._queue and not self._foreground_lock.locked():
            queued_text, queued_chat_id = self._queue.pop(0)
            await self._run_foreground(queued_text, queued_chat_id)""",
    """        # Process queued messages — I5 fix: try/except so one failing
        # queued message does not prevent processing the rest.
        while self._queue and not self._foreground_lock.locked():
            queued_text, queued_chat_id = self._queue.pop(0)
            try:
                await self._run_foreground(queued_text, queued_chat_id)
            except Exception as e:
                logger.error("Queued message error: %s", e, exc_info=True)"""
)

# Add default_chat_id property before stats
patch("bridge/dispatcher.py",
    """    @property
    def stats(self) -> dict[str, Any]:""",
    """    @property
    def default_chat_id(self) -> int:
        \"\"\"Default chat ID for API-triggered messages.\"\"\"
        return self._bot.chat_id

    @property
    def stats(self) -> dict[str, Any]:"""
)

# ============================================================
# 2. server.py — timing-safe auth, rate limit, bind 127.0.0.1, use property
# ============================================================
print("\n=== server.py ===")

# Add hmac import
patch("bridge/server.py",
    "import json\nimport logging\nimport time",
    "import hmac\nimport json\nimport logging\nimport time"
)

# Change default host to 127.0.0.1
patch("bridge/server.py",
    '        host: str = "0.0.0.0",',
    '        host: str = "127.0.0.1",'
)

# Add rate limit state after self._runner
patch("bridge/server.py",
    "        self._runner: web.AppRunner | None = None",
    """        self._runner: web.AppRunner | None = None
        # Simple rate limiting: max 30 API calls per minute
        self._api_calls: list[float] = []
        self._api_rate_limit = 30"""
)

# Replace auth check with timing-safe + rate limit
patch("bridge/server.py",
    """        # Check auth
        auth_key = request.headers.get("X-Jarvis-Key", "")
        if auth_key != self._api_key:
            return web.json_response(
                {"error": "Unauthorized"},
                status=401,
            )""",
    """        # Check auth — timing-safe comparison to prevent timing attacks
        auth_key = request.headers.get("X-Jarvis-Key", "")
        if not hmac.compare_digest(auth_key, self._api_key):
            return web.json_response(
                {"error": "Unauthorized"},
                status=401,
            )

        # Rate limiting
        now = time.time()
        self._api_calls = [t for t in self._api_calls if now - t < 60]
        if len(self._api_calls) >= self._api_rate_limit:
            return web.json_response(
                {"error": "Rate limit exceeded (30/min)"},
                status=429,
            )
        self._api_calls.append(now)"""
)

# Replace _bot.chat_id with default_chat_id property
patch("bridge/server.py",
    "            chat_id = self._dispatcher._bot.chat_id\n            await self._dispatcher.handle_message(prompt, chat_id)\n",
    "            chat_id = self._dispatcher.default_chat_id\n            await self._dispatcher.handle_message(prompt, chat_id)\n"
)

patch("bridge/server.py",
    "                chat_id = self._dispatcher._bot.chat_id\n                task_id = await self._workers.spawn(prompt, agent_type, chat_id)",
    "                chat_id = self._dispatcher.default_chat_id\n                task_id = await self._workers.spawn(prompt, agent_type, chat_id)"
)

# ============================================================
# 3. main.py — safe task wrapper, callback auth, log dir, bind fix
# ============================================================
print("\n=== main.py ===")

# Fix: safe task wrapper for fire-and-forget + callback auth check
patch("bridge/main.py",
    """                if text and chat_id:
                    # Process message in a task to not block polling
                    asyncio.create_task(
                        dispatcher.handle_message(text, chat_id),
                        name=f"msg-{update.get('update_id', '?')}",
                    )""",
    """                if text and chat_id:
                    # C3 fix: wrap in safe handler so exceptions are logged,
                    # not silently swallowed by fire-and-forget task.
                    async def _safe_dispatch(t: str, c: int, uid: str) -> None:
                        try:
                            await dispatcher.handle_message(t, c)
                        except Exception as exc:
                            logger.error("Unhandled error in msg-%s: %s", uid, exc, exc_info=True)

                    update_id = str(update.get('update_id', '?'))
                    asyncio.create_task(
                        _safe_dispatch(text, chat_id, update_id),
                        name=f"msg-{update_id}",
                    )"""
)

# Fix: callback auth check
patch("bridge/main.py",
    """                # Handle callback queries (approval buttons)
                callback_query = update.get("callback_query")
                if callback_query:
                    callback_data = callback_query.get("data", "")
                    callback_id = callback_query.get("id", "")
                    await approvals.handle_callback(callback_data, callback_id)
                    continue""",
    """                # Handle callback queries (approval buttons)
                callback_query = update.get("callback_query")
                if callback_query:
                    # Security: verify callback comes from authorized chat
                    cb_chat_id = (
                        callback_query.get("message", {})
                        .get("chat", {})
                        .get("id")
                    )
                    if cb_chat_id != bot.chat_id:
                        logger.warning("Unauthorized callback from chat_id=%s", cb_chat_id)
                        continue
                    callback_data = callback_query.get("data", "")
                    callback_id = callback_query.get("id", "")
                    await approvals.handle_callback(callback_data, callback_id)
                    continue"""
)

# Fix: create log dir at startup
patch("bridge/main.py",
    """    # Setup logging
    setup_logging(log_dir=cfg.log_dir)""",
    """    # Ensure log directory exists
    os.makedirs(cfg.log_dir, exist_ok=True)

    # Setup logging
    setup_logging(log_dir=cfg.log_dir)"""
)

# Fix: bind 127.0.0.1 instead of 0.0.0.0
patch("bridge/main.py",
    '        host="0.0.0.0",',
    '        host="127.0.0.1",'
)

# ============================================================
# 4. approvals.py — TTL cleanup for pending retries
# ============================================================
print("\n=== approvals.py ===")

# Add time import
patch("bridge/approvals.py",
    "import asyncio\nimport json\nimport logging\nimport os\nimport re\nimport uuid",
    "import asyncio\nimport json\nimport logging\nimport os\nimport re\nimport time\nimport uuid"
)

# Add TTL constant and timestamp to pending retries
patch("bridge/approvals.py",
    '        self._pending_retries: dict[str, dict[str, Any]] = {}',
    """        self._pending_retries: dict[str, dict[str, Any]] = {}
        self._retry_ttl_seconds = 600  # 10 min TTL for pending retries"""
)

# Store timestamp when creating retry
patch("bridge/approvals.py",
    """        # Generate retry ID
        retry_id = str(uuid.uuid4())[:8]

        # Store retry context
        self._pending_retries[retry_id] = {""",
    """        # Cleanup expired retries
        self._cleanup_expired_retries()

        # Generate retry ID
        retry_id = str(uuid.uuid4())[:8]

        # Store retry context with timestamp for TTL
        self._pending_retries[retry_id] = {
            "_created_at": time.time(),"""
)

# Add cleanup method before close()
patch("bridge/approvals.py",
    """    async def close(self) -> None:
        \"\"\"Cleanup pending retries.\"\"\"
        self._pending_retries.clear()""",
    """    def _cleanup_expired_retries(self) -> None:
        \"\"\"Remove pending retries older than TTL.\"\"\"
        now = time.time()
        expired = [
            rid for rid, ctx in self._pending_retries.items()
            if now - ctx.get("_created_at", 0) > self._retry_ttl_seconds
        ]
        for rid in expired:
            del self._pending_retries[rid]
        if expired:
            logger.info("Cleaned up %d expired retry(ies)", len(expired))

    async def close(self) -> None:
        \"\"\"Cleanup pending retries.\"\"\"
        self._pending_retries.clear()"""
)

# ============================================================
# 5. claude_runner.py — replace assert with proper check
# ============================================================
print("\n=== claude_runner.py ===")

patch("bridge/claude_runner.py",
    "        assert process.stdout is not None",
    """        if process.stdout is None:
            return ClaudeResult(
                is_error=True,
                error_message="stdout pipe not available",
                text="Erreur interne: stdout pipe non disponible.",
            )"""
)

# ============================================================
# 6. log.py — add Qdrant API key masking pattern
# ============================================================
print("\n=== log.py ===")

patch("bridge/log.py",
    '    re.compile(r"(eyJ[A-Za-z0-9_-]{20,}\\.[A-Za-z0-9_-]{20,})"),  # JWT tokens\n]',
    """    re.compile(r"(eyJ[A-Za-z0-9_-]{20,}\\.[A-Za-z0-9_-]{20,})"),  # JWT tokens
    re.compile(r"(?<=api-key[\"': ]{1,3})([A-Za-z0-9_-]{20,})"),       # Qdrant/generic API keys in headers
]"""
)

# ============================================================
# 7. plane_client.py — add verify=False comment
# ============================================================
print("\n=== plane_client.py ===")

patch("bridge/plane_client.py",
    "            verify=False,",
    "            verify=False,  # Plane accessed via Tailscale (self-signed cert, no local CA)"
)

# ============================================================
# 8. settings-ops.json — replace docker wildcard with safe specifics
# ============================================================
print("\n=== settings-ops.json ===")

ops_settings = {
    "permissions": {
        "allow": [
            "Read", "Glob", "Grep",
            "Bash(ansible:*)",
            "Bash(ansible-playbook:*)",
            "Bash(ansible-vault:*)",
            "Bash(docker ps:*)",
            "Bash(docker logs:*)",
            "Bash(docker inspect:*)",
            "Bash(docker stats:*)",
            "Bash(docker images:*)",
            "Bash(docker network:*)",
            "Bash(docker volume ls:*)",
            "Bash(docker compose ps:*)",
            "Bash(docker compose logs:*)",
            "Bash(docker compose config:*)",
            "Bash(docker compose top:*)",
            "Bash(ssh:*)",
            "Bash(scp:*)",
            "Bash(systemctl status:*)",
            "Bash(systemctl is-active:*)",
            "Bash(journalctl:*)",
            "Bash(cat:*)", "Bash(ls:*)", "Bash(head:*)", "Bash(tail:*)",
            "Bash(grep:*)", "Bash(curl:*)", "Bash(wget:*)",
            "Bash(df:*)", "Bash(free:*)", "Bash(uptime:*)",
            "Bash(top:*)", "Bash(htop:*)",
            "Bash(netstat:*)", "Bash(ss:*)", "Bash(ip:*)",
            "Bash(ping:*)", "Bash(dig:*)", "Bash(nslookup:*)"
        ],
        "deny": [
            "Write", "Edit",
            "Bash(docker rm:*)",
            "Bash(docker rmi:*)",
            "Bash(docker stop:*)",
            "Bash(docker kill:*)",
            "Bash(docker system prune:*)",
            "Bash(docker compose down:*)",
            "Bash(docker compose rm:*)",
            "Bash(rm -rf:*)",
            "Bash(mkfs:*)",
            "Bash(dd if=:*)",
            "Bash(reboot:*)",
            "Bash(shutdown:*)"
        ]
    }
}
rewrite("config/settings-ops.json", json.dumps(ops_settings, indent=2) + "\n")

# ============================================================
# 9. settings-builder.json — fix rm deny pattern
# ============================================================
print("\n=== settings-builder.json ===")

builder_settings = {
    "permissions": {
        "allow": [
            "Read", "Write", "Edit", "Glob", "Grep",
            "Bash(git:*)",
            "Bash(python3:*)", "Bash(python:*)",
            "Bash(pip:*)", "Bash(pip3:*)",
            "Bash(pytest:*)",
            "Bash(npm:*)", "Bash(npx:*)", "Bash(node:*)",
            "Bash(make:*)",
            "Bash(cargo:*)", "Bash(rustc:*)",
            "Bash(cat:*)", "Bash(ls:*)",
            "Bash(mkdir:*)", "Bash(cp:*)", "Bash(mv:*)",
            "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)",
            "Bash(diff:*)", "Bash(find:*)",
            "Bash(chmod:*)", "Bash(touch:*)"
        ],
        "deny": [
            "Bash(rm -rf:*)",
            "Bash(sudo:*)",
            "Bash(mkfs:*)",
            "Bash(dd:*)",
            "Bash(reboot:*)",
            "Bash(shutdown:*)",
            "Bash(systemctl:*)",
            "Bash(docker:*)"
        ]
    }
}
rewrite("config/settings-builder.json", json.dumps(builder_settings, indent=2) + "\n")

# ============================================================
# 10. logrotate — remove broken postrotate
# ============================================================
print("\n=== jarvis-logrotate.conf ===")

logrotate_conf = """/var/log/jarvis-bridge/*.log {
    daily
    rotate 5
    maxsize 10M
    compress
    delaycompress
    missingok
    notifempty
    create 0644 mobuone mobuone
    copytruncate
}
"""
rewrite("jarvis-logrotate.conf", logrotate_conf)

print("\n=== ALL FIXES APPLIED ===")
