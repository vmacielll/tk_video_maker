#!/usr/bin/env python3
"""Mock tiktok_postar.py for tests.

Reads MOCK_TIKTOK_POSTAR_RESULT from env to choose behavior:
- success (default): exit 0, JSON with publish_id
- user_error: exit 1
- auth_error: exit 2
- upload_error: exit 3

Logs the call to a file (MOCK_CALL_LOG) so tests can verify invocation.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone


CALL_LOG = os.environ.get("MOCK_CALL_LOG", "/dev/null")
RESULT = os.environ.get("MOCK_TIKTOK_POSTAR_RESULT", "success")


def _log_call(argv: list, exit_code: int) -> None:
    try:
        with open(CALL_LOG, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "argv": argv,
                        "exit_code": exit_code,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                )
                + "\n"
            )
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Mock tiktok_postar.py for tests")
    ap.add_argument("video_path", help="Path to the .mp4 to upload")
    ap.add_argument("--caption", default=None)
    ap.add_argument("--caption-file", default=None)
    ap.add_argument("--privacy", default="SELF_ONLY")
    ap.add_argument("--no-wait", action="store_true")
    args = ap.parse_args()

    argv = sys.argv[1:]

    if RESULT == "success":
        payload = {
            "publish_id": "v2.mock." + os.urandom(4).hex(),
            "status": "PUBLISH_COMPLETE",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        _log_call(argv, 0)
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if RESULT == "user_error":
        _log_call(argv, 1)
        print("user error: bad input", file=sys.stderr)
        return 1

    if RESULT == "auth_error":
        _log_call(argv, 2)
        print("auth error: token rejected", file=sys.stderr)
        return 2

    if RESULT == "upload_error":
        _log_call(argv, 3)
        print("upload error: network failed", file=sys.stderr)
        return 3

    _log_call(argv, 1)
    print(f"unknown MOCK_TIKTOK_POSTAR_RESULT: {RESULT}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
