from __future__ import annotations

import re

from config import Config

# OCC option symbol format: 21 characters — e.g. AAPL  240119C00185000
# Also catches common shorthand: AAPL240119C00185000
_OCC_PATTERN = re.compile(
    r"""
    ^
    [A-Z]{1,6}          # underlying ticker (1-6 chars)
    \s*                 # optional padding (OCC pads to 6)
    \d{6}               # expiration YYMMDD
    [CP]                # call or put
    \d{8}               # strike * 1000 (8 digits)
    $
    """,
    re.VERBOSE,
)


def check_options_symbol(symbol: str) -> dict | None:
    """
    Return a blocked error dict if symbol looks like an options contract.
    Returns None if the symbol is clear.
    """
    s = symbol.strip().upper()

    # OCC format check
    if _OCC_PATTERN.match(s):
        return _options_blocked()

    # Colon separator (e.g. "AAPL:240119C185")
    if ":" in s:
        return _options_blocked()

    # Short-form suffix: digit immediately followed by C or P at end
    # e.g. "AAPL185C", "SPY450P"
    if re.search(r"\d[CP]$", s):
        return _options_blocked()

    return None


def check_order_value(estimated_value: float, cfg: Config) -> dict | None:
    """
    Return a blocked error dict if estimated order value exceeds the configured max.
    Returns None if the value is within limits.
    """
    if estimated_value > cfg.max_order_value_usd:
        return {
            "status": "blocked",
            "reason": (
                f"Estimated order value ${estimated_value:,.2f} exceeds the configured "
                f"maximum of ${cfg.max_order_value_usd:,.2f}. "
                f"Adjust max_order_value_usd in ~/.robinhood/config.toml to increase this limit."
            ),
        }
    return None


def _options_blocked() -> dict:
    return {
        "status": "blocked",
        "reason": (
            "Options trading is not supported by this MCP server. "
            "Please use the Robinhood app directly to trade options."
        ),
    }
