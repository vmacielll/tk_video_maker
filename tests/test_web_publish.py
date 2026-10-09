"""Tests for the Web SSE publish endpoint (issue #5).

The seam under test is the full HTTP + SSE flow: start the server, POST to
/api/publish, consume the text/event-stream, assert on the events. The
end-to-end pipeline (nucleo / pexels / gemini / openverse_audio) is replaced
by stubs via PYTHONPATH so the test is fast and deterministic.
"""

import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import urllib.request


WORKTREE_ROOT = Path(__file__).resolve().parent.parent
STUBS_DIR = WORKTREE_ROOT / "tests" / "fixtures" / "stubs"
MOCK_POSTAR = WORKTREE_ROOT / "tests" / "fixtures" / "mock_tiktok_postar.py"


# A 1x1 transparent PNG (smallest valid PNG). The test doesn't care about the
# pixels — the nucleo stub writes a fake .mp4 file regardless of input.
TINY_PNG = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _wait_for_server(port: int, timeout_s: float = 10.0) -> bool:
    """Poll the server until it accepts a TCP connection."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.1)
    return False


def _ephemeral_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _read_sse_events(response, timeout_s: float = 30.0):
    """Yield (event_type, data_dict) parsed from an SSE response stream.

    Reads line-by-line; yields an event when a blank line is seen.
    Stops when the connection closes or the timeout elapses.
    """
    buffer = ""
    deadline = time.time() + timeout_s
    # Use a thread to read with a timeout, so we don't block forever.
    chunks = []

    def reader():
        try:
            while True:
                chunk = response.read(1)
                if not chunk:
                    break
                chunks.append(chunk.decode("utf-8", errors="replace"))
        except Exception:
            pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    while time.time() < deadline:
        # Coalesce chunks into a buffer
        while chunks:
            buffer += chunks.pop(0)
        # Emit complete events (separated by \n\n or by trailing \n\n on a single \n)
        while "\n\n" in buffer:
            event_block, buffer = buffer.split("\n\n", 1)
            event_type = "message"
            data_parts = []
            for line in event_block.split("\n"):
                if line.startswith("event:"):
                    event_type = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    data_parts.append(line[len("data:"):].strip())
            if data_parts:
                try:
                    yield event_type, json.loads("\n".join(data_parts))
                except json.JSONDecodeError:
                    pass
        # If the connection closed, drain and stop
        if not t.is_alive() and not chunks and not buffer:
            break
        time.sleep(0.05)


def _valid_tokens() -> dict:
    return {
        "client_key": "ck_test",
        "client_secret": "cs_test",
        "access_token": "at_test",
        "refresh_token": "rt_test",
        "open_id": "oid_test",
        "scope": "user.info.basic,video.publish,video.upload",
        "access_expires_at": "2099-01-01T00:00:00.000Z",
    }


@pytest.fixture
def publish_server(tmp_path, python_bin):
    """Start server.py with stub nucleo/pexels/gemini/openverse_audio on PYTHONPATH.

    Yields (port, tokens_file, output_dir). The server writes fake .mp4 to
    output_dir.
    """
    tokens_file = tmp_path / "tiktok_tokens.json"
    tokens_file.write_text(json.dumps(_valid_tokens()))

    out_dir = tmp_path / "saida_web"
    out_dir.mkdir()

    port = _ephemeral_port()

    # Symlink tiktok_tokens.json into the worktree so tiktok_auth (which reads
    # the default path relative to the script) finds our valid file.
    real_tokens = WORKTREE_ROOT / "tiktok_tokens.json"
    if real_tokens.exists() or real_tokens.is_symlink():
        real_tokens.unlink()
    os.symlink(tokens_file, real_tokens)

    # Build env: PYTHONPATH prepended with stubs so server imports stubs first
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(STUBS_DIR) + (os.pathsep + existing_pp if existing_pp else "")
    # TIKTOK_POSTAR_BIN points at the mock postar from #2
    env["TIKTOK_POSTAR_BIN"] = str(MOCK_POSTAR)
    env["MOCK_TIKTOK_POSTAR_RESULT"] = "success"  # default

    proc = subprocess.Popen(
        [str(python_bin), str(WORKTREE_ROOT / "server.py"), str(port)],
        cwd=str(WORKTREE_ROOT),
        env=env,
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
        yield port, tokens_file, out_dir
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        if real_tokens.is_symlink():
            real_tokens.unlink()


def _post_sse(port, payload, timeout_s=20):
    """POST JSON to /api/publish and return the SSE response (still streaming)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/publish",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Don't use a context manager — we want to keep the stream open to read events.
    response = urllib.request.urlopen(req, timeout=timeout_s)
    return response


def _event_types(events):
    return [e[0] for e in events]


# --- Acceptance scenario 1: publish=true, valid tokens, full sequence ------


def test_publish_true_emits_full_event_sequence(publish_server):
    """POST /api/publish with publish=true and valid tokens emits started -> generating -> generated -> publishing -> completed."""
    port, _tokens, _out_dir = publish_server
    payload = {
        "imagens": [base64.b64encode(TINY_PNG).decode("ascii")],
        "textos": "Linha 1\nLinha 2\nLinha 3",
        "publish": True,
    }
    response = _post_sse(port, payload, timeout_s=15)
    try:
        events = list(_read_sse_events(response, timeout_s=15))
    finally:
        response.close()

    types = _event_types(events)
    assert "started" in types, f"missing 'started' in {types}"
    assert "generating" in types
    assert "generated" in types
    assert "publishing" in types
    assert "completed" in types
    # Order: started must come first; completed must be last (in this slice).
    assert types[0] == "started"
    assert types[-1] == "completed"
    # No error
    assert "error" not in types

    # The started event carries the tiktok_status
    started_event = next(d for t, d in events if t == "started")
    assert "tiktok_status" in started_event
    assert started_event["tiktok_status"]["configured"] is True
    assert started_event["tiktok_status"]["scope_ok"] is True
    # The started event carries a job_id
    job_id = started_event.get("job_id")
    assert job_id, "started event missing job_id"
    # The completed event carries a publish_id
    completed_event = next(d for t, d in events if t == "completed")
    assert completed_event.get("publish_id")


# --- Acceptance scenario 2: publish=false, terminates after generated -------


def test_publish_false_terminates_after_generated(publish_server):
    """POST /api/publish with publish=false emits up to generated; no publishing / completed (publish path)."""
    port, _, _ = publish_server
    payload = {
        "imagens": [base64.b64encode(TINY_PNG).decode("ascii")],
        "textos": "Linha 1\nLinha 2",
        "publish": False,
    }
    response = _post_sse(port, payload, timeout_s=15)
    try:
        events = list(_read_sse_events(response, timeout_s=15))
    finally:
        response.close()

    types = _event_types(events)
    assert "started" in types
    assert "generated" in types
    # publish path: no 'publishing' / no 'completed' (with publish_id)
    assert "publishing" not in types
    # A "completed" event might still be emitted at the end (without publish_id)
    # — per the spec it's expected only on the publish path. So we check explicitly.
    completed_with_publish_id = [d for t, d in events if t == "completed" and d.get("publish_id")]
    assert not completed_with_publish_id
    assert "error" not in types


# --- Acceptance scenario 3: publish=true, postar fails, error event ---------


def test_publish_true_with_postar_failure_emits_error(publish_server, tmp_path, python_bin):
    """When tiktok_postar.py fails (mocked), the SSE stream ends with an error event and the video is preserved."""
    port, _, out_dir = publish_server
    # Restart the server with MOCK_TIKTOK_POSTAR_RESULT=upload_error
    # We can't change env on a running subprocess, so we spawn a second one.
    # (Simpler than reworking the fixture.)
    tokens_file = tmp_path / "tiktok_tokens.json"
    tokens_file.write_text(json.dumps(_valid_tokens()))

    real_tokens = WORKTREE_ROOT / "tiktok_tokens.json"
    if real_tokens.exists() or real_tokens.is_symlink():
        real_tokens.unlink()
    os.symlink(tokens_file, real_tokens)

    port2 = _ephemeral_port()
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(STUBS_DIR) + (os.pathsep + existing_pp if existing_pp else "")
    env["TIKTOK_POSTAR_BIN"] = str(MOCK_POSTAR)
    env["MOCK_TIKTOK_POSTAR_RESULT"] = "upload_error"

    proc = subprocess.Popen(
        [str(python_bin), str(WORKTREE_ROOT / "server.py"), str(port2)],
        cwd=str(WORKTREE_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert _wait_for_server(port2), "second server did not start"

        payload = {
            "imagens": [base64.b64encode(TINY_PNG).decode("ascii")],
            "textos": "Linha 1\nLinha 2",
            "publish": True,
        }
        response = _post_sse(port2, payload, timeout_s=15)
        try:
            events = list(_read_sse_events(response, timeout_s=15))
        finally:
            response.close()

        types = _event_types(events)
        assert "started" in types
        assert "generated" in types
        assert "publishing" in types
        assert "error" in types
        assert "completed" not in types

        # Error event has the right shape
        error_event = next(d for t, d in events if t == "error")
        assert error_event.get("error_type") == "upload"
        assert error_event.get("error")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        if real_tokens.is_symlink():
            real_tokens.unlink()


# --- Acceptance scenario 4: re-attach replays events -----------------------


def test_stream_endpoint_replays_stored_events(publish_server):
    """GET /api/publish/stream?job_id=X replays the events already stored in the JobStore."""
    port, _, _ = publish_server

    # First, create a job and append some events via the JobStore (which the
    # server is using). This is the "fast-forward" scenario: the job is already
    # done; the re-attach should just replay the events.
    import urllib.request
    # Hit the pre-check endpoint to confirm the server is up
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/tiktok/status", timeout=2) as r:
        assert r.status == 200

    # Access the server's JOB_STORE via a small admin endpoint? No — we don't
    # want to add a test-only endpoint. Instead, run a real publish job first
    # to populate the store, then re-attach.
    payload = {
        "imagens": [base64.b64encode(TINY_PNG).decode("ascii")],
        "textos": "Linha 1\nLinha 2",
        "publish": False,  # fast (no subprocess)
    }
    response = _post_sse(port, payload, timeout_s=15)
    try:
        events = list(_read_sse_events(response, timeout_s=15))
    finally:
        response.close()
    # Pick the first event's job_id
    started = next(d for t, d in events if t == "started")
    job_id = started["job_id"]

    # Now re-attach to that job — the job should already be done, so the
    # response just replays the stored events.
    re = urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/publish/stream?job_id={job_id}", timeout=10
    )
    try:
        replayed = list(_read_sse_events(re, timeout_s=10))
    finally:
        re.close()

    replayed_types = _event_types(replayed)
    # Should at least contain the events that were originally generated.
    assert "started" in replayed_types
    assert "generated" in replayed_types


# --- Bonus: video is preserved on disk when post fails (save-as-fallback) ---


def test_publish_failure_preserves_video_on_disk(publish_server, tmp_path, python_bin):
    """When tiktok_postar fails, the generated .mp4 remains on disk (save-as-fallback)."""
    port, _, out_dir = publish_server
    # Use the second-server pattern with MOCK_TIKTOK_POSTAR_RESULT=upload_error
    tokens_file = tmp_path / "tiktok_tokens.json"
    tokens_file.write_text(json.dumps(_valid_tokens()))

    real_tokens = WORKTREE_ROOT / "tiktok_tokens.json"
    if real_tokens.exists() or real_tokens.is_symlink():
        real_tokens.unlink()
    os.symlink(tokens_file, real_tokens)

    port2 = _ephemeral_port()
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(STUBS_DIR) + (os.pathsep + existing_pp if existing_pp else "")
    env["TIKTOK_POSTAR_BIN"] = str(MOCK_POSTAR)
    env["MOCK_TIKTOK_POSTAR_RESULT"] = "upload_error"

    proc = subprocess.Popen(
        [str(python_bin), str(WORKTREE_ROOT / "server.py"), str(port2)],
        cwd=str(WORKTREE_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert _wait_for_server(port2), "second server did not start"

        payload = {
            "imagens": [base64.b64encode(TINY_PNG).decode("ascii")],
            "textos": "Linha 1\nLinha 2",
            "publish": True,
        }
        response = _post_sse(port2, payload, timeout_s=15)
        try:
            list(_read_sse_events(response, timeout_s=15))
        finally:
            response.close()

        # After the error, the fake .mp4 should still be on disk.
        # The stub nucleo.gerar_video writes to saida_dir from opcoes.
        mp4s = list(out_dir.glob("*.mp4"))
        # The nucleo stub writes to saida_dir which is the server's saida_web.
        # Find any .mp4 in the worktree's saida_web
        all_mp4s = list((WORKTREE_ROOT / "saida_web").glob("*.mp4"))
        assert all_mp4s, "no .mp4 was written — save-as-fallback failed"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        if real_tokens.is_symlink():
            real_tokens.unlink()
        # Cleanup the fake .mp4
        for p in (WORKTREE_ROOT / "saida_web").glob("*.mp4"):
            try:
                p.unlink()
            except OSError:
                pass
