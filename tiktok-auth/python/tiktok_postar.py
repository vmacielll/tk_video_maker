#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upload a video to TikTok via the Content Posting API (Direct Post).

This is the local half of the auto-posting tool: it assumes the OAuth flow
already ran (tokens in ``tiktok_tokens.json``, see ``tiktok_auth.py``) and
handles the three publishing steps:

    1. ``POST /v2/post/publish/video/init/`` — initialize the upload
    2. ``PUT <upload_url>`` with ``Content-Range`` — upload the file in chunks
    3. ``GET /v2/post/publish/status/fetch/`` — poll until processing ends

Design notes:
    * Stdlib only (``urllib``, ``json``, ``pathlib``, ``math``, ``time``).
    * Progress logs go to **stderr**; the final result is JSON on **stdout**
      so an AI agent (Hermes) can parse it.
    * Exit codes: 0 success, 1 user error, 2 auth error, 3 upload error.

CLI:
    python3 tiktok_postar.py VIDEO_PATH [--caption "..."] \
        [--caption-file PATH] [--privacy SELF_ONLY] [--no-wait]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import NoReturn

from tiktok_auth import AuthError, TOKENS_PATH, ensure_fresh_tokens


INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
DEFAULT_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_CHUNK_SIZE = 64 * 1024 * 1024  # 64 MB
MIN_CHUNK_SIZE = 5 * 1024 * 1024  # 5 MB (multi-chunk minimum)
POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 60
MAX_CAPTION_LENGTH = 2200
HTTP_TIMEOUT_SECONDS = 120

VALID_PRIVACY_LEVELS = (
    "SELF_ONLY",
    "PUBLIC_TO_EVERYONE",
    "MUTUAL_FOLLOW_FRIENDS",
    "FOLLOW_FOLLOWERS",
)

FAILED_STATUSES = {"FAIL", "PUBLISH_FAILED", "PROCESSING_FAILED"}


class UploadError(RuntimeError):
    """Raised when upload initialization, transfer, or polling fails.

    Subclasses ``RuntimeError`` so callers that catch plain ``RuntimeError``
    keep working, while the CLI can map it to exit code 3.
    """


def _stderr(message: str) -> None:
    """Progress log on stderr; stdout is reserved for the final JSON."""
    print(message, file=sys.stderr, flush=True)


def _http_request(
    method: str,
    url: str,
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> tuple[int, bytes]:
    """Perform an HTTP request and return ``(status_code, body_bytes)``.

    HTTP error responses are returned (not raised) so callers can surface
    status and body. Only transport-level failures raise :class:`UploadError`.
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
        raise UploadError(f"network error calling {url}: {exc.reason}") from exc


def _auth_headers(tokens: dict) -> dict:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Content-Type": "application/json",
    }


def _init_upload(tokens: dict, post_info: dict, source_info: dict) -> tuple[str, str]:
    """Initialize the direct-post upload. Returns ``(upload_url, publish_id)``."""
    body = json.dumps(
        {"post_info": post_info, "source_info": source_info}, ensure_ascii=False
    ).encode("utf-8")
    status, raw = _http_request("POST", INIT_URL, _auth_headers(tokens), body)
    text = raw.decode("utf-8", "replace")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UploadError(
            f"init failed: HTTP {status}, non-JSON response: {text[:300]}"
        ) from exc

    error = payload.get("error") or {}
    code = error.get("code")
    if code not in (None, "", "ok"):
        raise UploadError(
            f"init failed: HTTP {status}, error={code}: {error.get('message')}"
        )
    if status != 200:
        raise UploadError(f"init failed: HTTP {status}: {text[:300]}")

    data = payload.get("data") or {}
    upload_url = data.get("upload_url")
    publish_id = data.get("publish_id")
    if not upload_url or not publish_id:
        raise UploadError(
            f"init failed: missing upload_url/publish_id in response: {text[:300]}"
        )
    return upload_url, publish_id


def _upload_file(upload_url: str, video_path: pathlib.Path, chunk_size: int) -> int:
    """Upload ``video_path`` to ``upload_url`` in chunks. Returns chunk count."""
    total_size = video_path.stat().st_size
    if total_size <= 0:
        raise ValueError(f"video file is empty: {video_path}")
    if total_size > MAX_CHUNK_SIZE * 2:
        raise ValueError(
            f"video too large ({total_size} bytes); TikTok accepts at most "
            f"{MAX_CHUNK_SIZE * 2} bytes"
        )

    total_chunks = max(1, math.ceil(total_size / chunk_size))
    with video_path.open("rb") as handle:
        for index in range(total_chunks):
            start = index * chunk_size
            handle.seek(start)
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            end = start + len(chunk) - 1
            headers = {
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes {start}-{end}/{total_size}",
            }
            status, raw = _http_request("PUT", upload_url, headers, chunk)
            if status not in (200, 201, 206):
                detail = raw.decode("utf-8", "replace")
                raise UploadError(
                    f"upload chunk {index + 1}/{total_chunks} failed: "
                    f"HTTP {status}: {detail[:300]}"
                )
            _stderr(f"[chunk {index + 1}/{total_chunks}] uploaded {len(chunk)} bytes")
    return total_chunks


def _poll_status(
    tokens: dict, publish_id: str, timeout: int = POLL_TIMEOUT_SECONDS
) -> dict:
    """Poll the publish status until complete, failed, or timed out."""
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    url = STATUS_URL + "?" + urllib.parse.urlencode({"publish_id": publish_id})
    deadline = time.monotonic() + timeout
    attempt = 0

    while True:
        attempt += 1
        status, raw = _http_request("GET", url, headers, timeout=30)
        text = raw.decode("utf-8", "replace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise UploadError(
                f"status fetch returned non-JSON: HTTP {status}: {text[:300]}"
            ) from exc
        if status != 200:
            raise UploadError(f"status fetch failed: HTTP {status}: {text[:300]}")

        error = payload.get("error") or {}
        error_code = error.get("code")
        if error_code not in (None, "", "ok"):
            raise UploadError(
                f"status fetch failed: error={error_code}: {error.get('message')}"
            )

        data = payload.get("data") or {}
        current = data.get("status") or ""
        _stderr(f"[poll {attempt}] status={current or 'UNKNOWN'}")

        if current == "PUBLISH_COMPLETE":
            return data
        if current in FAILED_STATUSES or current.startswith("FAILED"):
            reason = (
                data.get("fail_reason")
                or data.get("fail_reason_message")
                or "unknown reason"
            )
            raise UploadError(
                f"TikTok processing failed (status={current}): {reason}"
            )
        if time.monotonic() >= deadline:
            raise UploadError(
                f"TikTok processing timed out after {timeout}s "
                f"(last status={current or 'UNKNOWN'})"
            )
        time.sleep(POLL_INTERVAL_SECONDS)


def post_video(
    video_path: pathlib.Path,
    caption: str,
    privacy_level: str = "SELF_ONLY",
    video_made_with_ai: bool = True,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    wait_for_completion: bool = True,
) -> dict:
    """Upload ``video_path`` to TikTok and optionally wait for processing."""
    path = pathlib.Path(video_path)
    if not path.exists():
        raise ValueError(f"video not found: {path}")
    if not path.is_file():
        raise ValueError(f"not a file: {path}")
    if not os.access(path, os.R_OK):
        raise ValueError(f"video is not readable: {path}")
    if not caption or not caption.strip():
        raise ValueError("caption must not be empty")
    if len(caption) > MAX_CAPTION_LENGTH:
        raise ValueError(
            f"caption too long ({len(caption)} chars); max is {MAX_CAPTION_LENGTH}"
        )
    if privacy_level not in VALID_PRIVACY_LEVELS:
        raise ValueError(
            f"invalid privacy_level {privacy_level!r}; expected one of "
            f"{', '.join(VALID_PRIVACY_LEVELS)}"
        )
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_size > MAX_CHUNK_SIZE:
        raise ValueError(
            f"chunk_size {chunk_size} exceeds the maximum of {MAX_CHUNK_SIZE} bytes"
        )

    _stderr("[1/5] Loading tokens (refresh if needed)...")
    tokens = ensure_fresh_tokens()

    total_size = path.stat().st_size
    if total_size <= 0:
        raise ValueError(f"video file is empty: {path}")

    total_chunk_count = max(1, math.ceil(total_size / chunk_size))
    if total_chunk_count == 1:
        # A single chunk may be smaller than the 5 MB multi-chunk minimum.
        effective_chunk_size = total_size
    else:
        if not (MIN_CHUNK_SIZE <= chunk_size <= MAX_CHUNK_SIZE):
            raise ValueError(
                f"chunk_size for a {total_chunk_count}-chunk upload must be "
                f"between {MIN_CHUNK_SIZE} and {MAX_CHUNK_SIZE} bytes"
            )
        effective_chunk_size = chunk_size

    post_info = {
        "title": caption,
        "privacy_level": privacy_level,
        "video_made_with_ai": video_made_with_ai,
        "disable_duet": False,
        "disable_comment": False,
        "disable_stitch": False,
    }
    source_info = {
        "source": "FILE_UPLOAD",
        "video_size": total_size,
        "chunk_size": effective_chunk_size,
        "total_chunk_count": total_chunk_count,
    }

    _stderr("[2/5] Initializing upload...")
    upload_url, publish_id = _init_upload(tokens, post_info, source_info)
    _stderr(f"       publish_id={publish_id}")

    _stderr(
        f"[3/5] Uploading {total_size} bytes in {total_chunk_count} chunk(s)..."
    )
    _upload_file(upload_url, path, effective_chunk_size)

    if wait_for_completion:
        _stderr("[4/5] Waiting for TikTok to process the video...")
        status_data = _poll_status(tokens, publish_id)
        status = status_data.get("status", "PUBLISH_COMPLETE")
    else:
        _stderr("[4/5] Skipping processing poll (--no-wait)")
        status = "UPLOADED_PENDING_PROCESSING"

    _stderr("[5/5] Done.")
    return {
        "publish_id": publish_id,
        "status": status,
        "video_path": str(path),
        "caption_length": len(caption),
        "privacy_level": privacy_level,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class _ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 (user error) instead of 2."""

    def error(self, message: str) -> NoReturn:  # noqa: D401 - argparse override
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _read_caption_file(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"caption file not found: {path}") from exc
    except OSError as exc:
        raise ValueError(f"could not read caption file {path}: {exc}") from exc


def _resolve_caption(args: argparse.Namespace) -> str:
    """Resolve the caption from --caption, --caption-file, or the sidecar .txt."""
    if args.caption is not None:
        caption = args.caption
    elif args.caption_file is not None:
        caption = _read_caption_file(pathlib.Path(args.caption_file))
    else:
        sidecar = pathlib.Path(args.video_path).with_suffix(".txt")
        if sidecar.is_file():
            _stderr(f"       using sidecar caption: {sidecar}")
            caption = _read_caption_file(sidecar)
        else:
            raise ValueError(
                "no caption provided and no sidecar .txt found; use --caption "
                "or --caption-file"
            )

    caption = caption.strip()
    if not caption:
        raise ValueError("caption is empty")
    return caption


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(
        description="Upload a video to TikTok via the Content Posting API."
    )
    parser.add_argument("video_path", help="Path to the .mp4 file to post.")
    caption_group = parser.add_mutually_exclusive_group()
    caption_group.add_argument(
        "--caption", default=None, help="Caption/title to post."
    )
    caption_group.add_argument(
        "--caption-file",
        default=None,
        help="Read the caption from this file (whitespace-trimmed).",
    )
    parser.add_argument(
        "--privacy",
        default="SELF_ONLY",
        choices=sorted(VALID_PRIVACY_LEVELS),
        help="Privacy level (default: SELF_ONLY).",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Skip status polling; return the publish_id right after upload.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Upload chunk size in bytes (default: {DEFAULT_CHUNK_SIZE}).",
    )
    args = parser.parse_args(argv)

    try:
        caption = _resolve_caption(args)
        result = post_video(
            video_path=pathlib.Path(args.video_path),
            caption=caption,
            privacy_level=args.privacy,
            chunk_size=args.chunk_size,
            wait_for_completion=not args.no_wait,
        )
    except ValueError as exc:
        _stderr(f"error: {exc}")
        return 1
    except AuthError as exc:
        _stderr(f"auth error: {exc}")
        return 2
    except UploadError as exc:
        _stderr(f"upload error: {exc}")
        return 3
    except RuntimeError as exc:
        _stderr(f"error: {exc}")
        return 3

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
