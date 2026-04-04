from __future__ import annotations

import logging
from typing import Any, Callable, Literal

import robin_stocks.robinhood as rh

import confirmation
import guards
import market_data
from config import get_config

logger = logging.getLogger(__name__)

TimeInForce = Literal["gfd", "gtc"]
TrailType = Literal["amount", "percentage"]

# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _cfg():
    return get_config()


def _estimate_value(symbol: str, quantity: float, asset_type: str | None, limit_price: float | None = None) -> float:
    if limit_price is not None:
        return abs(limit_price * quantity)
    price = market_data.get_last_trade_price(symbol, asset_type)
    return (price or 0.0) * abs(quantity)


def _dry_run_result(summary: str, order_fn: Callable[[], Any]) -> dict[str, Any]:
    cfg = _cfg()
    token, expires_in = confirmation.generate_token(order_fn, summary, cfg.confirmation_token_ttl_seconds)
    return {
        "status": "dry_run",
        "summary": summary,
        "confirmation_token": token,
        "expires_in_seconds": expires_in,
    }


def _fractional_stop_warning(quantity: float, order_type: str) -> str:
    if quantity != int(quantity) and "stop" in order_type:
        return (
            " ⚠️ Warning: Robinhood stop orders on fractional shares only trigger price alerts, "
            "not execution. Consider using a whole-share quantity."
        )
    return ""


def _normalize_order_result(raw: Any) -> dict[str, Any]:
    if not raw or not isinstance(raw, dict):
        return {"status": "error", "code": "ROBINHOOD_API_ERROR", "message": "Empty response from Robinhood.", "action_required": ""}
    return {
        "status": "submitted",
        "order_id": raw.get("id", raw.get("order_id", "unknown")),
        "state": raw.get("state", "unknown"),
        "type": raw.get("type", "unknown"),
        "side": raw.get("side", "unknown"),
        "symbol": raw.get("symbol") or raw.get("currency_pair_id", "unknown"),
        "quantity": raw.get("quantity") or raw.get("rounded_executed_notional"),
        "price": raw.get("price") or raw.get("executed_notional"),
        "raw": raw,
    }


def _guard_and_estimate(
    symbol: str,
    quantity: float,
    limit_price: float | None = None,
) -> tuple[dict | None, float, str | None]:
    """
    Run option + value guards. Returns (blocked_dict | None, estimated_value, asset_type).
    """
    blocked = guards.check_options_symbol(symbol)
    if blocked:
        return blocked, 0.0, None

    asset_type = market_data.resolve_asset_type(symbol)
    estimated = _estimate_value(symbol, quantity, asset_type, limit_price)

    cfg = _cfg()
    blocked = guards.check_order_value(estimated, cfg)
    if blocked:
        return blocked, estimated, asset_type

    return None, estimated, asset_type


def _execute_or_dryrun(
    dry_run: bool,
    confirmation_token: str | None,
    summary: str,
    order_fn: Callable[[], Any],
) -> dict[str, Any]:
    if dry_run:
        return _dry_run_result(summary, order_fn)

    # Confirm path: consume the token, then execute.
    if not confirmation_token:
        return {
            "status": "error",
            "code": "ORDER_BLOCKED",
            "message": "confirmation_token is required when dry_run=False. First call with dry_run=True to get a token.",
            "action_required": "Call this tool with dry_run=True first to receive a confirmation_token.",
        }

    cfg = _cfg()
    try:
        fn = confirmation.consume_token(confirmation_token, cfg.confirmation_token_ttl_seconds)
    except confirmation.TokenExpiredError:
        return {
            "status": "error",
            "code": "TOKEN_EXPIRED",
            "message": "Confirmation token has expired. Please start over with a new dry_run.",
            "action_required": "Call this tool with dry_run=True to get a fresh token.",
        }
    except confirmation.TokenNotFoundError:
        return {
            "status": "error",
            "code": "TOKEN_NOT_FOUND",
            "message": "Confirmation token not found. It may have already been used or never existed.",
            "action_required": "Call this tool with dry_run=True to get a new token.",
        }

    try:
        raw = fn()
        return _normalize_order_result(raw)
    except Exception as exc:
        logger.exception("Order execution failed")
        return {
            "status": "error",
            "code": "ROBINHOOD_API_ERROR",
            "message": str(exc),
            "action_required": "",
        }


# ──────────────────────────────────────────────────────────────────────────────
# Equity order functions
# ──────────────────────────────────────────────────────────────────────────────

def order_buy_market(
    symbol: str,
    quantity: float,
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity)
    if blocked:
        return blocked

    summary = f"Buy {quantity} shares of {symbol} at market (~${estimated:,.2f} estimated)"
    order_fn = lambda: rh.orders.order_buy_market(symbol, quantity)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def order_sell_market(
    symbol: str,
    quantity: float,
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity)
    if blocked:
        return blocked

    summary = f"Sell {quantity} shares of {symbol} at market (~${estimated:,.2f} estimated)"
    order_fn = lambda: rh.orders.order_sell_market(symbol, quantity)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def order_buy_limit(
    symbol: str,
    quantity: float,
    limit_price: float,
    time_in_force: TimeInForce = "gfd",
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity, limit_price)
    if blocked:
        return blocked

    summary = f"Buy {quantity} shares of {symbol} at limit ${limit_price:,.2f} (~${estimated:,.2f} estimated)"
    order_fn = lambda: rh.orders.order_buy_limit(symbol, quantity, limit_price, timeInForce=time_in_force)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def order_sell_limit(
    symbol: str,
    quantity: float,
    limit_price: float,
    time_in_force: TimeInForce = "gfd",
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity, limit_price)
    if blocked:
        return blocked

    summary = f"Sell {quantity} shares of {symbol} at limit ${limit_price:,.2f} (~${estimated:,.2f} estimated)"
    order_fn = lambda: rh.orders.order_sell_limit(symbol, quantity, limit_price, timeInForce=time_in_force)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def order_buy_stop_loss(
    symbol: str,
    quantity: float,
    stop_price: float,
    time_in_force: TimeInForce = "gfd",
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity, stop_price)
    if blocked:
        return blocked

    warn = _fractional_stop_warning(quantity, "stop_loss")
    summary = f"Buy {quantity} shares of {symbol} stop-loss at ${stop_price:,.2f} (~${estimated:,.2f} estimated){warn}"
    order_fn = lambda: rh.orders.order_buy_stop_loss(symbol, quantity, stop_price, timeInForce=time_in_force)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def order_sell_stop_loss(
    symbol: str,
    quantity: float,
    stop_price: float,
    time_in_force: TimeInForce = "gfd",
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity, stop_price)
    if blocked:
        return blocked

    warn = _fractional_stop_warning(quantity, "stop_loss")
    summary = f"Sell {quantity} shares of {symbol} stop-loss at ${stop_price:,.2f} (~${estimated:,.2f} estimated){warn}"
    order_fn = lambda: rh.orders.order_sell_stop_loss(symbol, quantity, stop_price, timeInForce=time_in_force)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def order_buy_stop_limit(
    symbol: str,
    quantity: float,
    stop_price: float,
    limit_price: float,
    time_in_force: TimeInForce = "gfd",
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity, limit_price)
    if blocked:
        return blocked

    warn = _fractional_stop_warning(quantity, "stop_limit")
    summary = (
        f"Buy {quantity} shares of {symbol} stop-limit: stop ${stop_price:,.2f}, "
        f"limit ${limit_price:,.2f} (~${estimated:,.2f} estimated){warn}"
    )
    order_fn = lambda: rh.orders.order_buy_stop_limit(symbol, quantity, stop_price, limit_price, timeInForce=time_in_force)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def order_sell_stop_limit(
    symbol: str,
    quantity: float,
    stop_price: float,
    limit_price: float,
    time_in_force: TimeInForce = "gfd",
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity, limit_price)
    if blocked:
        return blocked

    warn = _fractional_stop_warning(quantity, "stop_limit")
    summary = (
        f"Sell {quantity} shares of {symbol} stop-limit: stop ${stop_price:,.2f}, "
        f"limit ${limit_price:,.2f} (~${estimated:,.2f} estimated){warn}"
    )
    order_fn = lambda: rh.orders.order_sell_stop_limit(symbol, quantity, stop_price, limit_price, timeInForce=time_in_force)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def order_buy_trailing_stop(
    symbol: str,
    quantity: float,
    trail_amount: float,
    trail_type: TrailType = "percentage",
    time_in_force: TimeInForce = "gfd",
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity)
    if blocked:
        return blocked

    unit = "%" if trail_type == "percentage" else "$"
    warn = _fractional_stop_warning(quantity, "trailing_stop")
    summary = (
        f"Buy {quantity} shares of {symbol} trailing stop: trail {trail_amount}{unit} "
        f"(~${estimated:,.2f} estimated){warn}"
    )
    order_fn = lambda: rh.orders.order_buy_trailing_stop(
        symbol, quantity, trail_amount, trailType=trail_type, timeInForce=time_in_force
    )
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def order_sell_trailing_stop(
    symbol: str,
    quantity: float,
    trail_amount: float,
    trail_type: TrailType = "percentage",
    time_in_force: TimeInForce = "gfd",
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity)
    if blocked:
        return blocked

    unit = "%" if trail_type == "percentage" else "$"
    warn = _fractional_stop_warning(quantity, "trailing_stop")
    summary = (
        f"Sell {quantity} shares of {symbol} trailing stop: trail {trail_amount}{unit} "
        f"(~${estimated:,.2f} estimated){warn}"
    )
    order_fn = lambda: rh.orders.order_sell_trailing_stop(
        symbol, quantity, trail_amount, trailType=trail_type, timeInForce=time_in_force
    )
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


# ──────────────────────────────────────────────────────────────────────────────
# Crypto order functions
# ──────────────────────────────────────────────────────────────────────────────

def crypto_order_buy_market(
    symbol: str,
    quantity: float,
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity)
    if blocked:
        return blocked

    summary = f"Buy {quantity} {symbol} (crypto) at market (~${estimated:,.2f} estimated)"
    order_fn = lambda: rh.crypto.order_buy_crypto_by_quantity(symbol, quantity)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def crypto_order_sell_market(
    symbol: str,
    quantity: float,
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity)
    if blocked:
        return blocked

    summary = f"Sell {quantity} {symbol} (crypto) at market (~${estimated:,.2f} estimated)"
    order_fn = lambda: rh.crypto.order_sell_crypto_by_quantity(symbol, quantity)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def crypto_order_buy_limit(
    symbol: str,
    quantity: float,
    limit_price: float,
    time_in_force: TimeInForce = "gtc",
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity, limit_price)
    if blocked:
        return blocked

    summary = f"Buy {quantity} {symbol} (crypto) at limit ${limit_price:,.2f} (~${estimated:,.2f} estimated)"
    order_fn = lambda: rh.crypto.order_buy_crypto_limit_order(symbol, quantity, limit_price, timeInForce=time_in_force)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


def crypto_order_sell_limit(
    symbol: str,
    quantity: float,
    limit_price: float,
    time_in_force: TimeInForce = "gtc",
    dry_run: bool = True,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    blocked, estimated, asset_type = _guard_and_estimate(symbol, quantity, limit_price)
    if blocked:
        return blocked

    summary = f"Sell {quantity} {symbol} (crypto) at limit ${limit_price:,.2f} (~${estimated:,.2f} estimated)"
    order_fn = lambda: rh.crypto.order_sell_crypto_limit_order(symbol, quantity, limit_price, timeInForce=time_in_force)
    return _execute_or_dryrun(dry_run, confirmation_token, summary, order_fn)


# ──────────────────────────────────────────────────────────────────────────────
# Order management
# ──────────────────────────────────────────────────────────────────────────────

def confirm_order(confirmation_token: str) -> dict[str, Any]:
    """Execute a pending order by consuming its confirmation token."""
    cfg = _cfg()
    try:
        fn = confirmation.consume_token(confirmation_token, cfg.confirmation_token_ttl_seconds)
    except confirmation.TokenExpiredError:
        return {
            "status": "error",
            "code": "TOKEN_EXPIRED",
            "message": "Confirmation token has expired.",
            "action_required": "Start over with dry_run=True to get a fresh token.",
        }
    except confirmation.TokenNotFoundError:
        return {
            "status": "error",
            "code": "TOKEN_NOT_FOUND",
            "message": "Confirmation token not found or already used.",
            "action_required": "Start over with dry_run=True to get a new token.",
        }

    try:
        raw = fn()
        return _normalize_order_result(raw)
    except Exception as exc:
        logger.exception("Order execution failed in confirm_order")
        return {
            "status": "error",
            "code": "ROBINHOOD_API_ERROR",
            "message": str(exc),
            "action_required": "",
        }


def get_open_orders() -> dict[str, Any]:
    """Return all open equity and crypto orders."""
    orders: list[dict[str, Any]] = []

    try:
        equity_orders = rh.orders.get_all_open_stock_orders()
        if equity_orders and isinstance(equity_orders, list):
            for o in equity_orders:
                orders.append(_normalize_open_order(o, "equity"))
    except Exception as exc:
        logger.warning("Failed to fetch open equity orders: %s", exc)

    try:
        crypto_orders = rh.orders.get_all_open_crypto_orders()
        if crypto_orders and isinstance(crypto_orders, list):
            for o in crypto_orders:
                orders.append(_normalize_open_order(o, "crypto"))
    except Exception as exc:
        logger.warning("Failed to fetch open crypto orders: %s", exc)

    return {"open_orders": orders, "count": len(orders)}


def cancel_order(order_id: str) -> dict[str, Any]:
    """Cancel an open order by ID. Tries equity first, then crypto."""
    try:
        result = rh.orders.cancel_stock_order(order_id)
        if result is not None:
            return {"status": "cancelled", "order_id": order_id, "asset_type": "equity"}
    except Exception:
        pass

    try:
        result = rh.orders.cancel_crypto_order(order_id)
        if result is not None:
            return {"status": "cancelled", "order_id": order_id, "asset_type": "crypto"}
    except Exception:
        pass

    return {
        "status": "error",
        "code": "ROBINHOOD_API_ERROR",
        "message": f"Could not cancel order '{order_id}'. It may not exist or may already be filled/cancelled.",
        "action_required": "",
    }


def _normalize_open_order(raw: dict[str, Any], asset_type: str) -> dict[str, Any]:
    return {
        "order_id": raw.get("id", "unknown"),
        "asset_type": asset_type,
        "side": raw.get("side", "unknown"),
        "type": raw.get("type", "unknown"),
        "symbol": raw.get("symbol") or raw.get("currency_pair_id", "unknown"),
        "quantity": raw.get("quantity"),
        "price": raw.get("price"),
        "stop_price": raw.get("stop_price"),
        "time_in_force": raw.get("time_in_force"),
        "state": raw.get("state", "unknown"),
        "created_at": raw.get("created_at"),
    }
