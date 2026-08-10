from pathlib import Path

import yaml

from scripts.brick_generate import REPO, cmd_lint, load_manifest, validate_manifest

FIXTURES = Path(__file__).parent / "fixtures"


def valid():
    return yaml.safe_load((FIXTURES / "umami-valid.yml").read_text(encoding="utf-8"))


def errors_of(manifest, versions=None):
    return validate_manifest(manifest, Path("roles/umami/brick.yml"), versions or {})


def test_valid_manifest_passes():
    assert errors_of(valid()) == []


def test_load_manifest_reads_fixture():
    m = load_manifest(FIXTURES / "umami-valid.yml")
    assert m["identity"]["name"] == "umami"


def test_digest_malformed_fails():
    m = valid()
    m["identity"]["digest"] = "sha256:tooshort"
    assert any("digest" in e for e in errors_of(m))


def test_digest_absent_fails():
    m = valid()
    del m["identity"]["digest"]
    assert any("digest" in e for e in errors_of(m))


def test_backup_strategy_key_absent_fails():
    m = valid()
    del m["backup"]["strategy"]
    assert any("strategy" in e for e in errors_of(m))


def test_missing_memory_limit_fails():
    m = valid()
    del m["runtime"]["resources"]["memory_limit"]
    assert any("memory_limit" in e for e in errors_of(m))


def test_missing_healthcheck_fails():
    m = valid()
    del m["runtime"]["healthcheck"]
    assert any("healthcheck" in e for e in errors_of(m))


def test_compose_enum_enforced():
    m = valid()
    m["deployment"]["compose"] = "manual"
    assert any("compose" in e for e in errors_of(m))


def test_compose_absent_fails():
    m = valid()
    del m["deployment"]["compose"]
    assert any("compose" in e for e in errors_of(m))


def test_latest_tag_fails():
    m = valid()
    m["identity"]["image"] = "ghcr.io/umami-software/umami:latest"
    assert any("image" in e for e in errors_of(m))


def test_unknown_top_level_key_fails():
    m = valid()
    m["extra_field"] = {"foo": 1}
    assert errors_of(m) != []


def test_dotdot_in_backup_src_fails():
    m = valid()
    m["backup"]["strategy"] = [
        {"kind": "volume_tar", "archive": "evil", "src": "/opt/app/../../etc"}
    ]
    assert errors_of(m) != []


def test_numeric_env_key_does_not_crash_sort():
    # Un simple ajout de clé numérique (m["runtime"]["env"][1] = "x") ne
    # produit aucune erreur schéma (la clé n'est pas contrainte, seule la
    # valeur l'est via `additionalProperties`), donc `sorted()` ne compare
    # jamais de chemins hétérogènes dans ce cas précis. Pour reproduire le
    # TypeError réel (comparaison str/int dans `list(e.absolute_path)`), il
    # faut au moins deux erreurs dont les chemins partagent un préfixe mais
    # divergent en type au même index : clé numérique invalide + clé string
    # invalide dans runtime.env.
    m = valid()
    m["runtime"]["env"][1] = None
    m["runtime"]["env"]["BAD"] = None
    errors = errors_of(m)
    assert errors != []
    assert any("runtime.env.1" in e for e in errors) and any("runtime.env.BAD" in e for e in errors)


def test_digest_trailing_newline_fails():
    m = valid()
    m["identity"]["digest"] = (
        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
    )
    assert any("digest" in e for e in errors_of(m))


def test_backup_database_trailing_newline_fails():
    m = valid()
    m["backup"]["strategy"] = [{"kind": "postgres_dump", "database": "umami\n"}]
    assert any("database" in e for e in errors_of(m))


def test_empty_strategy_without_reason_fails():
    m = valid()
    m["backup"]["strategy"] = []
    assert any("disabled_reason" in e for e in errors_of(m))


def test_empty_strategy_with_reason_passes():
    m = valid()
    m["backup"]["strategy"] = []
    m["backup"]["disabled_reason"] = "stateless, état 100% en base déjà dumpée par la brique postgresql"
    assert errors_of(m) == []


def test_alerts_missing_restart_loop_fails():
    m = valid()
    m["monitoring"]["alerts"] = [{"kind": "service_down"}]
    assert any("restart_loop" in e for e in errors_of(m))


def test_alerts_missing_entirely_fails():
    m = valid()
    del m["monitoring"]["alerts"]
    assert any("service_down" in e and "restart_loop" in e for e in errors_of(m))


def test_http_5xx_without_vhost_fails():
    m = valid()
    del m["exposure"]
    assert any("http_5xx_rate" in e for e in errors_of(m))


def test_http_5xx_with_mode_none_fails():
    m = valid()
    m["exposure"]["vhost"]["mode"] = "none"
    assert any("http_5xx_rate" in e for e in errors_of(m))


def test_public_without_dns_proof_fails():
    m = valid()
    m["exposure"]["vhost"]["mode"] = "public"
    assert any("dns_proof" in e for e in errors_of(m))


def test_public_with_dns_proof_passes():
    m = valid()
    m["exposure"]["vhost"]["mode"] = "public"
    m["exposure"]["vhost"]["dns_proof"] = {
        "record_type": "A",
        "value": "203.0.113.10",
        "validated_at": "2026-08-05",
        "validated_by": "test",
    }
    assert errors_of(m) == []


def test_versions_yml_image_mismatch_fails():
    m = valid()
    versions = {"umami_image": "ghcr.io/umami-software/umami:postgresql-v2.19.0"}
    assert any("versions.yml" in e for e in errors_of(m, versions))


def test_versions_yml_image_match_passes():
    m = valid()
    versions = {"umami_image": "ghcr.io/umami-software/umami:postgresql-v2.20.0"}
    assert errors_of(m, versions) == []


def test_versions_yml_no_entry_is_ok():
    assert errors_of(valid(), {"other_image": "x:1"}) == []


def test_env_secret_key_as_literal_fails():
    m = valid()
    m["runtime"]["env"]["ADMIN_PASSWORD"] = "hunter2"
    assert any("vault_ref" in e for e in errors_of(m))


def test_env_secret_key_as_vault_ref_passes():
    m = valid()
    m["runtime"]["env"]["ADMIN_PASSWORD"] = {"vault_ref": "vault_umami_admin_password"}
    assert errors_of(m) == []


def test_env_secret_key_pw_as_literal_fails():
    m = valid()
    m["runtime"]["env"]["DB_PW"] = "x"
    assert any("vault_ref" in e for e in errors_of(m))


def test_non_string_name_does_not_crash():
    m = valid()
    m["identity"]["name"] = 123
    errors = errors_of(m)
    assert isinstance(errors, list)


def test_environments_unknown_value_fails():
    m = valid()
    m["deployment"]["environments"] = ["seze"]
    assert any("environments" in e for e in errors_of(m))


def test_threshold_on_service_down_fails():
    m = valid()
    m["monitoring"]["alerts"][0]["threshold"] = "10"
    assert errors_of(m) != []


def test_window_on_restart_loop_fails():
    m = valid()
    idx = next(i for i, a in enumerate(m["monitoring"]["alerts"]) if a["kind"] == "restart_loop")
    m["monitoring"]["alerts"][idx]["window"] = "30m"
    assert errors_of(m) != []


def test_window_below_minimum_fails():
    m = valid()
    idx = next(i for i, a in enumerate(m["monitoring"]["alerts"]) if a["kind"] == "http_5xx_rate")
    m["monitoring"]["alerts"][idx]["window"] = "0m"
    assert any("bornes raisonnables" in e for e in errors_of(m))


def test_window_above_maximum_fails():
    m = valid()
    idx = next(i for i, a in enumerate(m["monitoring"]["alerts"]) if a["kind"] == "http_5xx_rate")
    m["monitoring"]["alerts"][idx]["window"] = "999999d"
    assert any("bornes raisonnables" in e for e in errors_of(m))


def test_window_within_bounds_passes():
    m = valid()
    idx = next(i for i, a in enumerate(m["monitoring"]["alerts"]) if a["kind"] == "http_5xx_rate")
    m["monitoring"]["alerts"][idx]["window"] = "7d"
    assert errors_of(m) == []


def test_environments_absent_fails():
    m = valid()
    del m["deployment"]["environments"]
    assert any("environments" in e for e in errors_of(m))


def test_environments_empty_fails():
    m = valid()
    m["deployment"]["environments"] = []
    assert any("environments" in e for e in errors_of(m))


def test_image_without_tag_fails():
    m = valid()
    m["identity"]["image"] = "mauriceboe/trek"
    assert any("image" in e for e in errors_of(m))


def test_image_with_tag_passes():
    m = valid()
    m["identity"]["image"] = "mauriceboe/trek:3.0.22"
    assert errors_of(m) == []


def test_image_ghcr_with_tag_passes():
    m = valid()
    m["identity"]["image"] = "ghcr.io/umami-software/umami:postgresql-v2.20.0"
    assert errors_of(m) == []


def test_cmd_lint_deployment_as_string_does_not_crash(tmp_path):
    role_dir = tmp_path / "roles" / "x"
    role_dir.mkdir(parents=True)
    (role_dir / "brick.yml").write_text(
        "identity:\n  name: x\ndeployment: generated\n", encoding="utf-8"
    )
    # deployment n'est pas un mapping -> pas d'environments -> orphelin -> bloquant.
    assert cmd_lint(tmp_path) == 1


def test_cmd_lint_no_orphans_returns_zero():
    assert cmd_lint(REPO) == 0


def test_cmd_lint_flags_orphan_alert_artifact(tmp_path):
    """Un fichier alerting-bricks-<env>.yaml pour un env qu'aucun manifeste ne
    déclare est un artefact mort (rien ne le câble dans les rôles) — cmd_lint
    doit le détecter, pas seulement les manifestes sans environnement
    (finding TV HIGH couverture)."""
    role_dir = tmp_path / "roles" / "x"
    role_dir.mkdir(parents=True)
    (role_dir / "brick.yml").write_text(
        "identity:\n  name: x\ndeployment:\n  environments: [\"sese\"]\n", encoding="utf-8"
    )
    alerts_dir = tmp_path / "roles" / "monitoring" / "templates" / "grafana" / "provisioning" / "bricks"
    alerts_dir.mkdir(parents=True)
    (alerts_dir / "alerting-bricks-preprod.yaml").write_text("apiVersion: 1\ngroups: []\n", encoding="utf-8")
    assert cmd_lint(tmp_path) == 1


def test_list_envs_generator_backup_includes_artifact_only_env(tmp_path):
    """Un env d'inventaire réel (bricks_backup_<env>.yml déjà présent, ex.
    scaffold preprod vide) doit rester dans la boucle de dérive même si aucun
    manifeste ne le déclare encore — sinon son contenu échappe à toute garde
    (finding TV HIGH couverture, Makefile lint-bricks)."""
    from scripts.brick_generate import cmd_list_envs

    role_dir = tmp_path / "roles" / "x"
    role_dir.mkdir(parents=True)
    (role_dir / "brick.yml").write_text(
        "identity:\n  name: x\ndeployment:\n  environments: [\"sese\"]\n", encoding="utf-8"
    )
    backup_dir = tmp_path / "roles" / "backup-config" / "vars"
    backup_dir.mkdir(parents=True)
    (backup_dir / "bricks_backup_preprod.yml").write_text(
        "brick_backup_pg_databases: []\nbrick_backup_tar_jobs: []\n", encoding="utf-8"
    )
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        assert cmd_list_envs(tmp_path, "backup") == 0
    envs = buf.getvalue().split()
    assert set(envs) == {"sese", "preprod"}
