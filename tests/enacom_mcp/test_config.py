"""Tests for HertzConfig.from_env environment parsing.

hertz.py imports Playwright at module load, so skip cleanly if it's absent.
"""
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from enacom_mcp.hertz import HertzConfig  # noqa: E402


def test_defaults_when_env_absent(monkeypatch):
    for var in (
        "ENACOM_HEADED", "ENACOM_DRY_RUN", "ENACOM_ARTIFACTS_DIR",
        "ENACOM_STORAGE_STATE", "ENACOM_CUIT", "ENACOM_RAZON_SOCIAL",
        "ENACOM_FUNDAMENTO",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = HertzConfig.from_env()
    assert cfg.headed is True          # safe default: visible browser
    assert cfg.dry_run is True         # safe default: do not send
    assert cfg.storage_state is None
    assert cfg.artifacts_dir == Path("./artifacts")


def test_booleans_are_case_insensitive(monkeypatch):
    monkeypatch.setenv("ENACOM_HEADED", "FALSE")
    monkeypatch.setenv("ENACOM_DRY_RUN", "False")
    cfg = HertzConfig.from_env()
    assert cfg.headed is False
    assert cfg.dry_run is False


def test_dry_run_only_true_for_exactly_true(monkeypatch):
    # Anything other than "true" (any case) disables dry_run — but the default
    # (unset) stays safe because from_env defaults the string to "true".
    monkeypatch.setenv("ENACOM_DRY_RUN", "yes")
    assert HertzConfig.from_env().dry_run is False
    monkeypatch.setenv("ENACOM_DRY_RUN", "true")
    assert HertzConfig.from_env().dry_run is True


def test_storage_state_path_parsed(monkeypatch, tmp_path):
    p = tmp_path / "state.json"
    monkeypatch.setenv("ENACOM_STORAGE_STATE", str(p))
    cfg = HertzConfig.from_env()
    assert cfg.storage_state == p


def test_identity_fields_passed_through(monkeypatch):
    monkeypatch.setenv("ENACOM_CUIT", "20-12345678-9")
    monkeypatch.setenv("ENACOM_RAZON_SOCIAL", "TITULAR X")
    monkeypatch.setenv("ENACOM_FUNDAMENTO", "Sin actividad")
    cfg = HertzConfig.from_env()
    assert cfg.cuit == "20-12345678-9"
    assert cfg.razon_social == "TITULAR X"
    assert cfg.fundamento == "Sin actividad"
