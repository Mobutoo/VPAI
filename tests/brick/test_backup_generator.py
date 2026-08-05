from pathlib import Path

import yaml

from tests.brick.test_validate import valid  # réutilise la fixture chargée

# Même préambule importlib que test_validate.py si scripts/ n'est pas un package :
from scripts.brick_generate import GENERATED_HEADER, generate_backup_vars


def manifests_fixture():
    umami = valid()  # postgres_dump umami, env sese
    trek = valid()
    trek["identity"]["name"] = "trek"
    trek["backup"]["strategy"] = [
        {"kind": "volume_tar", "archive": "uploads", "src": "{{ trek_uploads_dir }}"},
        {"kind": "volume_tar", "archive": "data", "src": "{{ trek_data_dir }}"},
    ]
    hetzner_only = valid()
    hetzner_only["identity"]["name"] = "zitadel"
    hetzner_only["deployment"]["environments"] = ["hetzner-hello-awa"]
    return [
        (Path("roles/umami/brick.yml"), umami),
        (Path("roles/trek/brick.yml"), trek),
        (Path("roles/zitadel/brick.yml"), hetzner_only),
    ]


def test_selects_only_env_bricks():
    out = yaml.safe_load(generate_backup_vars(manifests_fixture(), "sese"))
    bricks = {j["brick"] for j in out["brick_backup_tar_jobs"]}
    assert bricks == {"trek"}
    assert out["brick_backup_pg_databases"] == ["umami"]


def test_tar_jobs_sorted_and_default_include():
    out = yaml.safe_load(generate_backup_vars(manifests_fixture(), "sese"))
    jobs = out["brick_backup_tar_jobs"]
    assert [j["archive"] for j in jobs] == ["data", "uploads"]
    assert all(j["include"] == ["."] for j in jobs)


def test_deterministic():
    a = generate_backup_vars(manifests_fixture(), "sese")
    b = generate_backup_vars(manifests_fixture(), "sese")
    assert a == b


def test_header_present():
    text = generate_backup_vars(manifests_fixture(), "sese")
    assert GENERATED_HEADER.strip() in text
    assert "--env sese" in text


def test_empty_env_produces_empty_lists():
    out = yaml.safe_load(generate_backup_vars(manifests_fixture(), "nulle-part"))
    assert out == {"brick_backup_pg_databases": [], "brick_backup_tar_jobs": []}


def test_duplicate_brick_archive_pair_rejected():
    import pytest

    from scripts.brick_generate import BrickError

    fixtures = manifests_fixture()
    trek = fixtures[1][1]
    trek["backup"]["strategy"].append(
        {"kind": "volume_tar", "archive": "data", "src": "/autre/chemin"}
    )
    with pytest.raises(BrickError, match="trek.*data"):
        generate_backup_vars(fixtures, "sese")


def test_backup_vars_path_is_per_env():
    from scripts.brick_generate import backup_vars_path

    assert backup_vars_path("sese") == "roles/backup-config/vars/bricks_backup_sese.yml"


def test_cli_rejects_unsafe_env(tmp_path):
    from scripts.brick_generate import main

    assert main(["--generate", "backup", "--env", "../../etc", "--repo", str(tmp_path)]) == 1
