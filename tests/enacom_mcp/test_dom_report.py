"""Tests for the pure-Python DOM selector-candidate report (no browser needed)."""
from enacom_mcp.dom_report import summarize_interactive_elements, suggest_locator

SAMPLE = """
<html><body>
  <button id="save" class="btn primary">Guardar</button>
  <a href="/dj">DECLARACIONES JURADAS</a>
  <input name="anio" type="text" placeholder="Año"/>
  <select name="servicio"><option>TCFV</option></select>
  <textarea aria-label="Fundamento"></textarea>
  <button data-testid="enviar-btn">Enviar</button>
  <span>ignored</span>
</body></html>
"""


def test_counts_and_grouping():
    r = summarize_interactive_elements(SAMPLE)
    assert r["counts"] == {"button": 2, "a": 1, "input": 1, "select": 1, "textarea": 1}
    assert len(r["buttons"]) == 2
    assert len(r["links"]) == 1
    assert len(r["inputs"]) == 1
    assert len(r["selects"]) == 1
    assert len(r["textareas"]) == 1


def test_button_text_captured():
    r = summarize_interactive_elements(SAMPLE)
    texts = {b["text"] for b in r["buttons"]}
    assert texts == {"Guardar", "Enviar"}


def test_suggest_locator_prefers_testid():
    el = {"tag": "button", "text": "Enviar", "attrs": {"data-testid": "enviar-btn"}}
    assert suggest_locator(el) == 'get_by_test_id("enviar-btn")'


def test_suggest_locator_role_for_button():
    el = {"tag": "button", "text": "Guardar", "attrs": {}}
    assert suggest_locator(el) == 'get_by_role("button", name="Guardar")'


def test_suggest_locator_role_for_link():
    el = {"tag": "a", "text": "DECLARACIONES JURADAS", "attrs": {"href": "/dj"}}
    assert suggest_locator(el) == 'get_by_role("link", name="DECLARACIONES JURADAS")'


def test_suggest_locator_input_by_name():
    el = {"tag": "input", "text": "", "attrs": {"name": "anio", "type": "text"}}
    assert suggest_locator(el) == "locator(\"input[name='anio']\")"


def test_suggest_locator_textarea_by_label():
    el = {"tag": "textarea", "text": "", "attrs": {"aria-label": "Fundamento"}}
    assert suggest_locator(el) == 'get_by_label("Fundamento")'


def test_empty_html_is_safe():
    r = summarize_interactive_elements("")
    assert r["counts"] == {}
    assert r["buttons"] == []


def test_every_element_has_a_suggestion():
    r = summarize_interactive_elements(SAMPLE)
    for grp in ("buttons", "links", "inputs", "selects", "textareas"):
        for el in r[grp]:
            assert el["suggested"], f"missing suggestion for {el}"
