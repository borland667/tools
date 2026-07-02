"""Smoke test: the MCP server imports and registers the expected tools.

The server module reads ENACOM_TRACKER_PATH at import time and imports Playwright
(via hertz). We create a temp tracker, point the env at it, and skip if Playwright
isn't installed.
"""
import asyncio
import importlib
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

pytest.importorskip("playwright")

from enacom_mcp.tracker import SHEET  # noqa: E402

EXPECTED_TOOLS = {
    "tracker_summary",
    "list_pending_ddjj",
    "update_tracker",
    "hertz_open_and_login",
    "hertz_open_workspace",
    "hertz_login_open",
    "hertz_login_status",
    "hertz_login_capture",
    "hertz_dump_dom",
    "submit_one",
    "submit_batch",
    "close_session",
}


@pytest.fixture
def server_module(tmp_path: Path, monkeypatch):
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(["#", "Servicio", "Año", "Período", "Mes/Trim", "Estado",
               "Nº Carpeta Técnica", "Fecha presentación", "Fundamento usado", "Notas"])
    ws.append([1, "TCFV", 2023, 1, "Enero", "Pendiente", None, None, None, None])
    tracker = tmp_path / "tracker.xlsx"
    wb.save(tracker)

    monkeypatch.setenv("ENACOM_TRACKER_PATH", str(tracker))
    # Force a clean import so the module-level env read picks up our tracker.
    sys.modules.pop("enacom_mcp.server", None)
    mod = importlib.import_module("enacom_mcp.server")
    try:
        yield mod
    finally:
        sys.modules.pop("enacom_mcp.server", None)


def test_all_tools_registered(server_module):
    tools = asyncio.run(server_module.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS


def test_tracker_tools_work_without_browser(server_module):
    # Tracker-backed tools must not require the Playwright session.
    summary = server_module.tracker_summary()
    assert summary["total"] == 1
    assert summary["by_status"]["Pendiente"] == 1
    pending = server_module.list_pending_ddjj()
    assert len(pending) == 1
    assert pending[0]["servicio"] == "TCFV"


def test_missing_tracker_path_raises(monkeypatch):
    # Empty (rather than unset) so a project .env loaded by load_dotenv(override=
    # False) at import time can't silently repopulate it. server.py treats an
    # empty ENACOM_TRACKER_PATH as "not configured" and must raise.
    monkeypatch.setenv("ENACOM_TRACKER_PATH", "")
    sys.modules.pop("enacom_mcp.server", None)
    with pytest.raises(RuntimeError):
        importlib.import_module("enacom_mcp.server")
    sys.modules.pop("enacom_mcp.server", None)
