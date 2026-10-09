"""Shared pytest fixtures for the tk_video_maker test suite."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# Project root = parent of the tests/ directory. The worktree is checked out
# at .slim/worktrees/publish-flow/ but the .venv (with deps) lives at the main
# repo. Both are siblings under tk_video_maker/, so the worktree's project
# root is the worktree dir, and the venv is one level up.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_ROOT.parent.parent / ".venv" / "bin" / "python3"

# Fallback: if a venv isn't found one level up, walk up the tree.
if not VENV_PYTHON.exists():
    for ancestor in PROJECT_ROOT.parents:
        candidate = ancestor / ".venv" / "bin" / "python3"
        if candidate.exists():
            VENV_PYTHON = candidate
            break
    else:
        VENV_PYTHON = Path(sys.executable)


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def python_bin() -> Path:
    return VENV_PYTHON


@pytest.fixture
def tmp_tokens_dir(tmp_path: Path) -> Path:
    """A tmp dir pre-seeded with a valid tiktok_tokens.json and an expired one."""
    valid = {
        "client_key": "ck_test",
        "client_secret": "cs_test",
        "access_token": "at_test",
        "refresh_token": "rt_test",
        "open_id": "oid_test",
        "scope": "user.info.basic,video.publish,video.upload",
        "access_expires_at": "2099-01-01T00:00:00.000Z",
    }
    expired = dict(valid)
    expired["access_expires_at"] = "2020-01-01T00:00:00.000Z"
    (tmp_path / "valid.json").write_text(json.dumps(valid))
    (tmp_path / "expired.json").write_text(json.dumps(expired))
    (tmp_path / "missing_scope.json").write_text(
        json.dumps({**valid, "scope": "user.info.basic"})
    )
    return tmp_path


@pytest.fixture
def cli_runner(python_bin, project_root):
    """A callable that runs auto_gerar.py with given args and optional env."""
    def _run(args, env=None, timeout=120):
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        return subprocess.run(
            [str(python_bin), str(project_root / "auto_gerar.py"), *args],
            capture_output=True,
            text=True,
            env=full_env,
            cwd=str(project_root),
            timeout=timeout,
        )
    return _run
