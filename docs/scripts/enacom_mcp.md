# enacom_mcp

## Purpose

MCP (Model Context Protocol) server that automates DDJJ submission on ENACOM's
Portal Hertz for TIC licensees, using a real Chromium browser via Playwright.
Scoped to monthly TCFV (Tasa de Control, Fiscalización y Verificación) and
SU-M (Aporte al Servicio Universal Mensual). The companion
`enacom_mcp.scripts.make_tracker` generates the Excel tracker the server reads
from and writes back to.

Use this when:

- You're a TIC licensee with a backlog of DDJJ to file in cero.
- You want to automate the click-through on Hertz without exposing your AFIP
  clave fiscal — login is always manual.
- You want a single source of truth (the Excel tracker) for what's pending,
  in flight, and finalized.

Do NOT use this for:

- Filings with non-zero amounts. The current zero-fill helper assumes no
  taxable activity in the period.
- Bulk submission without verification. Always run in dry-run first.

## Requirements

- Python 3.10+.
- AFIP clave fiscal nivel 3 (for TAD login). Manual.
- Optional: Playwright Chromium runtime (`playwright install chromium`).
- Optional dependency in `pip install -e .` mode pulls `mcp`, `playwright`,
  `openpyxl`, `python-dotenv`, `pydantic`.

The `make_tracker` script alone needs only `openpyxl`.

## Quick Start

```bash
cd enacom_mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium
cp .env.example .env  # edit ENACOM_TRACKER_PATH and personal fields

python -m enacom_mcp.scripts.make_tracker \
    --cuit 20-XXXXXXXXX-X \
    --razon-social "NOMBRE APELLIDO" \
    --tcfv 2023-01:2024-12,2025-06:2025-12 \
    --su-m 2023-01:2024-12,2025-07:2025-12 \
    --output ./tracker.xlsx

python -m enacom_mcp  # starts MCP server on stdio
```

Wire the server into your MCP client (Claude Desktop, Cowork, Claude Code) by
pointing it at `python -m enacom_mcp` with the venv's interpreter.

## Common Usage Patterns

### Generate a tracker for a typical backlog

```bash
python -m enacom_mcp.scripts.make_tracker \
    --cuit 20-12345678-9 \
    --razon-social "JOHN DOE" \
    --tcfv 2023-01:2025-12 \
    --su-m 2023-01:2025-12 \
    --output ./tracker.xlsx
```

### Dry-run a single period from your MCP client

```text
> tracker_summary()
> list_pending_ddjj(limit=3)
> hertz_open_and_login(timeout_seconds=600)
> hertz_open_workspace()
> submit_one(servicio="TCFV", anio=2023, periodo_num=1)
```

The browser stops before clicking *Enviar*. Visually review the draft, then
set `ENACOM_DRY_RUN=false` in `.env`, restart, and re-call `submit_one`.

> ⚠️  **Dry run is not a no-op.** Even with `ENACOM_DRY_RUN=true`, `submit_one`
> creates a **real draft** in the portal and saves its *Datos Generales* — only
> the final *Enviar* click is skipped. The tracker row also moves to `En curso`
> (not `Pendiente`), so a later `submit_batch` will **not** re-process it. To
> actually send a dry-run draft, set `ENACOM_DRY_RUN=false` and re-call
> `submit_one` for the same period.

### Capture login once, reuse the session

The blocking `hertz_open_and_login` requires the MCP client to hold the call
open for the whole login (which can take minutes and dies if interrupted).
The non-blocking capture flow is more robust: each tool call is short, and
the resulting cookies are reused on every subsequent run via
`ENACOM_STORAGE_STATE`.

```text
> hertz_login_open()              # opens browser at TAD, returns immediately
# ... log in via AFIP, navigate to "Declaraciones juradas TCFV/SU – HERTZ" ...
> hertz_login_status()            # optional: confirms current_url contains hertz.enacom.gob.ar
> hertz_login_capture()           # writes cookies to ENACOM_STORAGE_STATE
> hertz_open_workspace()
> submit_one(...)
```

On subsequent runs, `hertz_login_open()` auto-loads the saved cookies and you
usually skip straight to `hertz_open_workspace()`.

### Mark a period filed by hand

```text
> update_tracker(servicio="TCFV", anio=2023, periodo_num=1,
                 estado="Enviada",
                 carpeta_tecnica="119715.250407073525.55",
                 fecha_presentacion="2026-04-30")
```

## Arguments and Options

### `make_tracker`

Required:

- `--cuit`: CUIT of the licensee (e.g. `20-12345678-9`)
- `--razon-social`: name displayed in the tracker and on export sheet
- `--output` / `-o`: output `.xlsx` path

Optional (at least one required):

- `--tcfv`: TCFV period ranges, comma-separated, format `YYYY-MM:YYYY-MM`
- `--su-m`: SU-M monthly period ranges, same format
- `--su-t`: SU-T quarterly period ranges (for legacy 2007–2016 filings)

### `enacom_mcp` server

Configured entirely via env vars (see `.env.example`):

- `ENACOM_TRACKER_PATH` (required): absolute path to the Excel tracker
- `ENACOM_ARTIFACTS_DIR`: where Playwright screenshots/exports land
- `ENACOM_HEADED`: `true` (default) for visible browser, `false` for headless
- `ENACOM_DRY_RUN`: `true` (default) skips final *Enviar* click
- `ENACOM_CUIT`, `ENACOM_RAZON_SOCIAL`, `ENACOM_FUNDAMENTO`: prefilled into forms
- `ENACOM_STORAGE_STATE`: optional Playwright storage-state path to skip login

## Input and Output

Input:

- An Excel tracker generated by `make_tracker`. Schema: 10 columns starting
  with `# | Servicio | Año | Período | Mes/Trim | Estado | Nº Carpeta Técnica
  | Fecha presentación | Fundamento usado | Notas`.

Output:

- The same Excel tracker, mutated in place: `Estado`, `Nº Carpeta Técnica`,
  `Fecha presentación` are updated as the MCP submits each DDJJ.
- Per-step PNG screenshots in `ENACOM_ARTIFACTS_DIR` for audit.
- Hertz's own portal-side state (drafts, sent DDJJ) is the authoritative
  record once filings reach *Validadas* / *Finalizadas*.

## Internal Behavior Summary

1. `make_tracker` builds the Excel template with three sheets (Tracker,
   Resumen, DJ FINALIZADAS).
2. The MCP server boots with FastMCP and registers tools.
3. `hertz_open_and_login` (or the non-blocking `hertz_login_open` /
   `hertz_login_capture` pair) launches Chromium and waits for the user to
   reach the Hertz portal via TAD.
4. `hertz_dump_dom` can snapshot any page's HTML + a full-page screenshot +
   a JSON inventory of interactive elements (each with a suggested Playwright
   locator) into the artifacts dir, so real selectors can replace the guessed
   ones in `selectors.py`.
5. `submit_one` clicks `+ Nueva DDJJ`, captures the Carpeta Técnica number,
   fills Datos Generales (servicio / período / año / Original / fundamento)
   and the Formulario Principal in zero, and either submits or stops on
   dry-run.
6. The tracker row is updated to `Enviada` (live) or `En curso` (dry-run).
7. Screenshots are written into the artifacts dir at every meaningful step.

Selector strategy: for buttons/links/tabs the client tries a role-based
`get_by_role(name=...)` locator (using the `NAME_*` constants in
`selectors.py`) first and falls back to the raw CSS constant, so a wrong CSS
guess degrades gracefully rather than hard-failing.
7. `submit_batch` iterates over pending rows; stops on the first error to
   avoid cascading mistakes.
8. `close_session` tears down the browser.

## Safety Notes

- `ENACOM_DRY_RUN=true` is the default. The server fills forms but **does not
  click final *Enviar*** until you flip the env var off.
- The server never asks for or stores your AFIP password; you type it in the
  browser yourself. If you set `ENACOM_STORAGE_STATE`, Playwright writes a
  session-cookie file to that path so later runs can skip login. Treat that
  file as a credential: keep it outside the repository and never commit it.
- `ENACOM_ARTIFACTS_DIR` (default `./artifacts`) holds full-page screenshots
  of a logged-in government portal plus element dumps. `artifacts/`, `*.xlsx`
  and `.scan_state/` are gitignored — do not force-add them.
- Selectors in `selectors.py` are inferred from ENACOM's PDF guide and may
  need adjustment on first use. Each tool logs the selector it tried.
- DDJJ are sworn declarations. Even when automated, the licensee is legally
  responsible for the filing.
- The tracker is mutated in place. Keep it backed up if you care about
  historical state.

## Known Limitations

- Hertz UI is not public. Selectors are inferred from screenshots in
  ENACOM's official PDF guide and will likely need a few tweaks the first
  time you run them.
- Only zero-amount filings are supported by `fill_principal_zero`. For
  non-zero filings, fill the Formulario Principal manually after the MCP
  has created the draft.
- No retry on transient network errors — failures stop the batch so you can
  inspect.
- Two-factor / clave fiscal renewal is intentionally not automated.
- Quarterly SU-T filings (2007–2016) are scaffolded but not used in the
  default workflow.

## Validation Checklist

- `python -m enacom_mcp.scripts.make_tracker --help` returns 0 and prints
  argparse help.
- `python -m enacom_mcp.scripts.make_tracker --cuit ... --razon-social ...
  --tcfv 2023-01:2023-03 --output /tmp/t.xlsx` writes a 3-row tracker.
- `pytest tests/enacom_mcp/` is green (tracker, make_tracker round-trip,
  HertzConfig.from_env, selector-constants sanity, dom_report, and a
  server tool-registration smoke test).
- `python -m enacom_mcp` boots the server (it will exit on missing
  `ENACOM_TRACKER_PATH` — set it to the test tracker for a smoke test).
- With a real Hertz session: `submit_one` in dry-run leaves the browser at a
  visible draft for manual review.

## Maintenance Notes

When changing behavior or flags, update:

- This doc.
- `enacom_mcp/.env.example` if env vars change.
- `enacom_mcp/README.md` for tool list / install steps.
- `tests/enacom_mcp/` (test_tracker, test_make_tracker, test_config,
  test_selectors, test_dom_report, test_server_smoke) for schema, config,
  selector, or tool-surface changes.
- `selectors.py` whenever ENACOM revises the Hertz UI; document the change in
  the file's docstring.
