# enacom_mcp

MCP server that automates DDJJ filings on ENACOM's **Portal Hertz** for TIC licensees, using a real Chromium browser (Playwright). Scoped to TCFV and SU-M (and SU-T historical, if needed).

> ⚠️  A DDJJ is a sworn declaration. This tool helps you click faster; it does not absolve you of legal responsibility for what gets submitted. Always start in `ENACOM_DRY_RUN=true` mode and visually review drafts before flipping the switch.

## What it does

- Reads pending periods from your Excel tracker.
- Opens a visible Chromium window pointed at TAD; you log in manually with AFIP clave fiscal.
- Drives the Hertz UI to: open *Declaraciones Juradas* → *+ Nueva DDJJ* → fill *Datos Generales* → fill *Formulario Principal* in zero → click *Enviar*.
- Updates the tracker with the assigned `Nº Carpeta Técnica` and new status.
- Snapshots every step into the artifacts dir for audit.

## What it deliberately does NOT do

- Does not ask for or store your AFIP password.
- Does not submit anything when `ENACOM_DRY_RUN=true` (the default).
- Does not assume responsibility for incorrect filings — review before unchecking dry-run.

## Install

```bash
cd enacom_mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
cp .env.example .env
# edit .env to set ENACOM_TRACKER_PATH (and your CUIT/razón social/fundamento)
```

## Generate a tracker

```bash
python -m enacom_mcp.scripts.make_tracker \
    --cuit 20-XXXXXXXXX-X \
    --razon-social "NOMBRE APELLIDO" \
    --tcfv 2023-01:2024-12,2025-06:2025-12 \
    --su-m 2023-01:2024-12,2025-07:2025-12 \
    --output ~/enacom/tracker.xlsx
```

Then point `ENACOM_TRACKER_PATH` in `.env` at that file.

## Run the MCP server

```bash
python -m enacom_mcp
```

This starts an MCP server over stdio. Wire it up in your MCP client of choice (Claude Desktop, Cowork, Claude Code).

### Claude Desktop config (example)

```jsonc
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "enacom-ddjj": {
      "command": "/absolute/path/to/repo/enacom_mcp/.venv/bin/python",
      "args": ["-m", "enacom_mcp"],
      "env": {
        "ENACOM_TRACKER_PATH": "/absolute/path/to/tracker.xlsx",
        "ENACOM_DRY_RUN": "true"
      }
    }
  }
}
```

## Tools exposed

| Tool | Purpose |
|---|---|
| `tracker_summary()` | Counts of DDJJ by status |
| `list_pending_ddjj(limit?)` | Pending rows from the tracker |
| `update_tracker(...)` | Mutate one tracker row by hand |
| `hertz_open_and_login(timeout_seconds?)` | Launch browser, wait for manual login |
| `hertz_open_workspace()` | Navigate to Declaraciones Juradas |
| `submit_one(servicio, anio, periodo_num)` | Create+fill+submit one DDJJ |
| `submit_batch(limit?)` | Iterate over pending DDJJ |
| `close_session()` | Tear down browser |

## Selectors

Hertz is gated behind clave fiscal so the selectors in `selectors.py` were inferred from ENACOM's official PDF guide and **almost certainly need a few tweaks** the first time you run it. Recommended bring-up:

1. Run with `ENACOM_HEADED=true ENACOM_DRY_RUN=true`.
2. Call `hertz_open_and_login()`. Log into TAD, open *Declaraciones juradas TCFV/SU – HERTZ*.
3. Call `hertz_open_workspace()`. If something fails, open DevTools (F12), find the right selector, paste it into `selectors.py`, restart.
4. Call `submit_one("TCFV", 2023, 1)`. Watch the form fill itself; the browser stops before *Enviar* because of dry-run.
5. If the draft looks correct, set `ENACOM_DRY_RUN=false` and call `submit_one` again on the same period.
6. Run `submit_batch(limit=1)` then `submit_batch(limit=5)` once you trust it.

## Tests

```bash
pytest tests/enacom_mcp/
```
