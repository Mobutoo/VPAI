"""Rend pre-backup.sh.j2 / backup-cleanup.sh.j2 avec des vars fixture et vérifie
que les jobs brick.yml y apparaissent et que le bash produit est syntaxiquement
valide (bash -n). Ne teste PAS la résolution Jinja imbriquée d'Ansible
({{ trek_data_dir }} dans les vars) : les src sont pré-résolus dans la fixture —
la résolution paresseuse est un comportement plateforme d'Ansible, prouvé au
déploiement (Task 7)."""
import subprocess
from pathlib import Path

import jinja2

REPO = Path(__file__).resolve().parents[2]

VARS = {
    "ansible_managed": "test",
    "project_display_name": "Test",
    "project_name": "testproj",
    "postgresql_password": "x",
    "redis_password": "x",
    "qdrant_api_key": "x",
    "grafana_admin_password": "x",
    "backup_base_dir": "/opt/testproj/backups",
    "backup_local_retention_days": 3,
    "backup_pre_script_cron_hour": "2",
    "backup_pre_script_cron_minute": "55",
    "backup_heartbeat_url": "",
    "postgresql_databases": [{"name": "n8n"}],
    "openclaw_volume_isolation": False,
    "brick_backup_pg_databases": ["umami"],
    "brick_backup_tar_jobs": [
        {"brick": "trek", "archive": "data", "src": "/opt/testproj/data/trek", "include": ["."]},
        {"brick": "trek", "archive": "uploads", "src": "/opt/testproj/data/trek-uploads", "include": ["."]},
        # src volontairement hostile : prouve que le filtre quote neutralise la
        # valeur RESOLUE (espace + $()), pas seulement la référence du manifeste.
        {"brick": "demo", "archive": "spaced", "src": "/opt/test proj/$(reboot)", "include": ["."]},
    ],
}


def _env() -> jinja2.Environment:
    import shlex

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(REPO / "roles/backup-config/templates"),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )
    env.filters["quote"] = shlex.quote  # équivalent du filtre Ansible `quote`
    return env


def render(template_name: str) -> str:
    return _env().get_template(template_name).render(**VARS)


def assert_bash_valid(script: str, tmp_path: Path, name: str):
    path = tmp_path / name
    path.write_text(script)
    subprocess.run(["bash", "-n", str(path)], check=True)


def test_prebackup_renders_brick_jobs(tmp_path):
    out = render("pre-backup.sh.j2")
    assert "trek/data-${TIMESTAMP}.tar.gz" in out
    assert "trek/uploads-${TIMESTAMP}.tar.gz" in out
    assert "-C /opt/testproj/data/trek ." in out  # chemin sain : quote no-op
    assert "-C '/opt/test proj/$(reboot)' ." in out  # chemin hostile : neutralisé
    assert "BRICK_TAR_FAILURES=$((BRICK_TAR_FAILURES + 1))" in out
    assert 'if [ "${BRICK_TAR_FAILURES}" -gt 0 ]' in out
    assert_bash_valid(out, tmp_path, "pre-backup.sh")


def test_prebackup_pg_includes_brick_databases(tmp_path):
    out = render("pre-backup.sh.j2")
    for_line = next(line for line in out.splitlines() if line.startswith("for DB in "))
    assert "umami" in for_line
    assert "prisme" in for_line  # la liste en dur historique reste
    covered_line = next(line for line in out.splitlines() if line.startswith("COVERED="))
    assert "umami" in covered_line  # la garde de dérive couvre aussi les bases brick


def test_prebackup_no_hardcoded_trek_block():
    out = render("pre-backup.sh.j2")
    assert "TREK data backup" not in out


def test_prebackup_without_brick_vars_still_renders(tmp_path):
    bare = {k: v for k, v in VARS.items() if not k.startswith("brick_backup_")}
    out = _env().get_template("pre-backup.sh.j2").render(**bare)
    assert_bash_valid(out, tmp_path, "pre-backup-bare.sh")


def test_cleanup_covers_brick_dirs(tmp_path):
    out = render("backup-cleanup.sh.j2")
    cleanup_line = next(line for line in out.splitlines() if line.startswith("for SUBDIR_PATH in "))
    assert 'find "${BACKUP_DIR}"' in cleanup_line
    assert "-maxdepth 1" in cleanup_line
    assert_bash_valid(out, tmp_path, "backup-cleanup.sh")
