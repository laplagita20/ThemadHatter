"""Natural-language portfolio text parser.

Supports formats:
  AAPL 100
  AAPL 100 @ 150
  AAPL 100 @ 150.50
  AAPL 100, MSFT 50
  One entry per line
  Comma-separated on one line
"""

import re

_ENTRY_PATTERN = re.compile(
    r"([A-Za-z]{1,5})"           # ticker (1-5 alpha chars)
    r"\s+"                        # whitespace
    r"([\d,]+(?:\.\d+)?)"        # shares (with optional decimals/commas)
    r"(?:\s*@\s*\$?"             # optional: @ price
    r"([\d,]+(?:\.\d+)?))?"     # price value
)


def parse_portfolio_text(text: str) -> list[dict]:
    """Parse free-form portfolio text into a list of holdings.

    Returns list of dicts with keys: ticker, shares, cost (cost may be 0).
    """
    if not text or not text.strip():
        return []

    results = []
    seen = set()

    # Split on newlines and commas that separate entries (but not within numbers)
    # First split by newlines, then within each line try comma separation
    lines = text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try to find all matches in this line
        for match in _ENTRY_PATTERN.finditer(line):
            ticker = match.group(1).upper()
            shares_str = match.group(2).replace(",", "")
            cost_str = match.group(3)

            try:
                shares = float(shares_str)
            except ValueError:
                continue

            cost = 0.0
            if cost_str:
                try:
                    cost = float(cost_str.replace(",", ""))
                except ValueError:
                    pass

            if shares > 0 and ticker not in seen:
                seen.add(ticker)
                results.append({
                    "ticker": ticker,
                    "shares": shares,
                    "cost": cost,
                })

    return results
