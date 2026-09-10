#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OAuth token storage + refresh for the TikTok Content Posting API.

This is the local half of the auto-posting tool. The OAuth authorization
flow itself lives in ``../netlify-app/`` (deployed on Netlify); after the
callback, the tokens are written to ``tiktok_tokens.json`` next to this
file. This module only does two things:

    * load those tokens and refresh the access token when it is about to
      expire
    * persist refreshed tokens atomically

Everything uses the Python standard library (``urllib``), no pip packages.

CLI:
    python3 tiktok_auth.py show      # masked tokens as JSON
    python3 tiktok_auth.py check     # valid/expired + expiry time
    python3 tiktok_auth.py refresh   # force a refresh and save it
    python3 tiktok_auth.py path      # absolute path to tiktok_tokens.json
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


TOKENS_PATH = pathlib.Path(__file__).parent / "tiktok_tokens.json"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
REFRESH_SKEW_SECONDS = 300  # refresh if expiring within 5 minutes
HTTP_TIMEOUT_SECONDS = 30

# Fields that must never be printed in full by the CLI.
SECRET_FIELDS = ("access_token", "refresh_token", "client_secret")


class AuthError(RuntimeError):
    """Raised when OAuth state is missing or a token refresh fails.

    Subclasses ``RuntimeError`` so callers that catch plain ``RuntimeError``
    keep working, while the posting CLI can map it to a dedicated exit code.
    """


def _http_request(
    method: str,
    url: str,
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> tuple[int, bytes]:
    """Perform an HTTP request and return ``(status_code, body_bytes)``.

    HTTP error responses (4xx/5xx) are returned rather than raised so the
    caller can include the status and body in its own error message. Only
    transport-level failures raise.
    """
    request = urllib.request.Request(url, data=body, method=method)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise AuthError(f"network error calling {url}: {exc.reason}") from exc


def _parse_iso_datetime(value: object) -> datetime | None:
    """Parse an ISO 8601 string (with ``Z`` support) into an aware datetime.

    Returns ``None`` when the value is missing or unparseable.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def load_tokens(path: pathlib.Path = TOKENS_PATH) -> dict | None:
    """Load the token file. Return ``None`` if missing or invalid JSON."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def save_tokens(tokens: dict, path: pathlib.Path = TOKENS_PATH) -> None:
    """Atomically write tokens to ``path``.

    Writes to ``<path>.tmp`` in the same directory, then ``os.replace()`` so
    readers never observe a partially written file.
    """
    path = pathlib.Path(path)
    payload = json.dumps(tokens, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def is_expired(tokens: dict, skew_seconds: int = REFRESH_SKEW_SECONDS) -> bool:
    """Return ``True`` if the access token is expired or expiring soon.

    Fails safe: a missing or unparseable ``access_expires_at`` is treated as
    expired so callers refresh instead of using a stale token.
    """
    expires_at = _parse_iso_datetime(tokens.get("access_expires_at"))
    if expires_at is None:
        return True
    threshold = expires_at - timedelta(seconds=skew_seconds)
    return datetime.now(timezone.utc) >= threshold


def refresh_tokens(tokens: dict) -> dict:
    """Exchange the refresh token for a fresh access token.

    Returns a new token dict that keeps ``client_key``/``client_secret`` and
    updates the OAuth fields. Raises :class:`AuthError` on any failure.
    """
    payload = {
        "client_key": tokens.get("client_key", ""),
        "client_secret": tokens.get("client_secret", ""),
        "grant_type": "refresh_token",
        "refresh_token": tokens.get("refresh_token", ""),
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    status, raw = _http_request("POST", TOKEN_URL, headers, body)
    text = raw.decode("utf-8", "replace")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AuthError(
            f"token refresh failed: HTTP {status}, non-JSON response: {text[:300]}"
        ) from exc

    if status != 200 or not parsed.get("access_token"):
        detail = (
            parsed.get("error_description")
            or parsed.get("error")
            or parsed.get("message")
            or text[:300]
        )
        raise AuthError(f"token refresh failed: HTTP {status}: {detail}")

    expires_in = parsed.get("expires_in")
    try:
        expires_seconds = int(expires_in)
    except (TypeError, ValueError):
        raise AuthError(
            f"token refresh failed: invalid expires_in in response: {expires_in!r}"
        )

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)
    refreshed = {
        "client_key": tokens.get("client_key", ""),
        "client_secret": tokens.get("client_secret", ""),
        "access_token": parsed["access_token"],
        "refresh_token": parsed.get("refresh_token") or tokens.get("refresh_token", ""),
        "open_id": parsed.get("open_id") or tokens.get("open_id", ""),
        "scope": parsed.get("scope") or tokens.get("scope", ""),
        "access_expires_at": expires_at.isoformat(),
    }
    return refreshed


def ensure_fresh_tokens(path: pathlib.Path = TOKENS_PATH) -> dict:
    """Load tokens, refreshing and persisting them first if needed."""
    tokens = load_tokens(path)
    if tokens is None:
        raise AuthError(
            f"tiktok_tokens.json not found at {path.resolve()} — run the "
            "OAuth flow first via https://<netlify-site>/"
        )
    if is_expired(tokens):
        tokens = refresh_tokens(tokens)
        save_tokens(tokens, path)
    return tokens


def mask_tokens(tokens: dict) -> dict:
    """Return a copy with secrets reduced to their last 4 characters."""
    masked = dict(tokens)
    for field in SECRET_FIELDS:
        value = masked.get(field)
        if isinstance(value, str) and value:
            masked[field] = f"...{value[-4:]}"
        else:
            masked[field] = "<hidden>"
    return masked


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_show(_args: argparse.Namespace) -> int:
    tokens = load_tokens()
    if tokens is None:
        print(
            f"tiktok_tokens.json not found or invalid at {TOKENS_PATH.resolve()}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(mask_tokens(tokens), ensure_ascii=False, indent=2))
    return 0


def _cmd_check(_args: argparse.Namespace) -> int:
    tokens = load_tokens()
    if tokens is None:
        print(f"missing: {TOKENS_PATH.resolve()}")
        return 1
    expiry = tokens.get("access_expires_at") or "<unknown>"
    if is_expired(tokens):
        print(f"expired: {expiry}")
        return 1
    print(f"valid: {expiry}")
    return 0


def _cmd_refresh(_args: argparse.Namespace) -> int:
    tokens = load_tokens()
    if tokens is None:
        print(
            f"tiktok_tokens.json not found at {TOKENS_PATH.resolve()}",
            file=sys.stderr,
        )
        return 1
    try:
        refreshed = refresh_tokens(tokens)
    except AuthError as exc:
        print(f"refresh failed: {exc}", file=sys.stderr)
        return 1
    save_tokens(refreshed)
    print(json.dumps(mask_tokens(refreshed), ensure_ascii=False, indent=2))
    return 0


def _cmd_path(_args: argparse.Namespace) -> int:
    print(TOKENS_PATH.resolve())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage TikTok OAuth tokens (tiktok_tokens.json)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("show", help="Print masked tokens as JSON.")
    subparsers.add_parser("check", help="Print token validity and expiry.")
    subparsers.add_parser("refresh", help="Force a token refresh and save it.")
    subparsers.add_parser("path", help="Print the token file's absolute path.")

    args = parser.parse_args(argv)
    handlers = {
        "show": _cmd_show,
        "check": _cmd_check,
        "refresh": _cmd_refresh,
        "path": _cmd_path,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
