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

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from . import selectors as S

log = logging.getLogger("enacom_mcp.hertz")


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

    # ---------- session lifecycle ----------
    def start(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=not self.cfg.headed)
        ctx_kwargs = {}
        if self.cfg.storage_state and self.cfg.storage_state.exists():
            ctx_kwargs["storage_state"] = str(self.cfg.storage_state)
        self._ctx = self._browser.new_context(**ctx_kwargs)
        self._page = self._ctx.new_page()
        log.info("Playwright session started (headed=%s)", self.cfg.headed)

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
        if not self._page:
            raise RuntimeError("Session not started. Call start() first.")
        return self._page

    # ---------- navigation ----------
    def open_tad_and_wait_login(self, timeout_seconds: int = 300) -> None:
        """Open TAD and pause for the user to complete login + 2FA manually.

        The user logs in with AFIP clave fiscal in the visible browser window,
        navigates to "Declaraciones juradas TCFV/SU – HERTZ", and the
        automation resumes once the Hertz home is detected.
        """
        page = self.page
        page.goto(S.TAD_URL)
        log.info("Waiting up to %ds for you to log in and reach Hertz...", timeout_seconds)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if S.HERTZ_HOME_HINT.lower() in page.content().lower():
                log.info("Detected Hertz portal — automation resumes.")
                return
            time.sleep(2)
        raise TimeoutError("Hertz home not detected within timeout.")

    def select_profile(self) -> None:
        """If multiple profiles, pick the Representante DDJJ profile."""
        page = self.page
        try:
            page.locator(S.HERTZ_PROFILE_INGRESAR_BTN).click(timeout=10_000)
        except Exception as e:
            log.warning("Could not click 'Ingresar' (selector=%s): %s",
                        S.HERTZ_PROFILE_INGRESAR_BTN, e)
            self._snap("select_profile_failed")
            raise

    def open_declaraciones_juradas(self) -> None:
        page = self.page
        page.locator(S.HERTZ_CARPETAS_TECNICAS_BTN).click()
        page.locator(S.HERTZ_DECLARACIONES_JURADAS_LINK).click()
        self._snap("dj_workspace")

    # ---------- DDJJ creation ----------
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
        page.locator(S.TAB_INICIADAS).click()
        page.locator(S.NEW_DDJJ_BUTTON).click()

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
        page.locator(S.DATOS_GENERALES_GUARDAR_BTN).click()
        self._snap(f"datos_generales_{carpeta}")
        return carpeta

    def fill_principal_zero(self) -> None:
        """Open Formulario Principal and fill all numeric fields with 0."""
        page = self.page
        page.locator(S.DATOS_GENERALES_FORMULARIOS_BTN).click()
        page.locator(S.FORM_PRINCIPAL_TAB).click()
        page.locator(S.FORM_PRINCIPAL_NUEVO_BTN).click()
        page.locator(S.FORM_PRINCIPAL_VER_DETALLES).click()
        for field, sel in S.FORM_PRINCIPAL_FIELDS.items():
            page.locator(sel).fill("0")
        page.locator(S.FORM_PRINCIPAL_GUARDAR).click()
        page.locator(S.FORM_PRINCIPAL_CERRAR).click()
        self._snap("formulario_principal_cero")

    def submit_ddjj(self) -> None:
        """Click 'Enviar'. Skipped when dry_run=True."""
        page = self.page
        page.locator(S.DATOS_GENERALES_CARPETA_TECNICA_BTN).click()
        if self.cfg.dry_run:
            log.warning("DRY RUN — skipping final 'Enviar' click. Review the draft visually.")
            self._snap("dry_run_before_enviar")
            return
        page.locator(S.DATOS_GENERALES_ENVIAR_BTN).click()
        try:
            page.locator(S.CONFIRM_ENVIAR_DIALOG).click(timeout=5_000)
        except Exception:
            pass
        page.wait_for_selector(S.SUCCESS_TOAST, timeout=15_000)
        self._snap("submitted")

    # ---------- helpers ----------
    def _snap(self, label: str) -> None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = self.cfg.artifacts_dir / f"{ts}_{label}.png"
        try:
            self.page.screenshot(path=str(path), full_page=True)
            log.info("📸 %s", path.name)
        except Exception as e:
            log.warning("Screenshot failed: %s", e)
