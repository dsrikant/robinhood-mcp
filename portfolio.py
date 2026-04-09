from __future__ import annotations

import logging
from typing import Any

import robin_stocks.robinhood as rh
import robin_stocks.robinhood.helper as rh_helper

logger = logging.getLogger(__name__)


def get_portfolio() -> dict[str, Any]:
    """
    Return all equity and crypto positions plus a portfolio summary.
    """
    positions: list[dict[str, Any]] = []

    # --- Equity positions ---
    try:
        holdings = rh.account.build_holdings()
        if holdings and isinstance(holdings, dict):
            for ticker, data in holdings.items():
                positions.append(_normalize_equity(ticker, data))
    except Exception as exc:
        logger.warning("Failed to fetch equity holdings: %s", exc)

    # --- Crypto positions ---
    try:
        crypto_positions = rh.crypto.get_crypto_positions()
        if crypto_positions and isinstance(crypto_positions, list):
            for pos in crypto_positions:
                normalized = _normalize_crypto(pos)
                if normalized:
                    positions.append(normalized)
    except Exception as exc:
        logger.warning("Failed to fetch crypto positions: %s", exc)

    # --- Summary ---
    summary = _build_summary(positions)

    return {
        "positions": positions,
        "summary": summary,
    }


def _normalize_equity(ticker: str, data: dict[str, Any]) -> dict[str, Any]:
    quantity = _float(data.get("quantity")) or 0.0
    avg_buy = _float(data.get("average_buy_price")) or 0.0
    current = _float(data.get("price")) or 0.0
    prev_close = _float(data.get("previous_close")) or current

    market_value = current * quantity
    cost_basis = avg_buy * quantity
    total_gain = market_value - cost_basis
    total_gain_pct = (total_gain / cost_basis * 100) if cost_basis else 0.0

    daily_change_per_share = current - prev_close
    daily_change = daily_change_per_share * quantity
    daily_change_pct = (daily_change_per_share / prev_close * 100) if prev_close else 0.0

    return {
        "ticker": ticker,
        "name": data.get("name", ticker),
        "quantity": quantity,
        "average_buy_price": avg_buy,
        "current_price": current,
        "daily_change": round(daily_change, 4),
        "daily_change_pct": round(daily_change_pct, 4),
        "total_gain": round(total_gain, 4),
        "total_gain_pct": round(total_gain_pct, 4),
        "market_value": round(market_value, 4),
        "asset_type": "equity",
    }


def _normalize_crypto(pos: dict[str, Any]) -> dict[str, Any] | None:
    quantity = _float(pos.get("quantity"))
    if quantity is None or quantity == 0:
        return None

    # Fetch live quote for current price.
    currency_code: str = ""
    currency = pos.get("currency")
    if isinstance(currency, dict):
        currency_code = currency.get("code", "")
    elif isinstance(currency, str):
        currency_code = currency

    if not currency_code:
        return None

    current_price: float | None = None
    prev_close: float | None = None
    try:
        quote = rh.crypto.get_crypto_quote(currency_code)
        if quote and isinstance(quote, dict):
            current_price = _float(quote.get("mark_price") or quote.get("last_trade_price"))
            prev_close = _float(quote.get("open_price"))
    except Exception as exc:
        logger.debug("Crypto quote fetch failed for %s: %s", currency_code, exc)

    current_price = current_price or 0.0
    prev_close = prev_close or current_price

    avg_buy = _float(pos.get("average_buy_price")) or 0.0
    market_value = current_price * quantity
    cost_basis = avg_buy * quantity
    total_gain = market_value - cost_basis
    total_gain_pct = (total_gain / cost_basis * 100) if cost_basis else 0.0

    daily_change_per_unit = current_price - prev_close
    daily_change = daily_change_per_unit * quantity
    daily_change_pct = (daily_change_per_unit / prev_close * 100) if prev_close else 0.0

    return {
        "ticker": currency_code,
        "name": currency_code,
        "quantity": quantity,
        "average_buy_price": avg_buy,
        "current_price": current_price,
        "daily_change": round(daily_change, 4),
        "daily_change_pct": round(daily_change_pct, 4),
        "total_gain": round(total_gain, 4),
        "total_gain_pct": round(total_gain_pct, 4),
        "market_value": round(market_value, 4),
        "asset_type": "crypto",
    }


def _build_summary(positions: list[dict[str, Any]]) -> dict[str, Any]:
    total_value = sum(p.get("market_value", 0) or 0 for p in positions)
    total_daily_gain = sum(p.get("daily_change", 0) or 0 for p in positions)
    total_all_time_gain = sum(p.get("total_gain", 0) or 0 for p in positions)

    cost_basis_total = sum(
        (p.get("average_buy_price", 0) or 0) * (p.get("quantity", 0) or 0)
        for p in positions
    )
    prev_value_total = sum(
        (p.get("market_value", 0) or 0) - (p.get("daily_change", 0) or 0)
        for p in positions
    )

    daily_gain_pct = (total_daily_gain / prev_value_total * 100) if prev_value_total else 0.0
    all_time_gain_pct = (total_all_time_gain / cost_basis_total * 100) if cost_basis_total else 0.0

    return {
        "total_portfolio_value": round(total_value, 2),
        "total_daily_gain": round(total_daily_gain, 2),
        "total_daily_gain_pct": round(daily_gain_pct, 4),
        "total_all_time_gain": round(total_all_time_gain, 2),
        "total_all_time_gain_pct": round(all_time_gain_pct, 4),
    }


def get_account_info() -> dict[str, Any]:
    """
    Return account-level data including PDT day trade count, PDT flag status,
    cash balances, and buying power.
    """
    # Fetch raw accounts response — load_account_profile() wrapper does not
    # reliably surface day_trade_count; the raw results[0] object is authoritative.
    response = rh_helper.request_get(
        "https://api.robinhood.com/accounts/",
        jsonify_data=True,
    )

    if not response or "results" not in response or not response["results"]:
        return {"error": "Failed to load account profile. Session may be expired."}

    account = response["results"][0]

    return {
        "day_trade_count":      _int(account.get("day_trade_count")),
        "pattern_day_trader":   account.get("pattern_day_trader", False),
        "cash":                 _float(account.get("cash")),
        "buying_power":         _float(account.get("buying_power")),
        "cash_held_for_orders": _float(account.get("cash_held_for_orders")),
        "portfolio_cash":       _float(account.get("portfolio_cash")),
        "account_number":       account.get("account_number"),
        "account_type":         account.get("type"),
        "sma":                  _float(account.get("sma")),
    }


def _float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
