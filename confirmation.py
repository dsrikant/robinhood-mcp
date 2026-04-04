from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


class TokenExpiredError(Exception):
    pass


class TokenNotFoundError(Exception):
    pass


@dataclass
class PendingOrder:
    order_fn: Callable[[], Any]
    summary: str
    created_at: float = field(default_factory=time.monotonic)


# In-process memory only — never serialized to disk.
_pending: dict[str, PendingOrder] = {}

# TTL is read from config at call time to allow tests to override easily.
_DEFAULT_TTL = 60


def generate_token(order_fn: Callable[[], Any], summary: str, ttl: int = _DEFAULT_TTL) -> tuple[str, int]:
    """Store a pending order and return (token, expires_in_seconds)."""
    token = uuid.uuid4().hex
    _pending[token] = PendingOrder(order_fn=order_fn, summary=summary)
    return token, ttl


def consume_token(token: str, ttl: int = _DEFAULT_TTL) -> Callable[[], Any]:
    """
    Validate and remove a pending order token.
    Raises TokenNotFoundError or TokenExpiredError on failure.
    Returns the order callable on success.
    """
    entry = _pending.get(token)
    if entry is None:
        raise TokenNotFoundError(f"No pending order for token '{token}'")

    age = time.monotonic() - entry.created_at
    if age > ttl:
        del _pending[token]
        raise TokenExpiredError(f"Confirmation token expired after {ttl}s (age: {age:.1f}s)")

    del _pending[token]
    return entry.order_fn


def get_summary(token: str) -> str | None:
    """Return the dry-run summary for a token without consuming it."""
    entry = _pending.get(token)
    return entry.summary if entry else None


def clear_all() -> None:
    """Remove all pending tokens (useful for testing)."""
    _pending.clear()
