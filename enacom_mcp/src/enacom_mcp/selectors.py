"""Hertz portal CSS / role selectors.

⚠️  ADJUSTMENT REQUIRED ON FIRST USE.

The Portal Hertz UI is not public. The selectors below were inferred from
ENACOM's official "Guía rápida para la carga de DDJJ" (mayo 2025) and are
**likely wrong in the exact attribute names**. On your first session,
open the browser DevTools (F12) on each page and verify each selector.

Recommended approach:
  1. Run the MCP with ENACOM_HEADED=true and ENACOM_DRY_RUN=true
  2. Walk through one DDJJ end-to-end with `submit_one()` while watching
  3. When a step fails, inspect the DOM in DevTools, paste the corrected
     selector here, and re-run.

Each selector is a `Locator`-friendly string. Prefer Playwright's
`page.get_by_role()` / `page.get_by_label()` where possible — they are far
more resilient to CSS class churn than raw `.css-xyz` selectors.
"""
from __future__ import annotations

# ---------- Login & navigation ----------
TAD_URL = "https://tramitesadistancia.gob.ar"
HERTZ_HOME_HINT = "Portal Hertz"  # text expected on Hertz landing page
TAD_LOGIN_AFIP_BUTTON = "text=AFIP con tu clave fiscal"
TAD_TRAMITE_SEARCH_INPUT = "input[type='search']"
TAD_TRAMITE_NAME = "Declaraciones juradas TCFV/SU – HERTZ"

# Profile picker (when user has multiple Hertz profiles)
HERTZ_PROFILE_DROPDOWN = "select[name*='perfil']"  # TODO verify
HERTZ_PROFILE_INGRESAR_BTN = "button:has-text('Ingresar')"

# Workspace navigation
HERTZ_CARPETAS_TECNICAS_BTN = "text=Carpetas Técnicas"
HERTZ_DECLARACIONES_JURADAS_LINK = "a:has-text('DECLARACIONES JURADAS')"  # TODO verify casing/element

# ---------- DDJJ list tabs ----------
TAB_INICIADAS = "text=DDJJ Iniciadas (No Enviadas)"
TAB_ENVIADAS_PENDIENTE = "text=DDJJ Enviadas (Pendiente de validación)"
TAB_ENVIADAS_VALIDADAS = "text=DDJJ Enviadas (Validadas)"
TAB_FINALIZADAS = "text=DDJJ Finalizadas"
TAB_RECHAZADAS = "text=DDJJ Rechazadas"

NEW_DDJJ_BUTTON = "button:has-text('+ Nueva DDJJ')"

# ---------- Datos Generales form ----------
# After clicking "+ Nueva DDJJ" the system creates a draft and assigns
# the Carpeta Técnica number. We need to capture it.
DATOS_GENERALES_NUMERO_FIELD = "input[name='numero']"  # TODO verify name

DATOS_GENERALES_SERVICIO_SELECT = "select[name='servicio']"  # TODO verify
DATOS_GENERALES_PERIODICIDAD_SELECT = "select[name='periodicidad']"
DATOS_GENERALES_PERIODO_SELECT = "select[name='periodo']"
DATOS_GENERALES_ANIO_INPUT = "input[name='anio']"
DATOS_GENERALES_TIPO_DDJJ_SELECT = "select[name='tipoDDJJ']"
DATOS_GENERALES_FUNDAMENTO_TEXTAREA = "textarea[name='fundamento']"

DATOS_GENERALES_GUARDAR_BTN = "button:has-text('Guardar')"
DATOS_GENERALES_FORMULARIOS_BTN = "button:has-text('Formularios')"
DATOS_GENERALES_ENVIAR_BTN = "button:has-text('Enviar')"
DATOS_GENERALES_CARPETA_TECNICA_BTN = "button:has-text('Carpeta Técnica')"

# Selector option values per ENACOM guide:
SERVICIO_OPTIONS = {
    "TCFV": "TCFV - Tasa de Control, Fiscalización y Verificación",
    "SU-M": "SU-M - Servicio Universal RES 6981/16 (MENSUAL)",
    "SU-T": "SU-T - Servicio Universal RES 154/10 (TRIMESTRAL)",
}
PERIODICIDAD_MENSUAL = "Mensual"
TIPO_DDJJ_ORIGINAL = "Original"
PERIODO_OPTIONS = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

# ---------- Formulario principal DDJJ ----------
FORM_PRINCIPAL_TAB = "text=Formulario principal DDJJ"
FORM_PRINCIPAL_NUEVO_BTN = "button:has-text('+ Nuevo Formulario')"
FORM_PRINCIPAL_VER_DETALLES = "text=Ver Detalles"

# Numeric fields on the principal form (cargar todo en cero)
FORM_PRINCIPAL_FIELDS = {
    "ingresos_devengados": "input[name='ingresosDevengados']",  # TODO verify
    "deducciones_admitidas": "input[name='deduccionesAdmitidas']",
    "base_sujeta_tasa": "input[name='baseSujetaTasa']",
    "monto_tasa": "input[name='montoTasa']",
    "otros_pagos": "input[name='otrosPagos']",
    "saldo_favor_anteriores": "input[name='saldoFavorAnteriores']",
    "total_ingresar": "input[name='totalIngresar']",
    "saldo_favor_proximos": "input[name='saldoFavorProximos']",
}

FORM_PRINCIPAL_GUARDAR = "button:has-text('Guardar')"
FORM_PRINCIPAL_CERRAR = "button:has-text('Cerrar')"

# ---------- Confirm / Enviar ----------
CONFIRM_ENVIAR_DIALOG = "[role='dialog'] button:has-text('Confirmar')"
SUCCESS_TOAST = "[role='status']"

# ---------- Export "DJ FINALIZADAS" ----------
EXPORT_BUTTON = "button:has-text('Exportar')"
