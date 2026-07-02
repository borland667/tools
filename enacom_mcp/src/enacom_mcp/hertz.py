"""Playwright client that drives Portal Hertz.

⚠️  IMPORTANT — Read this before running:

  • Hertz is accessed only through TAD with your AFIP clave fiscal. The MCP
    cannot log in for you (and shouldn't — never give it your password).
    `start_session()` opens a real browser; you log in manually; then the
    automation takes over for the form filling.

  • A DDJJ is a sworn declaration. Even though we automate the click-through,
    you remain legally responsible. Run with ENACOM_DRY_RUN=true at first
    and visually check each draft before flipping the switch.

  • The selectors in `selectors.py` are inferred from ENACOM's official PDF
    guide and will need adjustment on first use. Each method below logs the
    selector it tried so failures are easy to fix.
"""
from __future__ import annotations

import concurrent.futures
import functools
import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from . import dom_report
from . import selectors as S

log = logging.getLogger("enacom_mcp.hertz")


def _on_pw_thread(method):
    """Dispatch the wrapped method to the HertzClient's Playwright worker thread.

    Playwright's sync API refuses to run inside an asyncio event loop and
    requires its objects to be used from the same thread that created them.
    The MCP server runs tool handlers under FastMCP's event loop, so all
    browser interaction is routed through a dedicated single-thread executor.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        return self._executor.submit(method, self, *args, **kwargs).result()
    return wrapper


@dataclass
class HertzConfig:
    headed: bool = True
    dry_run: bool = True
    artifacts_dir: Path = Path("./artifacts")
    storage_state: Path | None = None
    cuit: str = ""
    razon_social: str = ""
    fundamento: str = ""

    @classmethod
    def from_env(cls) -> "HertzConfig":
        return cls(
            headed=os.getenv("ENACOM_HEADED", "true").lower() == "true",
            dry_run=os.getenv("ENACOM_DRY_RUN", "true").lower() == "true",
            artifacts_dir=Path(os.getenv("ENACOM_ARTIFACTS_DIR", "./artifacts")),
            storage_state=Path(os.getenv("ENACOM_STORAGE_STATE")) if os.getenv("ENACOM_STORAGE_STATE") else None,
            cuit=os.getenv("ENACOM_CUIT", ""),
            razon_social=os.getenv("ENACOM_RAZON_SOCIAL", ""),
            fundamento=os.getenv("ENACOM_FUNDAMENTO", ""),
        )


class HertzClient:
    """Wraps a single Playwright session against Hertz."""

    def __init__(self, cfg: HertzConfig | None = None):
        self.cfg = cfg or HertzConfig.from_env()
        self.cfg.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._pw = None
        self._browser: Browser | None = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="hertz-pw"
        )

    # ---------- session lifecycle ----------
    @_on_pw_thread
    def start(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=not self.cfg.headed)
        ctx_kwargs = {}
        if self.cfg.storage_state and self.cfg.storage_state.exists():
            ctx_kwargs["storage_state"] = str(self.cfg.storage_state)
        self._ctx = self._browser.new_context(**ctx_kwargs)
        self._page = self._ctx.new_page()
        log.info("Playwright session started (headed=%s)", self.cfg.headed)

    @_on_pw_thread
    def stop(self) -> None:
        try:
            if self._ctx and self.cfg.storage_state:
                self._ctx.storage_state(path=str(self.cfg.storage_state))
        finally:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
            self._page = None
            self._ctx = None
            self._browser = None

    @contextmanager
    def session(self) -> Iterator["HertzClient"]:
        self.start()
        try:
            yield self
        finally:
            self.stop()

    @property
    def page(self) -> Page:
        """Return the Page the automation should operate on.

        TAD opens the Hertz portal in a new tab when the user clicks
        "Iniciar Trámite", so we auto-prefer a tab on hertz.enacom.gob.ar
        when one exists in the BrowserContext. Falls back to the initial
        tab during pre-login navigation (TAD home, AFIP, etc.).
        """
        if not self._ctx:
            raise RuntimeError("Session not started. Call start() first.")
        for pg in self._ctx.pages:
            if "hertz.enacom.gob.ar" in pg.url:
                return pg
        if self._page is None:
            raise RuntimeError("Session has no pages. Call start() first.")
        return self._page

    # ---------- navigation ----------
    @_on_pw_thread
    def open_tad_and_wait_login(self, timeout_seconds: int = 300) -> None:
        """Open TAD and pause for the user to complete login + 2FA manually.

        The user logs in with AFIP clave fiscal in the visible browser window,
        navigates to "Declaraciones juradas TCFV/SU – HERTZ", and the
        automation resumes once the Hertz home is detected.
        """
        self.page.goto(S.TAD_URL)
        log.info("Waiting up to %ds for you to log in and reach Hertz...", timeout_seconds)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                # Re-resolve self.page each tick: TAD opens Hertz in a new
                # tab, and the page property auto-prefers that tab once it
                # exists. A captured reference would stay pinned to TAD.
                if S.HERTZ_HOME_HINT.lower() in self.page.content().lower():
                    log.info("Detected Hertz portal — automation resumes.")
                    return
            except Exception as e:
                # page.content() throws if called while the page is mid-navigation.
                # TAD→AFIP→Hertz redirects make this likely; just retry on next tick.
                log.debug("Hertz detection retry (page navigating): %s", e)
            time.sleep(2)
        raise TimeoutError("Hertz home not detected within timeout.")

    # ---------- non-blocking login (capture flow) ----------
    @_on_pw_thread
    def open_tad(self) -> None:
        """Navigate to TAD home and return immediately. No polling, no blocking."""
        self.page.goto(S.TAD_URL)

    @_on_pw_thread
    def current_url(self) -> str:
        """Return the browser's current page URL."""
        return self.page.url

    @_on_pw_thread
    def save_storage_state(self) -> str:
        """Persist the current session cookies/localStorage to the configured path.

        Used after a manual login to capture the AFIP+Hertz session so future
        runs can skip the login step. Does NOT close the browser.
        """
        if not self._ctx:
            raise RuntimeError("Session not started. Call hertz_login_open() first.")
        if not self.cfg.storage_state:
            raise RuntimeError(
                "ENACOM_STORAGE_STATE is not configured in .env; nothing to save to."
            )
        self.cfg.storage_state.parent.mkdir(parents=True, exist_ok=True)
        self._ctx.storage_state(path=str(self.cfg.storage_state))
        return str(self.cfg.storage_state)

    @_on_pw_thread
    def select_profile(self) -> None:
        """If multiple profiles, pick the Representante DDJJ profile.

        Single-profile accounts land directly on the Hertz home (no Ingresar
        button shown), so this is a graceful no-op when the button is absent.
        """
        page = self.page
        try:
            self._click(
                page, S.HERTZ_PROFILE_INGRESAR_BTN,
                role="button", name=S.NAME_INGRESAR, timeout=3_000,
            )
        except Exception:
            log.info(
                "No profile-picker 'Ingresar' button found — assuming "
                "single-profile account, continuing."
            )

    @_on_pw_thread
    def open_declaraciones_juradas(self) -> None:
        page = self.page
        self._click(page, S.HERTZ_CARPETAS_TECNICAS_BTN,
                    role="button", name=S.NAME_CARPETAS_TECNICAS)
        self._click(page, S.HERTZ_DECLARACIONES_JURADAS_LINK,
                    role="link", name=S.NAME_DECLARACIONES_JURADAS)
        self._snap("dj_workspace")

    # ---------- DDJJ creation ----------
    @_on_pw_thread
    def create_ddjj(
        self,
        *,
        servicio: str,
        anio: int,
        periodo_nombre: str,
        fundamento: str | None = None,
    ) -> str:
        """Create one DDJJ draft. Returns the Carpeta Técnica number.

        Steps:
          1. Click "+ Nueva DDJJ" on the "Iniciadas" tab
          2. Capture the Nº Carpeta Técnica
          3. Fill Datos Generales (servicio, periodicidad, periodo, año,
             tipo Original, fundamento)
          4. Save
        """
        page = self.page
        self._click(page, S.TAB_INICIADAS, role="tab", name=S.NAME_TAB_INICIADAS)
        self._click(page, S.NEW_DDJJ_BUTTON, role="button", name=S.NAME_NUEVA_DDJJ)

        carpeta = page.locator(S.DATOS_GENERALES_NUMERO_FIELD).input_value()
        log.info("Created draft Nº %s for %s %d-%s", carpeta, servicio, anio, periodo_nombre)

        # Servicio
        page.locator(S.DATOS_GENERALES_SERVICIO_SELECT).select_option(
            label=S.SERVICIO_OPTIONS[servicio]
        )
        # Periodicidad (only editable for TCFV; auto for SU-M/SU-T)
        if servicio == "TCFV":
            page.locator(S.DATOS_GENERALES_PERIODICIDAD_SELECT).select_option(
                label=S.PERIODICIDAD_MENSUAL
            )
        # Periodo + Año
        page.locator(S.DATOS_GENERALES_PERIODO_SELECT).select_option(label=periodo_nombre)
        page.locator(S.DATOS_GENERALES_ANIO_INPUT).fill(str(anio))
        # Tipo DDJJ
        page.locator(S.DATOS_GENERALES_TIPO_DDJJ_SELECT).select_option(label=S.TIPO_DDJJ_ORIGINAL)
        # Fundamento
        page.locator(S.DATOS_GENERALES_FUNDAMENTO_TEXTAREA).fill(
            fundamento or self.cfg.fundamento
        )
        # Save
        self._click(page, S.DATOS_GENERALES_GUARDAR_BTN, role="button", name=S.NAME_GUARDAR)
        self._snap(f"datos_generales_{carpeta}")
        return carpeta

    @_on_pw_thread
    def fill_principal_zero(self) -> None:
        """Open Formulario Principal and fill all numeric fields with 0."""
        page = self.page
        self._click(page, S.DATOS_GENERALES_FORMULARIOS_BTN, role="button", name=S.NAME_FORMULARIOS)
        self._click(page, S.FORM_PRINCIPAL_TAB, role="tab", name=S.NAME_FORM_PRINCIPAL_TAB)
        self._click(page, S.FORM_PRINCIPAL_NUEVO_BTN, role="button", name=S.NAME_NUEVO_FORMULARIO)
        self._click(page, S.FORM_PRINCIPAL_VER_DETALLES, role="button", name=S.NAME_VER_DETALLES)
        for field, sel in S.FORM_PRINCIPAL_FIELDS.items():
            page.locator(sel).fill("0")
        self._click(page, S.FORM_PRINCIPAL_GUARDAR, role="button", name=S.NAME_GUARDAR)
        self._click(page, S.FORM_PRINCIPAL_CERRAR, role="button", name=S.NAME_CERRAR)
        self._snap("formulario_principal_cero")

    @_on_pw_thread
    def submit_ddjj(self) -> None:
        """Click 'Enviar' to send the DDJJ.

        Only this final send is gated by dry_run. When dry_run=True the draft
        (already created and saved by create_ddjj/fill_principal_zero) is left
        in place and 'Enviar' is NOT clicked.
        """
        page = self.page
        self._click(page, S.DATOS_GENERALES_CARPETA_TECNICA_BTN,
                    role="button", name=S.NAME_CARPETA_TECNICA)
        if self.cfg.dry_run:
            log.warning("DRY RUN — skipping final 'Enviar' click. Review the draft visually.")
            self._snap("dry_run_before_enviar")
            return
        self._click(page, S.DATOS_GENERALES_ENVIAR_BTN, role="button", name=S.NAME_ENVIAR)
        try:
            self._click(page, S.CONFIRM_ENVIAR_DIALOG,
                        role="button", name=S.NAME_CONFIRMAR, timeout=5_000)
        except Exception:
            pass
        page.wait_for_selector(S.SUCCESS_TOAST, timeout=15_000)
        self._snap("submitted")

    # ---------- diagnostics ----------
    @_on_pw_thread
    def dump_dom(self, label: str = "dump") -> dict:
        """Capture the current page's DOM for selector bring-up.

        Writes three artifacts to ENACOM_ARTIFACTS_DIR:
          • {ts}_{label}.html            — full page HTML
          • {ts}_{label}.png             — full-page screenshot
          • {ts}_{label}_elements.json   — inventory of interactive elements
            (buttons/links/inputs/selects/textareas) with a suggested
            Playwright locator for each.

        Returns a summary dict (paths + element counts + current URL/title) so
        you can lock down real selectors on your first live login instead of
        guessing.
        """
        page = self.page
        ts = time.strftime("%Y%m%d-%H%M%S")
        base = self.cfg.artifacts_dir / f"{ts}_{label}"
        html = page.content()
        report = dom_report.summarize_interactive_elements(html)

        html_path = base.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        json_path = self.cfg.artifacts_dir / f"{ts}_{label}_elements.json"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        png_path = base.with_suffix(".png")
        try:
            page.screenshot(path=str(png_path), full_page=True)
        except Exception as e:
            log.warning("dump_dom screenshot failed: %s", e)
            png_path = None

        log.info("🧭 dump_dom wrote %s (%s)", html_path.name, report["counts"])
        return {
            "url": page.url,
            "title": page.title(),
            "counts": report["counts"],
            "html_path": str(html_path),
            "elements_json_path": str(json_path),
            "screenshot_path": str(png_path) if png_path else None,
        }

    # ---------- helpers ----------
    def _click(
        self,
        page: Page,
        css: str,
        *,
        role: str | None = None,
        name: str | None = None,
        timeout: int = 10_000,
    ) -> None:
        """Click an element, trying a role-based locator first, then CSS.

        Runs on the Playwright worker thread (call only from @_on_pw_thread
        methods). The role-based attempt (get_by_role(role, name=name)) is far
        more resilient to CSS churn; if it fails we fall back to the exact CSS
        selector so behavior never regresses. Raises the last error if both
        strategies fail.
        """
        last_err: Exception | None = None
        if role and name:
            try:
                page.get_by_role(role, name=name).first.click(timeout=timeout)
                log.info("clicked via role=%s name=%r", role, name)
                return
            except Exception as e:  # noqa: BLE001 - fall back to CSS
                last_err = e
                log.debug("role click failed (role=%s name=%r): %s", role, name, e)
        try:
            page.locator(css).first.click(timeout=timeout)
            log.info("clicked via css=%s", css)
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("click failed for css=%s (role=%s name=%r): %s", css, role, name, e)
        raise last_err if last_err else RuntimeError(f"click failed: {css}")

    def _snap(self, label: str) -> None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = self.cfg.artifacts_dir / f"{ts}_{label}.png"
        try:
            self.page.screenshot(path=str(path), full_page=True)
            log.info("📸 %s", path.name)
        except Exception as e:
            log.warning("Screenshot failed: %s", e)
