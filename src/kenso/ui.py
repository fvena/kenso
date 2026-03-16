"""Terminal output helpers — zero external dependencies.

Provides ANSI styling, Unicode glyphs, and smart TTY detection.
All output goes through :func:`output` which strips ANSI when
stdout is not a terminal.
"""

from __future__ import annotations

import os
import re
import sys

__all__ = [
    "Style",
    "glyph",
    "supports_color",
    "output",
    "header",
    "ok",
    "fail",
    "warn",
    "info",
    "summary",
    "next_step",
    "detail",
    "terminal_snippet",
]

# ── ANSI codes ─────────────────────────────────────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class Style:
    """ANSI escape sequences for terminal styling."""

    RESET = "\x1b[0m"
    BOLD = "\x1b[1m"
    DIM = "\x1b[2m"

    # Foreground colours
    RED = "\x1b[31m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    BLUE = "\x1b[34m"
    MAGENTA = "\x1b[35m"
    CYAN = "\x1b[36m"
    WHITE = "\x1b[37m"
    GRAY = "\x1b[90m"

    # Brand colour (cyan for "kenso ·")
    BRAND = "\x1b[36m"


# ── Glyphs ─────────────────────────────────────────────────────────

glyph = {
    "ok": "\u2713",  # ✓
    "fail": "\u2717",  # ✗
    "warn": "\u25b2",  # ▲
    "skip": "\u2298",  # ⊘
    "dash": "\u2013",  # –
    "removed": "\u2715",  # ✕
    "dot": "\u00b7",  # ·
    "arrow": "\u2192",  # →
    "tree_mid": "\u251c\u2500",  # ├─
    "tree_end": "\u2514\u2500",  # └─
    "tree_pipe": "\u2502 ",  # │
    "rule": "\u2500",  # ─
}


# ── TTY / colour detection ────────────────────────────────────────


def supports_color() -> bool:
    """Return True when stdout is a TTY that likely supports colour."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from *text*."""
    return _ANSI_RE.sub("", text)


# ── Core output ────────────────────────────────────────────────────

_color: bool | None = None


def _use_color() -> bool:
    global _color
    if _color is None:
        _color = supports_color()
    return _color


def output(text: str = "", **kwargs) -> None:
    """Print *text*, stripping ANSI when stdout is not a TTY."""
    if not _use_color():
        text = strip_ansi(text)
    print(text, **kwargs)


def _styled(style: str, text: str) -> str:
    """Wrap *text* in an ANSI style sequence."""
    return f"{style}{text}{Style.RESET}"


# ── Header ─────────────────────────────────────────────────────────


def header(context: str, *, db_path: str | None = None) -> None:
    """Print the branded header line: ``kenso · {context}``."""
    line = f"{_styled(Style.BRAND + Style.BOLD, 'kenso')} {glyph['dot']} {context}"
    if db_path:
        line += f" {_styled(Style.DIM, f'(db: {db_path})')}"
    output(line)


# ── Status helpers ─────────────────────────────────────────────────


def ok(msg: str) -> None:
    output(f"{_styled(Style.GREEN, glyph['ok'])} {msg}")


def fail(msg: str) -> None:
    output(f"{_styled(Style.RED, glyph['fail'])} {msg}")


def warn(msg: str) -> None:
    output(f"{_styled(Style.YELLOW, glyph['warn'])} {msg}")


def info(msg: str) -> None:
    output(f"{_styled(Style.BLUE, 'i')} {msg}")


def summary(msg: str) -> None:
    output(f"{_styled(Style.BOLD, msg)}")


def next_step(cmd: str) -> None:
    output(f"Next {glyph['arrow']} {_styled(Style.BOLD, cmd)}")


def detail(msg: str) -> None:
    output(f"  {_styled(Style.DIM, msg)}")


# ── Snippet rendering ─────────────────────────────────────────────

_MARK_RE = re.compile(r"<mark>(.*?)</mark>")


def terminal_snippet(snippet: str) -> str:
    """Replace ``<mark>text</mark>`` with ANSI bold for terminal display."""
    return _MARK_RE.sub(rf"{Style.BOLD}\1{Style.RESET}", snippet)


# ── Colour helpers for search labels ──────────────────────────────


def cascade_label(stage: str) -> str:
    """Return a coloured cascade-stage label (AND/NEAR/OR)."""
    colors = {"AND": Style.GREEN, "NEAR": Style.BLUE, "OR": Style.YELLOW}
    color = colors.get(stage.upper(), "")
    return _styled(color + Style.BOLD, stage.upper()) if color else stage


def relevance_label(level: str) -> str:
    """Return a coloured relevance label (high/medium/low)."""
    colors = {"high": Style.GREEN, "medium": Style.YELLOW, "low": Style.RED}
    color = colors.get(level.lower(), "")
    return _styled(color, level.lower()) if color else level


# ── Formatting utilities ──────────────────────────────────────────


def human_size(n: int) -> str:
    """Format byte count as human-readable string."""
    if n < 1024:
        return f"{n} B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    else:
        return f"{n / (1024 * 1024):.1f} MB"


def rule_line(width: int = 55) -> str:
    """Return a horizontal rule of the given width."""
    return glyph["rule"] * width


def severity_glyph(severity: str) -> str:
    """Return the appropriate glyph for a lint severity level."""
    return {
        "error": _styled(Style.RED, glyph["fail"]),
        "warning": _styled(Style.YELLOW, glyph["warn"]),
        "info": _styled(Style.BLUE, "i"),
    }.get(severity, " ")
