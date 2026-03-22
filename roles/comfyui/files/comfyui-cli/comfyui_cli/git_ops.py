"""Git integration for workflow versioning.

All git operations are non-blocking — errors are logged but don't fail the CLI command.
"""
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


def _run_git(workflows_dir: str, args: List[str], env_override: Optional[Dict] = None) -> subprocess.CompletedProcess:
    """Run a git command in the workflows directory."""
    cmd = ["git"] + args
    return subprocess.run(
        cmd,
        cwd=workflows_dir,
        capture_output=True,
        text=True,
        timeout=30,
        env=env_override,
    )


def is_git_repo(workflows_dir: str) -> bool:
    """Check if the workflows directory is a git repo."""
    try:
        result = _run_git(workflows_dir, ["rev-parse", "--git-dir"])
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False


def git_commit(config: Dict, message: str, paths: List[str], delete: bool = False) -> bool:
    """Stage and commit changes with CLI attribution.

    Returns True if commit was made, False otherwise.
    Non-blocking: errors are logged but don't raise.
    """
    workflows_dir = config.get("workflows_dir", "")
    if not workflows_dir or not is_git_repo(workflows_dir):
        return False

    author_name = config.get("git_author_name", "Claude CLI")
    author_email = config.get("git_author_email", "claude@localhost")

    try:
        # Stage changes
        if delete:
            _run_git(workflows_dir, ["rm", "--cached", "--ignore-unmatch", "--"] + paths)
        else:
            _run_git(workflows_dir, ["add", "--"] + paths)

        # Check if there's anything to commit
        result = _run_git(workflows_dir, ["diff", "--cached", "--quiet"])
        if result.returncode == 0:
            log.debug("No changes to commit")
            return False

        # Commit with attribution
        result = _run_git(
            workflows_dir,
            [
                "-c", f"user.name={author_name}",
                "-c", f"user.email={author_email}",
                "commit", "-m", message,
            ],
        )

        if result.returncode == 0:
            log.info("Committed: %s", message)
            return True
        else:
            log.warning("Git commit failed: %s", result.stderr)
            return False

    except Exception as e:
        log.warning("Git error: %s", e)
        return False


def git_log(workflows_dir: str, path: Optional[str] = None, limit: int = 10) -> List[Dict]:
    """Get git log entries, optionally filtered to a specific file."""
    args = [
        "log", f"--max-count={limit}",
        "--format=%H%x00%an%x00%ae%x00%at%x00%s",
    ]
    if path:
        args += ["--", path]

    result = _run_git(workflows_dir, args)
    if result.returncode != 0:
        return []

    entries = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\x00", 4)
        if len(parts) == 5:
            entries.append({
                "commit": parts[0],
                "author_name": parts[1],
                "author_email": parts[2],
                "timestamp": int(parts[3]),
                "message": parts[4],
            })
    return entries


def git_diff(workflows_dir: str, path: Optional[str] = None, commit: Optional[str] = None) -> str:
    """Show diff for a file, optionally against a specific commit."""
    args = ["diff"]
    if commit:
        args.append(commit)
    args.append("--")
    if path:
        args.append(path)

    result = _run_git(workflows_dir, args)
    return result.stdout if result.returncode == 0 else ""


def git_show(workflows_dir: str, commit: str, path: str) -> str:
    """Show file content at a specific commit."""
    result = _run_git(workflows_dir, ["show", f"{commit}:{path}"])
    return result.stdout if result.returncode == 0 else ""


def git_revert_file(config: Dict, path: str, commit: str) -> bool:
    """Restore a file to a specific commit version."""
    workflows_dir = config.get("workflows_dir", "")
    if not workflows_dir or not is_git_repo(workflows_dir):
        return False

    try:
        # Get file content at that commit
        content = git_show(workflows_dir, commit, path)
        if not content:
            return False

        # Write file
        full_path = Path(workflows_dir) / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

        # Commit the revert
        return git_commit(config, f"cli: revert {path} to {commit[:8]}", [path])

    except Exception as e:
        log.warning("Revert failed: %s", e)
        return False
