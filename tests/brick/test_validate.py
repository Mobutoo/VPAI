import copy
from pathlib import Path

import yaml

from scripts.brick_generate import load_manifest, validate_manifest

FIXTURES = Path(__file__).parent / "fixtures"


def valid():
    return yaml.safe_load((FIXTURES / "umami-valid.yml").read_text())


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
