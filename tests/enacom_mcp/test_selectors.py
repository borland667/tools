"""Sanity checks on the selector constants so obvious mistakes fail fast.

These cannot verify selectors against the live (auth-gated) portal, but they
catch structural regressions: empty constants, mismatched service maps, and
locator strings that don't look like locators.
"""
from enacom_mcp import selectors as S


def test_service_options_cover_tracker_services():
    # The tracker/make_tracker use these three service codes.
    assert set(S.SERVICIO_OPTIONS) == {"TCFV", "SU-M", "SU-T"}
    assert all(isinstance(v, str) and v for v in S.SERVICIO_OPTIONS.values())


def test_periodo_options_has_twelve_months():
    assert len(S.PERIODO_OPTIONS) == 12
    assert S.PERIODO_OPTIONS[0] == "Enero"
    assert S.PERIODO_OPTIONS[-1] == "Diciembre"


def test_form_principal_fields_are_nonempty_selectors():
    assert S.FORM_PRINCIPAL_FIELDS, "expected numeric form fields"
    for key, sel in S.FORM_PRINCIPAL_FIELDS.items():
        assert key and isinstance(sel, str) and sel.strip(), key


def test_role_name_constants_present_and_nonempty():
    # Every NAME_* constant used by HertzClient._click must be a non-empty str.
    name_consts = {k: v for k, v in vars(S).items() if k.startswith("NAME_")}
    assert name_consts, "expected NAME_* role constants"
    for k, v in name_consts.items():
        assert isinstance(v, str) and v.strip(), k


def test_tad_url_is_https():
    assert S.TAD_URL.startswith("https://")
