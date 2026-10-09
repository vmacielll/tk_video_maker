"""Tests for the Web pre-check endpoint (issue #3) and the underlying logic.

The seam under test is the HTTP endpoint AND the underlying tiktok_status()
function. The unit tests cover all four token states; the HTTP test confirms
the endpoint is wired up and returns valid JSON.
"""

import json
import sys
import time
from pathlib import Path

import pytest
import urllib.request


WORKTREE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))


# --- Unit tests: tiktok_status() covers the four states ---------------------


def test_tiktok_status_unconfigured_when_tokens_missing(tmp_path):
    """When the tokens file does not exist, tiktok_status returns configured=False, scope_ok=False, expires_at=None."""
    from tiktok_auto_post.tiktok_auth import tiktok_status

    result = tiktok_status(tmp_path / "nope.json")
    assert result == {
        "configured": False,
        "expires_at": None,
        "scope_ok": False,
    }


def test_tiktok_status_unconfigured_when_tokens_expired(tmp_tokens_dir):
    """When the token is expired, tiktok_status returns configured=False (and preserves expires_at)."""
    from tiktok_auto_post.tiktok_auth import tiktok_status

    result = tiktok_status(tmp_tokens_dir / "expired.json")
    assert result["configured"] is False
    assert result["scope_ok"] is False
    assert result["expires_at"] is not None


def test_tiktok_status_configured_when_valid_with_scope(tmp_tokens_dir):
    """When the token is valid and scope includes video.publish, tiktok_status returns configured=True, scope_ok=True."""
    from tiktok_auto_post.tiktok_auth import tiktok_status

    result = tiktok_status(tmp_tokens_dir / "valid.json")
    assert result["configured"] is True
    assert result["scope_ok"] is True
    assert result["expires_at"] == "2099-01-01T00:00:00.000Z"


def test_tiktok_status_marks_scope_not_ok_when_missing(tmp_tokens_dir):
    """When scope lacks video.publish, tiktok_status returns scope_ok=False but configured=True."""
    from tiktok_auto_post.tiktok_auth import tiktok_status

    result = tiktok_status(tmp_tokens_dir / "missing_scope.json")
    assert result["configured"] is True
    assert result["scope_ok"] is False


def test_tiktok_status_does_not_leak_secrets(tmp_tokens_dir):
    """tiktok_status result contains no token secrets."""
    from tiktok_auto_post.tiktok_auth import tiktok_status

    result = tiktok_status(tmp_tokens_dir / "valid.json")
    keys = list(result.keys())
    for secret in ("access_token", "refresh_token", "client_secret"):
        assert secret not in keys
        assert secret not in str(result).lower()


# --- HTTP integration test: GET /api/tiktok/status --------------------------


def _wait_for_server(port: int, timeout_s: float = 10.0) -> bool:
    """Poll the server until it accepts a TCP connection (any HTTP response)."""
    import socket
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.1)
    return False


@pytest.fixture
def running_server(tmp_path, python_bin):
    """Start server.py on an ephemeral port with a temp TOKENS_PATH; yield the port; tear down."""
    import os
    import socket
    import subprocess

    # Point tiktok_auth at a tmp file the server can read.
    tokens_file = tmp_path / "tiktok_tokens.json"
    valid = {
        "client_key": "ck_test",
        "client_secret": "cs_test",
        "access_token": "at_test",
        "refresh_token": "rt_test",
        "open_id": "oid_test",
        "scope": "user.info.basic,video.publish,video.upload",
        "access_expires_at": "2099-01-01T00:00:00.000Z",
    }
    tokens_file.write_text(json.dumps(valid))

    # Pick an ephemeral port by binding socket 0.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    # Symlink tiktok_tokens.json into the worktree so tiktok_auth (which reads
    # the default path relative to the script) finds our valid file.
    real_tokens = WORKTREE_ROOT / "tiktok_tokens.json"
    symlink_target = tmp_path / "real_tokens_link"
    if real_tokens.exists() or real_tokens.is_symlink():
        real_tokens.unlink()
    try:
        os.symlink(tokens_file, real_tokens)
        proc = subprocess.Popen(
            [str(python_bin), str(WORKTREE_ROOT / "server.py"), str(port)],
            cwd=str(WORKTREE_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            if not _wait_for_server(port):
                stdout, stderr = proc.communicate(timeout=1)
                raise RuntimeError(
                    f"server did not start on port {port}.\n"
                    f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
                )
            yield port, tokens_file
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    finally:
        if real_tokens.is_symlink():
            real_tokens.unlink()


def test_endpoint_returns_200_with_json_body(running_server):
    """GET /api/tiktok/status returns 200 with a JSON body containing the three documented fields."""
    port, _ = running_server
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/tiktok/status", timeout=2
    ) as resp:
        assert resp.status == 200
        body = json.loads(resp.read().decode("utf-8"))
    assert "configured" in body and isinstance(body["configured"], bool)
    assert "expires_at" in body
    assert "scope_ok" in body and isinstance(body["scope_ok"], bool)


def test_endpoint_returns_configured_true_for_valid_tokens(running_server):
    """When the tokens file is valid + has the scope, the endpoint reports configured=True and scope_ok=True."""
    port, _ = running_server
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/tiktok/status", timeout=2
    ) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    assert body["configured"] is True
    assert body["scope_ok"] is True
    assert body["expires_at"] == "2099-01-01T00:00:00.000Z"


def test_endpoint_does_not_leak_secrets_in_response(running_server):
    """The HTTP response body contains no token secrets."""
    port, _ = running_server
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/tiktok/status", timeout=2
    ) as resp:
        body_bytes = resp.read()
    text = body_bytes.decode("utf-8")
    for secret in ("at_test", "rt_test", "cs_test"):
        assert secret not in text, f"response leaked secret: {secret!r}"
