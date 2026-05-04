"""Jinja2 environment for transactional email rendering.

Templates live next to this file in `templates/`. Each template extends
`base.html` and provides a `{% block content %}`. The renderer returns
both an HTML body and a plain-text fallback (auto-stripped from HTML
when the template doesn't supply one).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    html: str
    plain: str


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _to_plain(html: str) -> str:
    """Cheap HTML → text fallback. Good enough for transactional mail —
    Gmail composes the multipart body either way.
    """
    no_tags = _HTML_TAG_RE.sub("", html)
    return _WS_RE.sub(" ", no_tags).strip()


def render(
    template_name: str,
    *,
    subject: str,
    context: dict[str, Any],
) -> RenderedEmail:
    """Render `<template_name>.html` with the given context."""
    template = _env().get_template(f"{template_name}.html")
    html = template.render(**context)
    return RenderedEmail(subject=subject, html=html, plain=_to_plain(html))
