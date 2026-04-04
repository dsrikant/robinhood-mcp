from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

ROBINHOOD_DIR = Path.home() / ".robinhood"
CONFIG_PATH = ROBINHOOD_DIR / "config.toml"

_DEFAULTS = {
    "safety": {
        "max_order_value_usd": 5000.0,
        "default_dry_run": True,
        "confirmation_token_ttl_seconds": 60,
    },
    "server": {
        "log_level": "INFO",
        "log_file": str(ROBINHOOD_DIR / "mcp.log"),
    },
}


@dataclass
class Config:
    max_order_value_usd: float = 5000.0
    default_dry_run: bool = True
    confirmation_token_ttl_seconds: int = 60
    log_level: str = "INFO"
    log_file: str = str(ROBINHOOD_DIR / "mcp.log")


def _load_raw() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def get_config() -> Config:
    raw = _load_raw()
    safety = raw.get("safety", {})
    server = raw.get("server", {})
    defaults_safety = _DEFAULTS["safety"]
    defaults_server = _DEFAULTS["server"]
    return Config(
        max_order_value_usd=float(safety.get("max_order_value_usd", defaults_safety["max_order_value_usd"])),
        default_dry_run=bool(safety.get("default_dry_run", defaults_safety["default_dry_run"])),
        confirmation_token_ttl_seconds=int(
            safety.get("confirmation_token_ttl_seconds", defaults_safety["confirmation_token_ttl_seconds"])
        ),
        log_level=str(server.get("log_level", defaults_server["log_level"])).upper(),
        log_file=str(server.get("log_file", defaults_server["log_file"])),
    )


def configure_logging(cfg: Config) -> None:
    level = getattr(logging, cfg.log_level, logging.INFO)
    log_file = os.path.expanduser(cfg.log_file)

    handlers: list[logging.Handler] = []

    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    except Exception:
        pass

    # MCP servers must NOT write to stdout (it's the transport channel).
    # Only log to file; stderr is acceptable as a fallback but noisy.
    if not handlers:
        handlers.append(logging.StreamHandler(sys.stderr))

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
