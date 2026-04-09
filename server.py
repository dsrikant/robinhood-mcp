"""
Robinhood MCP Server
Entry point — registers all tools with FastMCP and starts the stdio transport.
"""
from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from fastmcp import FastMCP

import auth
import market_data
import orders
import portfolio
import watchlists
from config import configure_logging, get_config

logger = logging.getLogger(__name__)

mcp = FastMCP("robinhood")

# ──────────────────────────────────────────────────────────────────────────────
# Error envelope helper
# ──────────────────────────────────────────────────────────────────────────────

def _err(code: str, message: str, action_required: str = "") -> dict[str, Any]:
    return {"status": "error", "code": code, "message": message, "action_required": action_required}


def _wrap(fn, *args, **kwargs) -> dict[str, Any]:
    """Call fn(*args, **kwargs), catching all exceptions into an error envelope."""
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        return _err("INVALID_SYMBOL", str(exc), "Check the symbol and try again.")
    except RuntimeError as exc:
        return _err("ROBINHOOD_API_ERROR", str(exc), "")
    except Exception as exc:
        logger.exception("Unexpected error in tool call")
        return _err("ROBINHOOD_API_ERROR", f"Unexpected error: {exc}", "")


# ──────────────────────────────────────────────────────────────────────────────
# Auth tools
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def rh_login(mfa_code: Optional[str] = None) -> dict:
    """
    Authenticate with Robinhood. Credentials are read from the ROBINHOOD_USERNAME
    and ROBINHOOD_PASSWORD environment variables — never passed as parameters.
    If MFA is required, this tool returns an mfa_required response — call it
    again with the mfa_code parameter to complete login.
    """
    return _wrap(auth.login, mfa_code)


@mcp.tool()
def rh_logout() -> dict:
    """Revoke the current Robinhood session and delete the local session file."""
    return _wrap(auth.logout)


@mcp.tool()
def rh_session_status() -> dict:
    """
    Check whether a valid Robinhood session exists.
    Returns authenticated status, account number, and token age.
    """
    return _wrap(auth.session_status)


# ──────────────────────────────────────────────────────────────────────────────
# Portfolio tools
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def rh_get_portfolio() -> dict:
    """
    Return all current equity and crypto positions with P&L data, plus a
    portfolio summary with total value and gain/loss metrics.
    """
    return _wrap(portfolio.get_portfolio)


@mcp.tool()
def rh_get_account_info() -> dict:
    """
    Return account-level data including PDT day trade count, PDT flag status,
    cash balances, and buying power.

    day_trade_count: number of day trades used in the rolling 5-trading-day window (resets daily).
    pattern_day_trader: True if the account has been flagged as a PDT account.
    cash: settled cash available.
    buying_power: total buying power including margin if applicable.
    cash_held_for_orders: cash currently reserved for open orders.
    portfolio_cash: total cash value in the portfolio.
    """
    return _wrap(portfolio.get_account_info)


@mcp.tool()
def rh_get_quote(symbol: str) -> dict:
    """
    Get a real-time quote for any equity or crypto symbol.
    Returns bid/ask, last trade price, day high/low, volume, and market cap.
    """
    return _wrap(market_data.get_quote, symbol)


# ──────────────────────────────────────────────────────────────────────────────
# Equity order tools
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def rh_order_buy_market(
    symbol: str,
    quantity: float,
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Buy shares at the current market price.
    Always call with dry_run=True first to get a confirmation_token.
    Then call again with dry_run=False and the confirmation_token to execute.
    """
    return _wrap(orders.order_buy_market, symbol, quantity, dry_run, confirmation_token)


@mcp.tool()
def rh_order_sell_market(
    symbol: str,
    quantity: float,
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Sell shares at the current market price.
    Always call with dry_run=True first to get a confirmation_token.
    Then call again with dry_run=False and the confirmation_token to execute.
    """
    return _wrap(orders.order_sell_market, symbol, quantity, dry_run, confirmation_token)


@mcp.tool()
def rh_order_buy_limit(
    symbol: str,
    quantity: float,
    limit_price: float,
    time_in_force: Literal["gfd", "gtc"] = "gfd",
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Buy shares at or below a specified limit price.
    time_in_force: 'gfd' (good for day) or 'gtc' (good till cancelled).
    """
    return _wrap(orders.order_buy_limit, symbol, quantity, limit_price, time_in_force, dry_run, confirmation_token)


@mcp.tool()
def rh_order_sell_limit(
    symbol: str,
    quantity: float,
    limit_price: float,
    time_in_force: Literal["gfd", "gtc"] = "gfd",
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Sell shares at or above a specified limit price.
    time_in_force: 'gfd' (good for day) or 'gtc' (good till cancelled).
    """
    return _wrap(orders.order_sell_limit, symbol, quantity, limit_price, time_in_force, dry_run, confirmation_token)


@mcp.tool()
def rh_order_buy_stop_loss(
    symbol: str,
    quantity: float,
    stop_price: float,
    time_in_force: Literal["gfd", "gtc"] = "gfd",
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Buy shares when the price rises to or above stop_price (market order triggered at stop).
    Note: fractional quantities only trigger price alerts, not execution.
    """
    return _wrap(orders.order_buy_stop_loss, symbol, quantity, stop_price, time_in_force, dry_run, confirmation_token)


@mcp.tool()
def rh_order_sell_stop_loss(
    symbol: str,
    quantity: float,
    stop_price: float,
    time_in_force: Literal["gfd", "gtc"] = "gfd",
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Sell shares when the price drops to or below stop_price (market order triggered at stop).
    Note: fractional quantities only trigger price alerts, not execution.
    """
    return _wrap(orders.order_sell_stop_loss, symbol, quantity, stop_price, time_in_force, dry_run, confirmation_token)


@mcp.tool()
def rh_order_buy_stop_limit(
    symbol: str,
    quantity: float,
    stop_price: float,
    limit_price: float,
    time_in_force: Literal["gfd", "gtc"] = "gfd",
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Buy shares when price hits stop_price, then place a limit order at limit_price.
    """
    return _wrap(orders.order_buy_stop_limit, symbol, quantity, stop_price, limit_price, time_in_force, dry_run, confirmation_token)


@mcp.tool()
def rh_order_sell_stop_limit(
    symbol: str,
    quantity: float,
    stop_price: float,
    limit_price: float,
    time_in_force: Literal["gfd", "gtc"] = "gfd",
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Sell shares when price hits stop_price, then place a limit order at limit_price.
    """
    return _wrap(orders.order_sell_stop_limit, symbol, quantity, stop_price, limit_price, time_in_force, dry_run, confirmation_token)


@mcp.tool()
def rh_order_buy_trailing_stop(
    symbol: str,
    quantity: float,
    trail_amount: float,
    trail_type: Literal["amount", "percentage"] = "percentage",
    time_in_force: Literal["gfd", "gtc"] = "gfd",
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Buy with a trailing stop that rises with the price by trail_amount.
    trail_type: 'percentage' (e.g. 5 = 5%) or 'amount' (e.g. 5 = $5).
    """
    return _wrap(orders.order_buy_trailing_stop, symbol, quantity, trail_amount, trail_type, time_in_force, dry_run, confirmation_token)


@mcp.tool()
def rh_order_sell_trailing_stop(
    symbol: str,
    quantity: float,
    trail_amount: float,
    trail_type: Literal["amount", "percentage"] = "percentage",
    time_in_force: Literal["gfd", "gtc"] = "gfd",
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Sell with a trailing stop that follows the price upward by trail_amount.
    trail_type: 'percentage' (e.g. 5 = 5%) or 'amount' (e.g. 5 = $5).
    """
    return _wrap(orders.order_sell_trailing_stop, symbol, quantity, trail_amount, trail_type, time_in_force, dry_run, confirmation_token)


# ──────────────────────────────────────────────────────────────────────────────
# Order management
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def rh_confirm_order(confirmation_token: str) -> dict:
    """
    Execute a pending order using the confirmation_token returned by a dry_run call.
    Tokens expire after 60 seconds and are single-use.
    """
    return _wrap(orders.confirm_order, confirmation_token)


@mcp.tool()
def rh_cancel_order(order_id: str) -> dict:
    """Cancel an open or queued order by its order ID."""
    return _wrap(orders.cancel_order, order_id)


@mcp.tool()
def rh_get_open_orders() -> dict:
    """Return all currently open equity and crypto orders."""
    return _wrap(orders.get_open_orders)


@mcp.tool()
def rh_get_order_history(limit: int = 20) -> dict:
    """
    Return the last N filled and cancelled orders across equity and crypto.
    Results are sorted most-recent first. Default limit is 20; maximum useful range is ~100.
    """
    return _wrap(orders.get_order_history, limit)


# ──────────────────────────────────────────────────────────────────────────────
# Crypto order tools
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def rh_crypto_order_buy_market(
    symbol: str,
    quantity: float,
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Buy cryptocurrency at the current market price.
    Supported symbols: BTC, ETH, DOGE, etc.
    Always dry_run=True first, then confirm with the returned token.
    """
    return _wrap(orders.crypto_order_buy_market, symbol, quantity, dry_run, confirmation_token)


@mcp.tool()
def rh_crypto_order_sell_market(
    symbol: str,
    quantity: float,
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Sell cryptocurrency at the current market price.
    Always dry_run=True first, then confirm with the returned token.
    """
    return _wrap(orders.crypto_order_sell_market, symbol, quantity, dry_run, confirmation_token)


@mcp.tool()
def rh_crypto_order_buy_limit(
    symbol: str,
    quantity: float,
    limit_price: float,
    time_in_force: Literal["gfd", "gtc"] = "gtc",
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Buy cryptocurrency at or below limit_price.
    Crypto limit orders default to 'gtc' (good till cancelled).
    """
    return _wrap(orders.crypto_order_buy_limit, symbol, quantity, limit_price, time_in_force, dry_run, confirmation_token)


@mcp.tool()
def rh_crypto_order_sell_limit(
    symbol: str,
    quantity: float,
    limit_price: float,
    time_in_force: Literal["gfd", "gtc"] = "gtc",
    dry_run: bool = True,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    Sell cryptocurrency at or above limit_price.
    Crypto limit orders default to 'gtc' (good till cancelled).
    """
    return _wrap(orders.crypto_order_sell_limit, symbol, quantity, limit_price, time_in_force, dry_run, confirmation_token)


# ──────────────────────────────────────────────────────────────────────────────
# Watchlist tools
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def rh_get_watchlists() -> dict:
    """Return all Robinhood watchlists with their names and symbol counts."""
    return _wrap(watchlists.get_watchlists)


@mcp.tool()
def rh_get_watchlist(name: str) -> dict:
    """Return symbols and current quotes for a named watchlist."""
    return _wrap(watchlists.get_watchlist, name)


@mcp.tool()
def rh_create_watchlist(name: str) -> dict:
    """Create a new empty watchlist with the given name."""
    return _wrap(watchlists.create_watchlist, name)


@mcp.tool()
def rh_add_to_watchlist(name: str, symbol: str) -> dict:
    """Add a ticker symbol to a named watchlist."""
    return _wrap(watchlists.add_to_watchlist, name, symbol)


@mcp.tool()
def rh_remove_from_watchlist(name: str, symbol: str) -> dict:
    """Remove a ticker symbol from a named watchlist."""
    return _wrap(watchlists.remove_from_watchlist, name, symbol)


@mcp.tool()
def rh_delete_watchlist(name: str) -> dict:
    """
    Permanently delete an entire watchlist.
    WARNING: This action is irreversible. Confirm with the user before calling.
    """
    return _wrap(watchlists.delete_watchlist, name)


# ──────────────────────────────────────────────────────────────────────────────
# Startup
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = get_config()
    configure_logging(cfg)

    logger.info("Robinhood MCP server starting")

    restored = auth.load_session()
    if restored:
        logger.info("Session restored from disk")
    else:
        logger.info("No session on disk — call rh_login to authenticate")

    mcp.run()
