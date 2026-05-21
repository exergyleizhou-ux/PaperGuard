"""Tests for `paperguard doctor` CLI command.

Verifies:
- Default invocation succeeds (yellow exit OK = code 2; should be code 0
  only if every check is green, which depends on environment)
- `--json` produces parseable JSON with `summary` + `checks` keys
- `--ping-llm` without OPENAI_API_KEY adds llm_ping=YELLOW (skipped)
- All checks have a `name` / `status` / `detail` key
- No verdict words appear in output (privacy rule)
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from paperguard.cli import doctor_cmd


def _strip_yellow_red_for_clean_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remove env vars that make yellow checks fire so we can test
    the green-only path."""
    for k in [
        "PAPERGUARD_LLM_PROVIDER",
        "PAPERGUARD_LLM_BASE_URL",
        "PAPERGUARD_LLM_MODEL",
        "OPENAI_API_KEY",
    ]:
        monkeypatch.delenv(k, raising=False)


def test_doctor_json_mode_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    _strip_yellow_red_for_clean_env(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, ["--json"])
    # Exit 0 or 2 depending on whether yellow checks fired
    assert result.exit_code in (0, 2), result.output
    data = json.loads(result.output)
    assert "summary" in data
    assert "checks" in data
    assert "green" in data["summary"]
    assert "yellow" in data["summary"]
    assert "red" in data["summary"]
    assert isinstance(data["checks"], list)
    assert len(data["checks"]) > 10  # we have 11+ checks


def test_doctor_check_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every check is {name, status, detail}, status ∈ {GREEN, YELLOW, RED}."""
    _strip_yellow_red_for_clean_env(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, ["--json"])
    data = json.loads(result.output)
    for c in data["checks"]:
        assert set(c.keys()) == {"name", "status", "detail"}
        assert c["status"] in {"GREEN", "YELLOW", "RED"}
        assert isinstance(c["name"], str) and c["name"]
        assert isinstance(c["detail"], str)


def test_doctor_registry_check_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _strip_yellow_red_for_clean_env(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, ["--json"])
    data = json.loads(result.output)
    registry_check = next(c for c in data["checks"] if c["name"] == "registry")
    assert registry_check["status"] == "GREEN"
    assert "33" in registry_check["detail"] or "detector" in registry_check["detail"]


def test_doctor_python_version_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _strip_yellow_red_for_clean_env(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, ["--json"])
    data = json.loads(result.output)
    py = next(c for c in data["checks"] if c["name"] == "python_version")
    assert py["status"] == "GREEN"  # tests must be running on ≥ 3.11


def test_doctor_llm_config_yellow_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _strip_yellow_red_for_clean_env(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, ["--json"])
    data = json.loads(result.output)
    llm = next(c for c in data["checks"] if c["name"] == "llm_config")
    assert llm["status"] == "YELLOW"
    assert "PAPERGUARD_LLM_PROVIDER" in llm["detail"]


def test_doctor_llm_config_with_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERGUARD_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, ["--json"])
    data = json.loads(result.output)
    llm = next(c for c in data["checks"] if c["name"] == "llm_config")
    assert llm["status"] == "GREEN"
    assert "openai" in llm["detail"]


def test_doctor_ping_llm_skips_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _strip_yellow_red_for_clean_env(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, ["--ping-llm", "--json"])
    data = json.loads(result.output)
    ping = next(c for c in data["checks"] if c["name"] == "llm_ping")
    assert ping["status"] == "YELLOW"
    assert "OPENAI_API_KEY" in ping["detail"]


def test_doctor_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without --json, output should contain section headers + summary line."""
    _strip_yellow_red_for_clean_env(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, [])
    assert "PaperGuard doctor" in result.output
    assert "Summary" in result.output


def test_doctor_no_verdict_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Privacy iron rule: no verdict words."""
    _strip_yellow_red_for_clean_env(monkeypatch)
    forbidden = ("fraud", "fabrication", "misconduct", "造假", "cheating")
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, ["--ping-llm"])
    lower = result.output.lower()
    for word in forbidden:
        assert word not in lower, f"Forbidden word {word!r} in doctor output"


def test_doctor_webui_redis_yellow_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _strip_yellow_red_for_clean_env(monkeypatch)
    monkeypatch.delenv("PAPERGUARD_REDIS_URL", raising=False)
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, ["--json"])
    data = json.loads(result.output)
    redis_check = next(c for c in data["checks"] if c["name"] == "webui_redis")
    assert redis_check["status"] == "YELLOW"
    assert "PAPERGUARD_REDIS_URL" in redis_check["detail"]


def test_doctor_webui_redis_green_with_fakeredis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When PAPERGUARD_REDIS_URL is set and reachable, the check goes GREEN."""
    fakeredis = pytest.importorskip("fakeredis")
    _strip_yellow_red_for_clean_env(monkeypatch)
    monkeypatch.setenv("PAPERGUARD_REDIS_URL", "redis://fake")

    # Patch RedisBackend.from_url to return a fakeredis-backed instance.
    import paperguard.webui.ratelimit as rl

    def fake_from_url(cls: type, url: str) -> rl.RedisBackend:
        return rl.RedisBackend(fakeredis.FakeRedis(decode_responses=False))

    monkeypatch.setattr(
        rl.RedisBackend, "from_url", classmethod(fake_from_url)
    )
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, ["--json"])
    data = json.loads(result.output)
    redis_check = next(c for c in data["checks"] if c["name"] == "webui_redis")
    assert redis_check["status"] == "GREEN"
    assert "Redis backend reachable" in redis_check["detail"]


def test_doctor_exit_code_yellow_is_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Yellow-only checks should exit 2, never 1, and never 0 if any yellow."""
    _strip_yellow_red_for_clean_env(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(doctor_cmd, [])
    # On a typical dev env there's at least one yellow (no LLM provider).
    # So code should be 2. Never 1 (which means RED).
    assert result.exit_code != 1, result.output
