from pathlib import Path

import pytest
import yaml

from scripts.brick_generate import (
    BrickError,
    GENERATED_HEADER,
    _promql_syntax_errors,
    alerts_yaml_path,
    declared_environments,
    generate_alerts_yaml,
)
from tests.brick.test_validate import valid  # réutilise la fixture chargée


def manifests_fixture():
    umami = valid()  # sese, vpn_only, service_down + restart_loop + http_5xx_rate
    trek = valid()
    trek["identity"]["name"] = "trek"
    trek["exposure"]["vhost"]["mode"] = "none"
    del trek["monitoring"]["alerts"][-1]  # pas de http_5xx_rate : pas d'exposition HTTP
    hetzner_only = valid()
    hetzner_only["identity"]["name"] = "zitadel"
    hetzner_only["deployment"]["environments"] = ["hetzner-hello-awa"]
    return [
        (Path("roles/umami/brick.yml"), umami),
        (Path("roles/trek/brick.yml"), trek),
        (Path("roles/zitadel/brick.yml"), hetzner_only),
    ]


def test_selects_only_env_bricks():
    out = yaml.safe_load(generate_alerts_yaml(manifests_fixture(), "sese"))
    bricks = {rule["labels"]["brick"] for rule in out["groups"][0]["rules"]}
    assert bricks == {"umami", "trek"}


def test_minimum_two_kinds_always_present():
    out = yaml.safe_load(generate_alerts_yaml(manifests_fixture(), "sese"))
    trek_kinds = {
        rule["uid"].removeprefix("brick-trek-")
        for rule in out["groups"][0]["rules"]
        if rule["labels"]["brick"] == "trek"
    }
    assert trek_kinds == {"service_down", "restart_loop"}


def test_http_5xx_rate_only_with_exposure():
    out = yaml.safe_load(generate_alerts_yaml(manifests_fixture(), "sese"))
    umami_kinds = {
        rule["uid"].removeprefix("brick-umami-")
        for rule in out["groups"][0]["rules"]
        if rule["labels"]["brick"] == "umami"
    }
    assert "http_5xx_rate" in umami_kinds
    trek_kinds = {
        rule["uid"].removeprefix("brick-trek-")
        for rule in out["groups"][0]["rules"]
        if rule["labels"]["brick"] == "trek"
    }
    assert "http_5xx_rate" not in trek_kinds


def test_deterministic():
    a = generate_alerts_yaml(manifests_fixture(), "sese")
    b = generate_alerts_yaml(manifests_fixture(), "sese")
    assert a == b


def test_rules_sorted_by_brick_then_kind():
    from scripts.brick_generate import ALERT_KIND_ORDER

    out = yaml.safe_load(generate_alerts_yaml(manifests_fixture(), "sese"))
    pairs = [
        (rule["labels"]["brick"], rule["uid"].split("-", 2)[2]) for rule in out["groups"][0]["rules"]
    ]
    expected = sorted(pairs, key=lambda p: (p[0], ALERT_KIND_ORDER.index(p[1])))
    assert pairs == expected


def test_header_present():
    text = generate_alerts_yaml(manifests_fixture(), "sese")
    assert GENERATED_HEADER.strip() in text
    assert "--generate alerts --env sese" in text


def test_empty_env_produces_empty_groups():
    out = yaml.safe_load(generate_alerts_yaml(manifests_fixture(), "nulle-part"))
    assert out == {"apiVersion": 1, "groups": []}


def test_valid_apiversion_and_rule_shape():
    out = yaml.safe_load(generate_alerts_yaml(manifests_fixture(), "sese"))
    assert out["apiVersion"] == 1
    for rule in out["groups"][0]["rules"]:
        refids = {d["refId"] for d in rule["data"]}
        assert rule["condition"] in refids
        assert {"uid", "title", "condition", "data", "for", "noDataState"} <= rule.keys()


def test_alerts_yaml_path_is_per_env():
    assert alerts_yaml_path("sese") == (
        "roles/monitoring/templates/grafana/provisioning/bricks/alerting-bricks-sese.yaml"
    )


def test_cli_rejects_unsafe_env(tmp_path):
    from scripts.brick_generate import main

    assert main(["--generate", "alerts", "--env", "../../etc", "--repo", str(tmp_path)]) == 1


def test_unknown_alert_kind_rejected():
    fixtures = manifests_fixture()
    umami = fixtures[0][1]
    umami["monitoring"]["alerts"] = [{"kind": "made_up"}]
    with pytest.raises(BrickError, match="made_up"):
        generate_alerts_yaml(fixtures, "sese")


# --- vérification syntaxique PromQL (structurelle, cf. docstring du générateur) ---


def test_promql_syntax_accepts_generated_exprs():
    text = generate_alerts_yaml(manifests_fixture(), "sese")
    out = yaml.safe_load(text)
    for rule in out["groups"][0]["rules"]:
        expr = rule["data"][0]["model"]["expr"]
        assert _promql_syntax_errors(expr) == []


def test_promql_syntax_rejects_unbalanced_parens():
    assert _promql_syntax_errors('(sum(up{job="x"})') != []


def test_promql_syntax_rejects_unbalanced_braces():
    assert _promql_syntax_errors('sum(up{job="x")}') != []


def test_promql_syntax_rejects_empty():
    assert _promql_syntax_errors("") != []
    assert _promql_syntax_errors("   ") != []


# --- label PromQL épinglé (revue findings TV, MEDIUM label) ---


def test_http_5xx_rate_label_is_server():
    """Gèle la convention de label utilisée pour apparier le trafic HTTP par
    brique tant qu'aucun job de scrape réel ne la confirme (cf. commentaire
    au-dessus de _promql_syntax_errors) : toute évolution doit passer par ce
    test, pas par une divergence silencieuse."""
    out = yaml.safe_load(generate_alerts_yaml(manifests_fixture(), "sese"))
    rule = next(
        rule
        for rule in out["groups"][0]["rules"]
        if rule["uid"] == "brick-umami-http_5xx_rate"
    )
    expr = rule["data"][0]["model"]["expr"]
    assert 'server=~".*_umami$"' in expr


# --- window/threshold : plus de string libre non validée (findings TV HIGH/MEDIUM) ---


def test_http_5xx_rate_relative_time_range_scales_with_window():
    fixtures = manifests_fixture()
    umami = fixtures[0][1]
    umami["monitoring"]["alerts"][-1]["window"] = "10m"
    out = yaml.safe_load(generate_alerts_yaml(fixtures, "sese"))
    rule = next(
        rule
        for rule in out["groups"][0]["rules"]
        if rule["uid"] == "brick-umami-http_5xx_rate"
    )
    # 10m = 600s ; relativeTimeRange.from doit couvrir >= 2x la fenêtre du rate.
    assert rule["data"][0]["relativeTimeRange"]["from"] >= 1200
    # "for" (durée de pending) n'est plus dérivé de window (revue TV HIGH).
    assert rule["for"] != "10m"


def test_invalid_window_rejected_by_schema():
    from scripts.brick_generate import validate_manifest, load_versions

    fixtures = manifests_fixture()
    umami = fixtures[0][1]
    umami["monitoring"]["alerts"][-1]["window"] = "jamais"
    errors = validate_manifest(umami, Path("roles/umami/brick.yml"), load_versions())
    assert any("window" in err for err in errors)


def test_invalid_threshold_rejected_by_schema():
    from scripts.brick_generate import validate_manifest, load_versions

    fixtures = manifests_fixture()
    umami = fixtures[0][1]
    umami["monitoring"]["alerts"][-1]["threshold"] = "beaucoup"
    errors = validate_manifest(umami, Path("roles/umami/brick.yml"), load_versions())
    assert any("threshold" in err for err in errors)


def test_threshold_window_on_non_http5xx_kind_rejected():
    """finding TV MEDIUM : threshold/window n'étaient honorés que par la
    branche http_5xx_rate de _alert_rule — un manifeste {kind: restart_loop,
    threshold: '10', window: '30m'} passait la validation puis les voyait
    silencieusement ignorés à la génération. Doit désormais être rejeté avant
    toute génération."""
    from scripts.brick_generate import validate_manifest, load_versions

    fixtures = manifests_fixture()
    umami = fixtures[0][1]
    restart_loop = next(a for a in umami["monitoring"]["alerts"] if a["kind"] == "restart_loop")
    restart_loop["threshold"] = "10"
    restart_loop["window"] = "30m"
    errors = validate_manifest(umami, Path("roles/umami/brick.yml"), load_versions())
    assert any("threshold" in e or "window" in e for e in errors)
    # cmd_generate_alerts refuse la génération avant même d'appeler
    # generate_alerts_yaml quand validate_manifest remonte des erreurs — c'est
    # ce chemin (CLI), pas generate_alerts_yaml seule, qui doit bloquer cette
    # config (cf. test_missing_backup_or_alerts_fails_before_generation).


def test_duplicate_alert_kind_rejected():
    from scripts.brick_generate import validate_manifest, load_versions

    fixtures = manifests_fixture()
    umami = fixtures[0][1]
    umami["monitoring"]["alerts"].append({"kind": "service_down"})
    errors = validate_manifest(umami, Path("roles/umami/brick.yml"), load_versions())
    assert any("dupliqués" in err for err in errors)


# --- gate du lot : diff entre source et artefact committé ---


def test_declared_environments_matches_committed_bricks():
    # trek (seul manifeste réel) déclare sese — la commande --list-envs doit le
    # retrouver sans dépendre d'un glob des fichiers déjà générés.
    assert "sese" in declared_environments()


def test_manually_edited_artifact_fails_check(tmp_path):
    from scripts.brick_generate import main

    repo = tmp_path
    (repo / "roles" / "trek").mkdir(parents=True)
    (repo / "roles" / "trek" / "brick.yml").write_text(
        Path("roles/trek/brick.yml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert main(["--generate", "alerts", "--env", "sese", "--repo", str(repo)]) == 0
    target = repo / alerts_yaml_path("sese")
    original = target.read_text(encoding="utf-8")
    target.write_text(original.replace("gt", "lt"), encoding="utf-8")
    assert main(["--generate", "alerts", "--env", "sese", "--repo", str(repo), "--check"]) == 1


def test_missing_backup_or_alerts_fails_before_generation(tmp_path):
    """Gate du lot V : un manifeste sans backup.strategy ou sans les alertes
    minimales est déjà refusé par validate_manifest (schéma + assertions §5) —
    la génération (backup et alertes) réutilise ce même chemin de validation
    et refuse donc d'émettre un artefact pour un manifeste invalide."""
    from scripts.brick_generate import main

    repo = tmp_path
    (repo / "roles" / "trek").mkdir(parents=True)
    broken = yaml.safe_load(Path("roles/trek/brick.yml").read_text(encoding="utf-8"))
    del broken["monitoring"]["alerts"]
    (repo / "roles" / "trek" / "brick.yml").write_text(
        yaml.safe_dump(broken), encoding="utf-8"
    )
    assert main(["--generate", "alerts", "--env", "sese", "--repo", str(repo)]) == 1
    assert main(["--generate", "backup", "--env", "sese", "--repo", str(repo)]) == 1
