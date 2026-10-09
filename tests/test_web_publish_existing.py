"""Tests for the re-publish endpoint (POST /api/publish_existing)."""

import base64
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
import urllib.request


WORKTREE_ROOT = Path(__file__).resolve().parent.parent
STUBS_DIR = WORKTREE_ROOT / "tests" / "fixtures" / "stubs"
MOCK_POSTAR = WORKTREE_ROOT / "tests" / "fixtures" / "mock_tiktok_postar.py"


def _wait_for_server(port, timeout_s=10.0):
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _ephemeral_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]; s.close(); return p


def _valid_tokens():
    return {
        "client_key": "ck", "client_secret": "cs",
        "access_token": "at", "refresh_token": "rt", "open_id": "o",
        "scope": "video.publish",
        "access_expires_at": "2099-01-01T00:00:00.000Z",
    }


def _post_json(port, path, body, timeout_s=10):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def _start_server(out_dir, python_bin, mock_result="success"):
    """Spawn server.py with PYTHONPATH stubs and TIKTOK_POSTAR_BIN=mock.
    Returns (port, proc, real_tokens_backup, real_tokens_symlink, real_saida_symlink).
    The backup is the original tiktok_tokens.json content (or None); the
    symlinks must be torn down by the caller (see _stop_server).
    """
    real_tokens = WORKTREE_ROOT / "tiktok_tokens.json"
    # Snapshot the original (regular file) before unlinking — we restore it
    # in _stop_server so the test never destroys the developer's real tokens.
    backup = None
    if real_tokens.is_file() and not real_tokens.is_symlink():
        backup = real_tokens.read_bytes()
    if real_tokens.exists() or real_tokens.is_symlink():
        real_tokens.unlink()
    tokens_file = out_dir.parent / "tiktok_tokens.json"
    tokens_file.write_text(json.dumps(_valid_tokens()))
    os.symlink(tokens_file, real_tokens)

    real_saida = WORKTREE_ROOT / "saida_web"
    if real_saida.exists() or real_saida.is_symlink():
        if real_saida.is_symlink():
            real_saida.unlink()
        else:
            shutil.rmtree(real_saida)
    os.symlink(out_dir, real_saida)

    port = _ephemeral_port()
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(STUBS_DIR) + (os.pathsep + existing_pp if existing_pp else "")
    env["TIKTOK_POSTAR_BIN"] = str(MOCK_POSTAR)
    env["MOCK_TIKTOK_POSTAR_RESULT"] = mock_result

    proc = subprocess.Popen(
        [str(python_bin), str(WORKTREE_ROOT / "server.py"), str(port)],
        cwd=str(WORKTREE_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return port, proc, backup, real_tokens, real_saida


def _stop_server(proc, backup, real_tokens, real_saida):
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    # Tear down the symlinks.
    if real_tokens.is_symlink() or real_tokens.exists():
        real_tokens.unlink()
    if real_saida.is_symlink():
        real_saida.unlink()
    # Restore the developer's original tiktok_tokens.json (if any).
    if backup is not None:
        real_tokens.write_bytes(backup)


# --- Fixtures --------------------------------------------------------------


@pytest.fixture
def republish_server(tmp_path, python_bin):
    """Server with a pre-existing fake .mp4 in saida_web and a sidecar .txt."""
    out_dir = tmp_path / "saida_web"
    out_dir.mkdir()
    video_name = "video_existing_test.mp4"
    (out_dir / video_name).write_bytes(b"FAKE-EXISTING-MP4")
    (out_dir / (video_name + ".txt")).write_text("caption from sidecar\n", encoding="utf-8")

    port, proc, backup, real_tokens, real_saida = _start_server(out_dir, python_bin, "success")
    try:
        assert _wait_for_server(port), "server did not start"
        yield port, video_name
    finally:
        _stop_server(proc, backup, real_tokens, real_saida)


# --- Tests -----------------------------------------------------------------


def test_publish_existing_uses_sidecar_caption(republish_server):
    """Re-publish uses the sidecar .txt caption; no generation needed."""
    port, video_name = republish_server
    status, body = _post_json(port, "/api/publish_existing", {"video": video_name})
    assert status == 200, body
    assert body["ok"] is True
    assert body["publish_id"]


def test_publish_existing_legenda_overrides_sidecar(republish_server):
    """When 'legenda' is in the body, it overrides the sidecar (and is persisted to disk)."""
    port, video_name = republish_server
    status, body = _post_json(
        port, "/api/publish_existing",
        {"video": video_name, "legenda": "novo caption"},
    )
    assert status == 200, body
    assert body["ok"] is True
    # Confirm the sidecar was updated
    sidecar = WORKTREE_ROOT / "saida_web" / (video_name + ".txt")
    assert sidecar.read_text(encoding="utf-8").strip() == "novo caption"


def test_publish_existing_rejects_missing_video_field(republish_server):
    """Missing 'video' in body returns 400."""
    port, _ = republish_server
    status, body = _post_json(port, "/api/publish_existing", {})
    assert status == 400
    assert "video" in body.get("erro", "").lower()


def test_publish_existing_rejects_path_traversal(republish_server):
    """Filenames with '/' or '..' or no .mp4 extension are rejected."""
    port, _ = republish_server
    for bad in ["../etc/passwd", "../../saida_web/video.mp4", "subdir/video.mp4", "no_extension"]:
        status, body = _post_json(port, "/api/publish_existing", {"video": bad})
        assert status == 400, f"should reject {bad!r}: {body}"


def test_publish_existing_404_for_unknown_video(republish_server):
    """A well-formed filename that doesn't exist returns 404."""
    port, _ = republish_server
    status, body = _post_json(port, "/api/publish_existing", {"video": "ghost.mp4"})
    assert status == 404


def test_publish_existing_fails_when_no_legenda_no_sidecar(tmp_path, python_bin):
    """A video with no .txt sidecar and no 'legenda' in body returns 400."""
    out_dir = tmp_path / "saida_web_nosidecar"
    out_dir.mkdir()
    video_name = "video_no_caption.mp4"
    (out_dir / video_name).write_bytes(b"FAKE-MP4-NO-SIDECAR")

    port, proc, backup, real_tokens, real_saida = _start_server(out_dir, python_bin, "success")
    try:
        assert _wait_for_server(port)
        status, body = _post_json(port, "/api/publish_existing", {"video": video_name})
        assert status == 400
        assert "legenda" in body.get("erro", "").lower()
    finally:
        _stop_server(proc, backup, real_tokens, real_saida)


def test_publish_existing_propagates_postar_failure(republish_server, tmp_path, python_bin):
    """When tiktok_postar returns a non-zero exit code, the endpoint returns 500 + error_type."""
    port, video_name = republish_server
    # Stop the running server and start a new one with MOCK failure result
    # (republish_server fixture is the only one we have, so we cheat by
    # patching the env via a second spawn — simpler: re-use _start_server).
    out_dir = WORKTREE_ROOT / "saida_web"
    if out_dir.is_symlink():
        target = Path(os.readlink(out_dir))
    else:
        target = out_dir
    port2, proc, backup, real_tokens, real_saida = _start_server(target, python_bin, "upload_error")
    try:
        assert _wait_for_server(port2)
        status, body = _post_json(
            port2, "/api/publish_existing", {"video": video_name}
        )
        assert status == 500
        assert body["ok"] is False
        assert body.get("error_type") == "upload"
    finally:
        _stop_server(proc, backup, real_tokens, real_saida)
