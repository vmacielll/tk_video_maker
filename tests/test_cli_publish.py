"""Tests for the auto_gerar.py CLI publish flow (issue #2).

The seam under test is the CLI itself: we run `auto_gerar.py` as a subprocess
and assert on stdout JSON, exit code, and side-effects (files written).
"""

import os
import sys
import json
import tempfile
from pathlib import Path


# Make the worktree root importable so we can `import auto_gerar` directly
# from unit tests that exercise internal helpers.
WORKTREE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))


# --- Cycle 1: flag parsing ----------------------------------------------------


def test_help_shows_publish_and_audio_flags(cli_runner):
    """`auto_gerar.py --help` documents the new --publish and --audio flags."""
    result = cli_runner(["--help"])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "--publish" in result.stdout
    assert "--audio" in result.stdout


def test_help_describes_publish_and_audio(cli_runner):
    """The help text for --publish and --audio explains the allowed values."""
    result = cli_runner(["--help"])
    assert result.returncode == 0
    # The help text should mention the value choices
    assert "yes" in result.stdout.lower()
    assert "no" in result.stdout.lower()


# --- Cycle 2: audio resolution ----------------------------------------------


def test_resolve_audio_path_returns_none_when_off():
    """When audio=off, _resolve_audio_path returns None and does not call the searcher."""
    from auto_gerar import _resolve_audio_path

    called = []

    def fake_searcher(*args, **kwargs):
        called.append((args, kwargs))
        return []

    result = _resolve_audio_path("off", tema_obj={"busca": "x"}, searcher=fake_searcher)
    assert result is None
    assert called == [], "searcher must not be called when audio='off'"


def test_resolve_audio_path_returns_path_when_auto_and_options():
    """When audio=auto and the searcher returns options, _resolve_audio_path returns a downloaded file path."""
    from auto_gerar import _resolve_audio_path

    downloads = {}

    def fake_searcher(*args, **kwargs):
        return [
            {"id": 1, "title": "Track", "duration_str": "1:00", "url_download": "u1"},
        ]

    def fake_download(url, dest):
        downloads[url] = dest
        # Create the file so the path is "real"
        with open(dest, "wb") as f:
            f.write(b"x")

    result = _resolve_audio_path(
        "auto",
        tema_obj={"musica_busca": "ambient", "busca": "fallback"},
        searcher=fake_searcher,
        downloader=fake_download,
    )
    assert result is not None
    assert os.path.exists(result)
    assert downloads == {"u1": result}


def test_resolve_audio_path_falls_back_to_busca():
    """When tema has no musica_busca, _resolve_audio_path uses busca as the query."""
    from auto_gerar import _resolve_audio_path

    seen_queries = []

    def fake_searcher(query, n=5, chave=None):
        seen_queries.append(query)
        return []

    _resolve_audio_path(
        "auto",
        tema_obj={"busca": "fallback-query"},  # no musica_busca
        searcher=fake_searcher,
    )
    assert seen_queries == ["fallback-query"]


def test_resolve_audio_path_soft_fails_on_searcher_exception():
    """If the searcher raises, _resolve_audio_path returns None (soft fail)."""
    from auto_gerar import _resolve_audio_path

    def fake_searcher(*args, **kwargs):
        raise RuntimeError("network down")

    result = _resolve_audio_path(
        "auto",
        tema_obj={"busca": "x"},
        searcher=fake_searcher,
    )
    assert result is None


def test_resolve_audio_path_soft_fails_on_empty_results():
    """If the searcher returns no options, _resolve_audio_path returns None."""
    from auto_gerar import _resolve_audio_path

    result = _resolve_audio_path(
        "auto",
        tema_obj={"busca": "x"},
        searcher=lambda *a, **k: [],
    )
    assert result is None


# --- Cycle 3: token pre-check -----------------------------------------------


def test_pre_check_returns_unconfigured_when_tokens_missing(tmp_path):
    """When tiktok_tokens.json does not exist, _pre_check_tokens returns configured=False."""
    from auto_gerar import _pre_check_tokens

    result = _pre_check_tokens(tokens_path=tmp_path / "nope.json")
    assert result == {
        "configured": False,
        "expires_at": None,
        "scope_ok": False,
    }


def test_pre_check_returns_unconfigured_when_tokens_expired(tmp_tokens_dir):
    """When the token is expired, _pre_check_tokens returns configured=False."""
    from auto_gerar import _pre_check_tokens

    result = _pre_check_tokens(tokens_path=tmp_tokens_dir / "expired.json")
    assert result["configured"] is False
    assert result["scope_ok"] is False
    assert result["expires_at"] is not None


def test_pre_check_returns_configured_when_valid_with_scope(tmp_tokens_dir):
    """When the token is valid and the scope includes video.publish, _pre_check_tokens returns configured=True, scope_ok=True."""
    from auto_gerar import _pre_check_tokens

    result = _pre_check_tokens(tokens_path=tmp_tokens_dir / "valid.json")
    assert result["configured"] is True
    assert result["scope_ok"] is True
    assert result["expires_at"] == "2099-01-01T00:00:00.000Z"


def test_pre_check_marks_scope_not_ok_when_missing(tmp_tokens_dir):
    """When the token is valid but scope lacks video.publish, _pre_check_tokens returns scope_ok=False."""
    from auto_gerar import _pre_check_tokens

    result = _pre_check_tokens(tokens_path=tmp_tokens_dir / "missing_scope.json")
    assert result["configured"] is True
    assert result["scope_ok"] is False


def test_pre_check_does_not_leak_secrets(tmp_tokens_dir):
    """_pre_check_tokens result contains no token secrets (access_token, refresh_token, client_secret)."""
    from auto_gerar import _pre_check_tokens

    result = _pre_check_tokens(tokens_path=tmp_tokens_dir / "valid.json")
    keys = list(result.keys())
    for secret in ("access_token", "refresh_token", "client_secret"):
        assert secret not in keys
        assert secret not in str(result).lower()


# --- Cycle 4: publish subprocess invocation ---------------------------------


MOCK_POSTAR = str(WORKTREE_ROOT / "tests" / "fixtures" / "mock_tiktok_postar.py")


def _make_video(tmp_path: Path) -> Path:
    p = tmp_path / "fake.mp4"
    p.write_bytes(b"fake-video-bytes")
    return p


def test_invoke_publish_returns_success_block_on_exit_0(tmp_path):
    """When the postar subprocess exits 0, _invoke_publish_subprocess returns success=True, publish_id set."""
    from auto_gerar import _invoke_publish_subprocess

    video = _make_video(tmp_path)
    result = _invoke_publish_subprocess(
        video_path=video,
        postar_bin=MOCK_POSTAR,
        env={"MOCK_TIKTOK_POSTAR_RESULT": "success"},
    )
    assert result["attempted"] is True
    assert result["success"] is True
    assert result["publish_id"] is not None
    assert result["error"] is None
    assert result["error_type"] is None


def test_invoke_publish_maps_exit_1_to_user_error(tmp_path):
    """Exit 1 maps to error_type=user."""
    from auto_gerar import _invoke_publish_subprocess

    video = _make_video(tmp_path)
    result = _invoke_publish_subprocess(
        video_path=video,
        postar_bin=MOCK_POSTAR,
        env={"MOCK_TIKTOK_POSTAR_RESULT": "user_error"},
    )
    assert result["attempted"] is True
    assert result["success"] is False
    assert result["error_type"] == "user"
    assert result["publish_id"] is None


def test_invoke_publish_maps_exit_2_to_auth_error(tmp_path):
    """Exit 2 maps to error_type=auth."""
    from auto_gerar import _invoke_publish_subprocess

    video = _make_video(tmp_path)
    result = _invoke_publish_subprocess(
        video_path=video,
        postar_bin=MOCK_POSTAR,
        env={"MOCK_TIKTOK_POSTAR_RESULT": "auth_error"},
    )
    assert result["success"] is False
    assert result["error_type"] == "auth"


def test_invoke_publish_maps_exit_3_to_upload_error(tmp_path):
    """Exit 3 maps to error_type=upload."""
    from auto_gerar import _invoke_publish_subprocess

    video = _make_video(tmp_path)
    result = _invoke_publish_subprocess(
        video_path=video,
        postar_bin=MOCK_POSTAR,
        env={"MOCK_TIKTOK_POSTAR_RESULT": "upload_error"},
    )
    assert result["success"] is False
    assert result["error_type"] == "upload"


def test_invoke_publish_passes_video_path_to_subprocess(tmp_path):
    """The video path is passed as the first positional argument to postar."""
    from auto_gerar import _invoke_publish_subprocess

    video = _make_video(tmp_path)
    call_log = tmp_path / "calls.log"
    _invoke_publish_subprocess(
        video_path=video,
        postar_bin=MOCK_POSTAR,
        env={"MOCK_TIKTOK_POSTAR_RESULT": "success", "MOCK_CALL_LOG": str(call_log)},
    )
    log = call_log.read_text().strip()
    assert str(video) in log


def test_invoke_publish_passes_caption_when_given(tmp_path):
    """The caption is passed via --caption when provided."""
    from auto_gerar import _invoke_publish_subprocess

    video = _make_video(tmp_path)
    call_log = tmp_path / "calls.log"
    _invoke_publish_subprocess(
        video_path=video,
        caption="my caption",
        postar_bin=MOCK_POSTAR,
        env={"MOCK_TIKTOK_POSTAR_RESULT": "success", "MOCK_CALL_LOG": str(call_log)},
    )
    log = call_log.read_text()
    assert "--caption" in log
    assert "my caption" in log


def test_invoke_publish_handles_unexpected_exit_code(tmp_path):
    """An exit code outside 0/1/2/3 still produces a valid block, mapped to upload."""
    from auto_gerar import _invoke_publish_subprocess

    video = _make_video(tmp_path)
    # Use a one-liner that exits with code 5
    weird_script = tmp_path / "weird_postar.py"
    weird_script.write_text("#!/usr/bin/env python3\nimport sys; sys.exit(5)\n")
    result = _invoke_publish_subprocess(video_path=video, postar_bin=str(weird_script))
    assert result["success"] is False
    assert result["error_type"] in ("upload", "user")  # implementation choice; we accept either
    assert "5" in result["error"] or "exited" in result["error"].lower()


# --- Cycle 5: e2e CLI integration (fast paths only) ------------------------


def test_cli_invalid_tema_exits_with_clear_error(cli_runner):
    """A non-existent tema name produces a clear stderr error and a non-zero exit code."""
    result = cli_runner(["nonexistent-tema-name-xyz"])
    assert result.returncode != 0
    assert "não encontrado" in result.stderr or "not found" in result.stderr.lower()


def test_cli_publish_yes_with_no_tokens_fails_pre_check(cli_runner, tmp_path, monkeypatch):
    """When --publish=yes and tiktok_tokens.json is missing, the CLI exits with code 2 and a publish block."""
    # Point TOKENS_PATH at a tmp dir that does NOT contain tiktok_tokens.json.
    # The default path resolves relative to tiktok_auth.TOKENS_PATH; the simplest
    # way is to point TIKTOK_TOKENS_PATH if supported, or temporarily replace the
    # module's TOKENS_PATH attribute.
    import tiktok_auto_post.tiktok_auth as auth_mod
    monkeypatch.setattr(auth_mod, "TOKENS_PATH", tmp_path / "nope.json")

    result = cli_runner(["lei_da_atracao", "--publish=yes"], timeout=30)
    # Pre-check should fail before generation → no Groq/Pexels/ffmpeg calls.
    assert result.returncode == 2, f"stderr: {result.stderr!r}, stdout: {result.stdout!r}"
    payload = json.loads(result.stdout)
    assert payload["publish"]["error_type"] == "auth"
    assert payload["publish"]["success"] is False
    assert "tema" in payload  # the rest of the JSON is still emitted (with publish block)

