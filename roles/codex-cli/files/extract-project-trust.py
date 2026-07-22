#!/usr/bin/env python3
"""Extract the [projects.*] table from an existing Codex CLI config.toml.

Codex CLI writes `[projects."<path>"]` blocks (e.g. trust_level = "trusted")
into ~/.codex/config.toml at runtime, interactively, when the user approves
a project directory. These blocks are NOT modeled in the Ansible template
that renders config.toml, so a naive redeploy would silently erase them.
This script is called by Ansible BEFORE the template task to snapshot the
existing "projects" table as JSON, so the template can re-inject it.

Usage: extract-project-trust.py <path-to-config.toml>

Output contract (stdout): a single JSON object (dict of dicts), one line.
- If the file does not exist: prints "{}" and exits 0.
- If the file exists and parses: prints json.dumps(data.get("projects", {})).
- If parsing fails for any reason (corrupt file, permissions, etc.): prints
  "{}" on stdout, a warning on stderr, and STILL exits 0.

Resilience note: this script must NEVER cause the Ansible deploy to fail.
Losing the project trust blocks once (falling back to "{}") is an
acceptable degradation; blocking the whole config.toml deployment because
of a parsing hiccup in this best-effort preservation mechanism is not.
"""
import json
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("{}", file=sys.stderr)
        print("{}")
        return 0

    config_path = sys.argv[1]

    try:
        with open(config_path, "rb") as fh:
            import tomllib

            data = tomllib.load(fh)
        projects = data.get("projects", {})
        print(json.dumps(projects))
    except FileNotFoundError:
        print("{}")
    except Exception as exc:  # noqa: BLE001 - intentionally broad, see module docstring
        print(f"extract-project-trust.py: warning: failed to parse {config_path}: {exc}", file=sys.stderr)
        print("{}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
