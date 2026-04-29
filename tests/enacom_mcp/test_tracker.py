"""Smoke tests for tracker.py.

Run with:  pytest tests/
"""
from pathlib import Path

import pytest
from openpyxl import Workbook

from enacom_mcp.tracker import Tracker, SHEET


@pytest.fixture
def tmp_tracker(tmp_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(["#", "Servicio", "Año", "Período", "Mes/Trim", "Estado",
               "Nº Carpeta Técnica", "Fecha presentación", "Fundamento usado", "Notas"])
    ws.append([1, "TCFV", 2023, 1, "Enero", "Pendiente", None, None, None, None])
    ws.append([2, "SU-M", 2023, 1, "Enero", "Pendiente", None, None, None, None])
    p = tmp_path / "t.xlsx"
    wb.save(p)
    return p


def test_list_all(tmp_tracker):
    t = Tracker(tmp_tracker)
    rows = t.list_all()
    assert len(rows) == 2
    assert rows[0].servicio == "TCFV"


def test_list_pending(tmp_tracker):
    t = Tracker(tmp_tracker)
    assert len(t.list_pending()) == 2


def test_update(tmp_tracker):
    t = Tracker(tmp_tracker)
    updated = t.update("TCFV", 2023, 1, estado="Enviada", carpeta_tecnica="119715.X")
    assert updated.estado == "Enviada"
    assert updated.carpeta_tecnica == "119715.X"


def test_summary(tmp_tracker):
    t = Tracker(tmp_tracker)
    s = t.summary()
    assert s["total"] == 2
    assert s["by_status"]["Pendiente"] == 2
