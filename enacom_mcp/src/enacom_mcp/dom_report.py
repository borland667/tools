"""Pure-Python helpers for turning a page's HTML into a selector-candidate report.

The Hertz portal is gated behind AFIP clave fiscal, so its DOM is unknown until
you log in. `hertz_dump_dom()` calls into here to produce a compact inventory of
the interactive elements on the current page (buttons, links, inputs, selects),
including the attributes you actually need to write robust Playwright locators
(accessible name / visible text, id, name, type, role, placeholder).

This module has NO Playwright dependency and operates on an HTML string, so it
is fully unit-testable without a browser.
"""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

INTERACTIVE_TAGS = {"button", "a", "input", "select", "textarea"}
# Attributes worth capturing for building locators.
KEEP_ATTRS = (
    "id", "name", "type", "role", "placeholder", "value",
    "aria-label", "title", "href", "data-testid", "class",
)


class _InteractiveParser(HTMLParser):
    """Collect interactive elements and their visible text from an HTML string."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in INTERACTIVE_TAGS:
            return
        attr_map = {k: (v or "") for k, v in attrs}
        el: dict[str, Any] = {
            "tag": tag,
            "text": "",
            "attrs": {k: attr_map[k] for k in KEEP_ATTRS if k in attr_map},
        }
        # Void elements (input) have no closing tag / inner text.
        if tag in {"input"}:
            self.elements.append(el)
        else:
            self._stack.append(el)

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        if self._stack[-1]["tag"] == tag:
            el = self._stack.pop()
            el["text"] = " ".join(el["text"].split()).strip()
            self.elements.append(el)

    def handle_data(self, data: str) -> None:
        if self._stack and data.strip():
            self._stack[-1]["text"] += data


def summarize_interactive_elements(html: str) -> dict[str, Any]:
    """Return a compact inventory of interactive elements grouped by tag.

    Output shape:
        {
          "counts": {"button": 3, "a": 5, ...},
          "buttons": [{"text": "Guardar", "attrs": {...}}, ...],
          "links":   [...],
          "inputs":  [...],
          "selects": [...],
          "textareas": [...],
        }
    Each element keeps only locator-relevant attributes (see KEEP_ATTRS) plus a
    suggested Playwright locator string in "suggested".
    """
    parser = _InteractiveParser()
    parser.feed(html or "")

    groups: dict[str, list[dict[str, Any]]] = {
        "buttons": [], "links": [], "inputs": [], "selects": [], "textareas": [],
    }
    tag_to_group = {
        "button": "buttons", "a": "links", "input": "inputs",
        "select": "selects", "textarea": "textareas",
    }
    counts: dict[str, int] = {}
    for el in parser.elements:
        counts[el["tag"]] = counts.get(el["tag"], 0) + 1
        el["suggested"] = suggest_locator(el)
        groups[tag_to_group[el["tag"]]].append(el)

    return {"counts": counts, **groups}


def suggest_locator(el: dict[str, Any]) -> str:
    """Suggest the most robust Playwright locator string for an element.

    Preference order: accessible name (role) > label-ish attrs > id > name >
    placeholder > raw text. Returns a Python expression string the user can
    paste, e.g. `get_by_role("button", name="Guardar")`.
    """
    tag = el.get("tag", "")
    attrs = el.get("attrs", {})
    text = (el.get("text") or "").strip()
    aria = attrs.get("aria-label", "").strip()
    _id = attrs.get("id", "").strip()
    name = attrs.get("name", "").strip()
    placeholder = attrs.get("placeholder", "").strip()
    testid = attrs.get("data-testid", "").strip()

    if testid:
        return f'get_by_test_id("{testid}")'

    role = {"button": "button", "a": "link"}.get(tag)
    accessible = aria or text
    if role and accessible:
        return f'get_by_role("{role}", name="{accessible}")'

    if tag in {"input", "textarea", "select"}:
        if aria:
            return f'get_by_label("{aria}")'
        if _id:
            return f'locator("#{_id}")'
        if name:
            return f'locator("{tag}[name=\'{name}\']")'
        if placeholder:
            return f'get_by_placeholder("{placeholder}")'

    if _id:
        return f'locator("#{_id}")'
    if accessible:
        return f'get_by_text("{accessible}")'
    return f'locator("{tag}")'
