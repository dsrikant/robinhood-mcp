from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import robin_stocks.robinhood as rh

logger = logging.getLogger(__name__)

ROBINHOOD_DIR = Path.home() / ".robinhood"
SESSION_PATH = ROBINHOOD_DIR / "session.json"

# Tracks when we last loaded/created a session (wall-clock seconds)
_session_loaded_at: float | None = None
_session_account: str | None = None


def _ensure_dir() -> None:
    ROBINHOOD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)


def save_session(token_data: dict[str, Any]) -> None:
    _ensure_dir()
    path = str(SESSION_PATH)
    with open(path, "w") as f:
        json.dump(token_data, f)
    os.chmod(path, 0o600)
    logger.info("Session saved to %s", path)


def load_session() -> bool:
    """
    Load a persisted session token and inject it into robin_stocks.
    Returns True if a session was successfully loaded, False otherwise.
    """
    global _session_loaded_at, _session_account

    if not SESSION_PATH.exists():
        logger.debug("No session file found at %s", SESSION_PATH)
        return False

    try:
        with open(SESSION_PATH) as f:
            token_data: dict[str, Any] = json.load(f)
    except Exception as exc:
        logger.warning("Failed to read session file: %s", exc)
        return False

    # robin_stocks stores session state in its globals; we replay the login
    # state by calling login with the stored token.
    access_token = token_data.get("access_token")
    if not access_token:
        logger.warning("Session file missing access_token")
        return False

    try:
        # Restore session by setting robin_stocks internal state directly.
        # robin_stocks exposes set_login_state for this purpose.
        rh.authentication.set_login_state(True)
        rh.helper.set_default_account(token_data.get("account_id", ""))

        # Inject the bearer token into the requests session headers.
        import requests
        session = rh.helper.get_session()
        session.headers.update({"Authorization": f"Bearer {access_token}"})

        _session_loaded_at = time.time()
        _session_account = token_data.get("account_id", "unknown")
        logger.info("Session restored for account %s", _session_account)
        return True
    except Exception as exc:
        logger.warning("Failed to restore session state: %s", exc)
        return False


def login(username: str, password: str, mfa_code: str | None = None) -> dict[str, Any]:
    """
    Authenticate with Robinhood. Persists session to disk on success.
    Returns a result dict or an error/mfa-required dict.
    """
    global _session_loaded_at, _session_account

    # Never log credentials.
    logger.info("Attempting login for user %s", username)

    try:
        result = rh.login(
            username=username,
            password=password,
            mfa_code=mfa_code,
            store_session=False,  # We manage persistence ourselves.
            by_sms=True,
        )
    except Exception as exc:
        err_str = str(exc)
        logger.warning("Login exception: %s", err_str)

        # robin_stocks raises various exceptions for MFA; detect them.
        if "mfa" in err_str.lower() or "two_factor" in err_str.lower():
            return {
                "status": "mfa_required",
                "code": "MFA_REQUIRED",
                "message": "MFA code required. Call rh_login again with the mfa_code parameter.",
                "action_required": "Provide the MFA code sent to your device.",
            }
        return {
            "status": "error",
            "code": "ROBINHOOD_API_ERROR",
            "message": f"Login failed: {err_str}",
            "action_required": "Check your credentials and try again.",
        }

    if not result:
        return {
            "status": "error",
            "code": "ROBINHOOD_API_ERROR",
            "message": "Login returned an empty response.",
            "action_required": "Check your credentials and try again.",
        }

    # Extract access token from the result dict.
    access_token: str | None = None
    if isinstance(result, dict):
        access_token = result.get("access_token")

    if not access_token:
        # Some MFA flows return a challenge response rather than a token.
        if isinstance(result, dict) and (
            "mfa_required" in result or result.get("mfa_code") == ""
        ):
            return {
                "status": "mfa_required",
                "code": "MFA_REQUIRED",
                "message": "MFA code required. Call rh_login again with the mfa_code parameter.",
                "action_required": "Provide the MFA code sent to your device.",
            }
        return {
            "status": "error",
            "code": "ROBINHOOD_API_ERROR",
            "message": "Login succeeded but no access token was returned.",
            "action_required": "Try logging in again.",
        }

    # Fetch account number.
    account_id = _get_account_number()

    token_data: dict[str, Any] = {
        "access_token": access_token,
        "account_id": account_id,
        "saved_at": time.time(),
    }
    if isinstance(result, dict):
        token_data["refresh_token"] = result.get("refresh_token", "")
        token_data["token_type"] = result.get("token_type", "Bearer")

    save_session(token_data)
    _session_loaded_at = time.time()
    _session_account = account_id

    logger.info("Login successful for account %s", account_id)
    return {"status": "authenticated", "account": account_id}


def logout() -> dict[str, Any]:
    """Revoke session and delete session file."""
    global _session_loaded_at, _session_account

    try:
        rh.logout()
    except Exception as exc:
        logger.warning("Logout API call failed: %s", exc)

    if SESSION_PATH.exists():
        try:
            SESSION_PATH.unlink()
            logger.info("Session file deleted")
        except Exception as exc:
            logger.warning("Could not delete session file: %s", exc)

    _session_loaded_at = None
    _session_account = None
    return {"status": "logged_out"}


def session_status() -> dict[str, Any]:
    """Return current session state without making a network call."""
    if _session_loaded_at is None:
        return {"authenticated": False, "account_number": None, "token_age_seconds": None}

    age = int(time.time() - _session_loaded_at)
    return {
        "authenticated": True,
        "account_number": _session_account,
        "token_age_seconds": age,
    }


def _get_account_number() -> str:
    try:
        profile = rh.account.load_account_profile()
        if isinstance(profile, dict):
            return profile.get("account_number", "unknown")
    except Exception:
        pass
    return "unknown"
