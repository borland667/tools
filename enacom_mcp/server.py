"""FastMCP server exposing tools for the ENACOM Hertz workflow.

Run with:
    python -m enacom_mcp

Connect from your MCP client (Claude Desktop, Cowork, Claude Code, etc.).

Tools exposed:
  - tracker_summary(): counts by status
  - list_pending_ddjj(limit?): list pending rows from the Excel tracker
  - update_tracker(...): mutate one row of the tracker
  - hertz_open_and_login(): launch browser, wait for manual login
  - hertz_open_workspace(): navigate to "Declaraciones Juradas"
  - submit_one(servicio, anio, periodo_num): create+fill+submit one DDJJ
  - submit_batch(limit, dry_run): iterate over pending DDJJ
  - close_session(): tear down the browser
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .hertz import HertzClient, HertzConfig
from .tracker import Tracker

load_dotenv()
logging.basicConfig(
    level=os.getenv("ENACOM_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("enacom_mcp.server")

mcp = FastMCP("enacom-ddjj")

_tracker_path = os.getenv("ENACOM_TRACKER_PATH")
if not _tracker_path:
    raise RuntimeError(
        "ENACOM_TRACKER_PATH is not set. Copy .env.example to .env and fill it in."
    )
TRACKER = Tracker(_tracker_path)

# Hertz client is created lazily when first browser tool is called.
_hertz: HertzClient | None = None


def _hertz_client() -> HertzClient:
    global _hertz
    if _hertz is None:
        _hertz = HertzClient(HertzConfig.from_env())
        _hertz.start()
    return _hertz


# ---------- Tracker tools ----------

@mcp.tool()
def tracker_summary() -> dict[str, Any]:
    """Return counts of DDJJ by status, from the Excel tracker."""
    return TRACKER.summary()


@mcp.tool()
def list_pending_ddjj(limit: int = 0) -> list[dict]:
    """List pending DDJJ rows from the tracker.

    Args:
        limit: max rows to return; 0 = all
    """
    rows = [r.as_dict() for r in TRACKER.list_pending()]
    return rows[:limit] if limit else rows


@mcp.tool()
def update_tracker(
    servicio: str,
    anio: int,
    periodo_num: int,
    estado: str | None = None,
    carpeta_tecnica: str | None = None,
    fecha_presentacion: str | None = None,
    notas: str | None = None,
) -> dict:
    """Update one row of the tracker.

    Args:
        servicio: "TCFV" | "SU-M" | "SU-T"
        anio: e.g. 2024
        periodo_num: 1-12
        estado: optional new status
        carpeta_tecnica: optional Nº de Carpeta Técnica
        fecha_presentacion: optional ISO date string YYYY-MM-DD
        notas: optional free-text notes
    """
    row = TRACKER.update(
        servicio, anio, periodo_num,
        estado=estado, carpeta_tecnica=carpeta_tecnica,
        fecha_presentacion=fecha_presentacion, notas=notas,
    )
    return row.as_dict()


# ---------- Hertz tools ----------

@mcp.tool()
def hertz_open_and_login(timeout_seconds: int = 300) -> dict:
    """Open a Chromium window pointed at TAD. You log in manually.

    The MCP polls until it detects the Hertz portal. Returns once you
    arrive at Hertz successfully.
    """
    h = _hertz_client()
    h.open_tad_and_wait_login(timeout_seconds=timeout_seconds)
    return {"status": "ok", "message": "Hertz reached. Ready to operate."}


@mcp.tool()
def hertz_open_workspace() -> dict:
    """Navigate from Hertz home into the Declaraciones Juradas workspace."""
    h = _hertz_client()
    h.select_profile()
    h.open_declaraciones_juradas()
    return {"status": "ok"}


@mcp.tool()
def submit_one(servicio: str, anio: int, periodo_num: int) -> dict:
    """Create + fill (in zero) + submit ONE DDJJ for the given period.

    Behavior:
      • Reads the row from the tracker for context.
      • Skips if estado is already 'Enviada', 'Validada' or 'Finalizada'.
      • In ENACOM_DRY_RUN=true mode: stops before clicking 'Enviar' and
        leaves the draft visible for you to review.
      • Updates the tracker row with the new Carpeta Técnica and estado.
    """
    row = TRACKER.find(servicio, anio, periodo_num)
    if row is None:
        return {"status": "error", "message": f"Row not found: {servicio} {anio}-{periodo_num}"}
    if row.estado.lower() in ("enviada", "validada", "finalizada"):
        return {"status": "skipped", "message": f"Already {row.estado}", "row": row.as_dict()}

    h = _hertz_client()
    carpeta = h.create_ddjj(
        servicio=servicio,
        anio=anio,
        periodo_nombre=row.periodo_nombre,
    )
    h.fill_principal_zero()
    h.submit_ddjj()

    new_estado = "En curso" if h.cfg.dry_run else "Enviada"
    fecha = dt.date.today().isoformat() if not h.cfg.dry_run else None
    updated = TRACKER.update(
        servicio, anio, periodo_num,
        estado=new_estado, carpeta_tecnica=carpeta,
        fecha_presentacion=fecha,
    )
    return {
        "status": "ok",
        "dry_run": h.cfg.dry_run,
        "carpeta_tecnica": carpeta,
        "row": updated.as_dict(),
    }


@mcp.tool()
def submit_batch(limit: int = 5) -> dict:
    """Iterate over pending DDJJ and submit each one.

    Honors ENACOM_DRY_RUN. Recommended: start with limit=1 until you've
    verified the selectors against your Hertz UI.
    """
    h = _hertz_client()
    pending = TRACKER.list_pending()
    if limit:
        pending = pending[:limit]

    results: list[dict] = []
    for row in pending:
        try:
            r = submit_one(row.servicio, row.anio, row.periodo_num)
            results.append({"period": f"{row.servicio} {row.anio}-{row.periodo_num:02d}", **r})
        except Exception as e:
            log.exception("submit_one failed for %s", row)
            results.append({
                "period": f"{row.servicio} {row.anio}-{row.periodo_num:02d}",
                "status": "error",
                "message": str(e),
            })
            break  # stop on first failure to avoid cascading mistakes
    return {"processed": len(results), "results": results}


@mcp.tool()
def close_session() -> dict:
    """Close the Playwright browser session, if open."""
    global _hertz
    if _hertz is not None:
        _hertz.stop()
        _hertz = None
    return {"status": "closed"}
