"""Tests for git operations."""
import json
import subprocess
import tempfile
import pytest
from pathlib import Path
from comfyui_cli.git_ops import is_git_repo, git_commit, git_log


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@test", "commit", "--allow-empty", "-m", "init"],
        cwd=tmp_path, capture_output=True,
    )
    return tmp_path


@pytest.fixture
def git_config(git_repo):
    """Config pointing at the temp git repo."""
    return {
        "workflows_dir": str(git_repo),
        "git_enabled": True,
        "git_author_name": "Test CLI",
        "git_author_email": "test@localhost",
    }


def test_is_git_repo(git_repo):
    assert is_git_repo(str(git_repo)) is True
    # Use a truly isolated tempdir (not inside git_repo) to avoid git traversal
    with tempfile.TemporaryDirectory() as non_git:
        assert is_git_repo(non_git) is False
    # After cleanup the directory no longer exists — should return False gracefully
    assert is_git_repo(non_git) is False


def test_git_commit(git_config, git_repo):
    # Create a file to commit
    (git_repo / "test.json").write_text('{"test": true}')
    result = git_commit(git_config, "cli: test commit", ["test.json"])
    assert result is True


def test_git_commit_no_changes(git_config, git_repo):
    result = git_commit(git_config, "cli: no changes", [])
    assert result is False


def test_git_log(git_config, git_repo):
    (git_repo / "wf.json").write_text('{"nodes": []}')
    git_commit(git_config, "cli: add wf", ["wf.json"])
    entries = git_log(str(git_repo), limit=5)
    assert len(entries) >= 1
    assert entries[0]["author_name"] == "Test CLI"
    assert "cli: add wf" in entries[0]["message"]
