from __future__ import annotations

import logging
from typing import Any

import robin_stocks.robinhood as rh

logger = logging.getLogger(__name__)

# Known crypto base symbols supported by Robinhood.
# Used to short-circuit the asset-type resolution without an extra API round-trip.
_KNOWN_CRYPTO = {
    "BTC", "ETH", "DOGE", "SHIB", "LTC", "BCH", "ETC",
    "BSV", "XLM", "MATIC", "LINK", "UNI", "AAVE", "SOL",
    "ADA", "AVAX", "XTZ",
}


def resolve_asset_type(symbol: str) -> str | None:
    """
    Return 'equity', 'crypto', or None if symbol cannot be resolved.
    Checks the known-crypto list first to avoid unnecessary API calls.
    """
    s = symbol.upper().strip()
    if s in _KNOWN_CRYPTO:
        return "crypto"

    # Try equity lookup.
    try:
        result = rh.stocks.get_stock_quote_by_symbol(s)
        if result and isinstance(result, dict) and result.get("symbol"):
            return "equity"
    except Exception:
        pass

    # Try crypto lookup.
    try:
        result = rh.crypto.get_crypto_quote(s)
        if result and isinstance(result, dict) and result.get("symbol"):
            return "crypto"
    except Exception:
        pass

    return None


def get_quote(symbol: str) -> dict[str, Any]:
    """
    Return a normalized quote dict for an equity or crypto symbol.
    Raises ValueError if symbol cannot be resolved.
    """
    s = symbol.upper().strip()
    asset_type = resolve_asset_type(s)

    if asset_type == "equity":
        return _equity_quote(s)
    elif asset_type == "crypto":
        return _crypto_quote(s)
    else:
        raise ValueError(f"Symbol '{symbol}' not found as equity or crypto on Robinhood.")


def _equity_quote(symbol: str) -> dict[str, Any]:
    raw = rh.stocks.get_stock_quote_by_symbol(symbol)
    if not raw or not isinstance(raw, dict):
        raise ValueError(f"No equity quote returned for '{symbol}'")

    fundamentals = _safe_fundamentals(symbol)

    return {
        "symbol": symbol,
        "asset_type": "equity",
        "bid_price": _float(raw.get("bid_price")),
        "ask_price": _float(raw.get("ask_price")),
        "last_trade_price": _float(raw.get("last_trade_price")),
        "last_extended_hours_trade_price": _float(raw.get("last_extended_hours_trade_price")),
        "previous_close": _float(raw.get("previous_close")),
        "adjusted_previous_close": _float(raw.get("adjusted_previous_close")),
        "open": _float(raw.get("open")),
        "high": _float(fundamentals.get("high") if fundamentals else None),
        "low": _float(fundamentals.get("low") if fundamentals else None),
        "volume": _float(fundamentals.get("volume") if fundamentals else None),
        "market_cap": _float(fundamentals.get("market_cap") if fundamentals else None),
        "trading_halted": raw.get("trading_halted", False),
    }


def _crypto_quote(symbol: str) -> dict[str, Any]:
    raw = rh.crypto.get_crypto_quote(symbol)
    if not raw or not isinstance(raw, dict):
        raise ValueError(f"No crypto quote returned for '{symbol}'")

    return {
        "symbol": symbol,
        "asset_type": "crypto",
        "bid_price": _float(raw.get("bid_price")),
        "ask_price": _float(raw.get("ask_price")),
        "last_trade_price": _float(raw.get("mark_price") or raw.get("last_trade_price")),
        "last_extended_hours_trade_price": None,
        "previous_close": _float(raw.get("open_price")),
        "adjusted_previous_close": None,
        "open": _float(raw.get("open_price")),
        "high": _float(raw.get("high_price")),
        "low": _float(raw.get("low_price")),
        "volume": _float(raw.get("volume")),
        "market_cap": None,
        "trading_halted": False,
    }


def get_last_trade_price(symbol: str, asset_type: str | None = None) -> float | None:
    """Convenience function for orders.py to get estimated price."""
    try:
        s = symbol.upper()
        if asset_type == "equity" or (asset_type is None and s not in _KNOWN_CRYPTO):
            raw = rh.stocks.get_stock_quote_by_symbol(s)
            if raw and isinstance(raw, dict):
                return _float(raw.get("last_trade_price"))
        raw = rh.crypto.get_crypto_quote(s)
        if raw and isinstance(raw, dict):
            return _float(raw.get("mark_price") or raw.get("last_trade_price"))
    except Exception as exc:
        logger.debug("get_last_trade_price failed for %s: %s", symbol, exc)
    return None


def _safe_fundamentals(symbol: str) -> dict | None:
    try:
        result = rh.stocks.get_fundamentals(symbol)
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        if result and isinstance(result, dict):
            return result
    except Exception:
        pass
    return None


def _float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
