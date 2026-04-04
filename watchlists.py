from __future__ import annotations

import logging
from typing import Any

import robin_stocks.robinhood as rh

import market_data

logger = logging.getLogger(__name__)


def get_watchlists() -> dict[str, Any]:
    """Return all watchlists with their symbol arrays."""
    try:
        raw = rh.account.get_all_watchlists()
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch watchlists: {exc}") from exc

    if not raw or not isinstance(raw, dict):
        return {"watchlists": []}

    results = raw.get("results", [])
    watchlists = []
    for item in results:
        name = item.get("display_name", item.get("name", "Unknown"))
        watchlists.append({
            "name": name,
            "count": item.get("count", 0),
        })

    return {"watchlists": watchlists, "count": len(watchlists)}


def get_watchlist(name: str) -> dict[str, Any]:
    """Return symbols and current quotes for a named watchlist."""
    try:
        raw = rh.account.get_watchlist_by_name(name)
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch watchlist '{name}': {exc}") from exc

    if not raw:
        raise ValueError(f"Watchlist '{name}' not found.")

    # raw is typically a list of instrument dicts or a paginated response.
    items: list[dict] = []
    if isinstance(raw, dict):
        items = raw.get("results", [])
    elif isinstance(raw, list):
        items = raw

    symbols_with_quotes = []
    for item in items:
        # The instrument URL contains the ticker; resolve it.
        symbol = item.get("symbol") or _resolve_instrument_symbol(item.get("instrument", ""))
        if not symbol:
            continue

        quote: dict | None = None
        try:
            quote = market_data.get_quote(symbol)
        except Exception as exc:
            logger.debug("Quote fetch failed for %s: %s", symbol, exc)

        entry: dict[str, Any] = {"symbol": symbol}
        if quote:
            entry["last_trade_price"] = quote.get("last_trade_price")
            entry["asset_type"] = quote.get("asset_type")
        symbols_with_quotes.append(entry)

    return {"name": name, "items": symbols_with_quotes, "count": len(symbols_with_quotes)}


def create_watchlist(name: str) -> dict[str, Any]:
    """Create a new empty watchlist."""
    try:
        result = rh.account.post_watchlist(name)
    except Exception as exc:
        raise RuntimeError(f"Failed to create watchlist '{name}': {exc}") from exc

    return {"status": "created", "name": name, "result": result}


def add_to_watchlist(name: str, symbol: str) -> dict[str, Any]:
    """Add a ticker symbol to a named watchlist."""
    symbol = symbol.upper()
    try:
        result = rh.account.add_to_watchlist(name, symbol)
    except Exception as exc:
        raise RuntimeError(f"Failed to add {symbol} to watchlist '{name}': {exc}") from exc

    return {"status": "added", "watchlist": name, "symbol": symbol, "result": result}


def remove_from_watchlist(name: str, symbol: str) -> dict[str, Any]:
    """Remove a symbol from a named watchlist."""
    symbol = symbol.upper()
    try:
        result = rh.account.delete_symbol_from_watchlist(name, symbol)
    except Exception as exc:
        raise RuntimeError(f"Failed to remove {symbol} from watchlist '{name}': {exc}") from exc

    return {"status": "removed", "watchlist": name, "symbol": symbol, "result": result}


def delete_watchlist(name: str) -> dict[str, Any]:
    """Delete an entire watchlist."""
    try:
        result = rh.account.delete_watchlist(name)
    except Exception as exc:
        raise RuntimeError(f"Failed to delete watchlist '{name}': {exc}") from exc

    return {
        "status": "deleted",
        "name": name,
        "warning": f"Watchlist '{name}' has been permanently deleted.",
        "result": result,
    }


def _resolve_instrument_symbol(instrument_url: str) -> str | None:
    """Fetch the ticker symbol for a Robinhood instrument URL."""
    if not instrument_url:
        return None
    try:
        data = rh.stocks.get_instrument_by_url(instrument_url)
        if data and isinstance(data, dict):
            return data.get("symbol")
    except Exception:
        pass
    return None
