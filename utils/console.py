"""Windows-safe console output with ASCII fallbacks for Unicode symbols."""

import sys
import os


def _supports_unicode() -> bool:
    """Check if the current terminal supports Unicode output."""
    if os.name == "nt":
        # Windows: check if the console code page supports UTF-8
        try:
            "".encode(sys.stdout.encoding or "ascii")
            # Try encoding common symbols
            "\u2713\u2717\u25cb".encode(sys.stdout.encoding or "ascii")
            return True
        except (UnicodeEncodeError, LookupError):
            return False
    return True


# Configure stdout for UTF-8 on Windows
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

USE_UNICODE = _supports_unicode()

# Symbol mappings
CHECK = "\u2713" if USE_UNICODE else "[+]"
CROSS = "\u2717" if USE_UNICODE else "[-]"
CIRCLE = "\u25cb" if USE_UNICODE else "[o]"
ARROW_UP = "\u2191" if USE_UNICODE else "^"
ARROW_DOWN = "\u2193" if USE_UNICODE else "v"
BULLET = "\u2022" if USE_UNICODE else "*"
STAR = "\u2605" if USE_UNICODE else "*"


def ok(msg: str) -> str:
    return f"{CHECK} {msg}"


def fail(msg: str) -> str:
    return f"{CROSS} {msg}"


def neutral(msg: str) -> str:
    return f"{CIRCLE} {msg}"


def header(title: str, width: int = 60) -> str:
    return f"\n{'=' * width}\n{title}\n{'=' * width}"


def separator(width: int = 60) -> str:
    return "-" * width
