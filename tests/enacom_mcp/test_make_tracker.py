"""Tests for the tracker generator (make_tracker) and its round-trip through Tracker."""
from pathlib import Path

import pytest

from enacom_mcp.scripts.make_tracker import Period, parse_range_spec, build_tracker
from enacom_mcp.tracker import Tracker


def test_parse_range_spec_single_month():
    got = parse_range_spec("2023-05:2023-05", "TCFV")
    assert got == [Period("TCFV", 2023, 5)]


def test_parse_range_spec_spans_year_boundary():
    got = parse_range_spec("2023-11:2024-02", "SU-M")
    assert [(p.anio, p.mes) for p in got] == [(2023, 11), (2023, 12), (2024, 1), (2024, 2)]


def test_parse_range_spec_multiple_chunks():
    got = parse_range_spec("2023-01:2023-02,2023-06:2023-06", "TCFV")
    assert [(p.anio, p.mes) for p in got] == [(2023, 1), (2023, 2), (2023, 6)]


def test_parse_range_spec_rejects_inverted():
    with pytest.raises(ValueError):
        parse_range_spec("2024-05:2024-01", "TCFV")


def test_parse_range_spec_rejects_malformed():
    with pytest.raises(ValueError):
        parse_range_spec("2024/05-2024/06", "TCFV")


def test_mes_nombre():
    assert Period("TCFV", 2023, 1).mes_nombre == "Enero"
    assert Period("TCFV", 2023, 12).mes_nombre == "Diciembre"


def test_build_tracker_roundtrips_through_tracker(tmp_path: Path):
    periods = (
        parse_range_spec("2023-01:2023-03", "TCFV")
        + parse_range_spec("2023-01:2023-02", "SU-M")
    )
    out = tmp_path / "tracker.xlsx"
    n = build_tracker("20-12345678-9", "TEST TITULAR", periods, out)
    assert n == 5
    assert out.exists()

    t = Tracker(out)
    rows = t.list_all()
    assert len(rows) == 5
    # All start as Pendiente
    assert t.summary() == {"total": 5, "by_status": {"Pendiente": 5}}
    assert len(t.list_pending()) == 5
    # Servicios present and periodo names populated
    assert {r.servicio for r in rows} == {"TCFV", "SU-M"}
    assert all(r.periodo_nombre for r in rows)


def test_build_tracker_find_and_update(tmp_path: Path):
    periods = parse_range_spec("2023-01:2023-01", "TCFV")
    out = tmp_path / "t.xlsx"
    build_tracker("20-1-9", "X", periods, out)
    t = Tracker(out)
    assert t.find("TCFV", 2023, 1) is not None
    updated = t.update("TCFV", 2023, 1, estado="Enviada", carpeta_tecnica="119999.9")
    assert updated.estado == "Enviada"
    assert updated.carpeta_tecnica == "119999.9"
