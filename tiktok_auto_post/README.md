# TikTok auto-posting — Python module

## What this is

This is the **local Python half** of the TikTok auto-posting tool. It does two
things and nothing else:

- **refresh** the OAuth access token when it is about to expire
- **upload** a video to TikTok via the Content Posting API (Direct Post)

The OAuth **authorization flow** (the part where a human logs in to TikTok)
lives in `../tiktok-auth/` and is deployed on Netlify. When that flow finishes,
the callback page offers a **Download tiktok_tokens.json** button — save the
downloaded file to the **root of the project repo** (the same folder that
contains this `tiktok_auto_post/` directory). That file is the single source
of truth for OAuth state.

No pip packages: Python **3.10+** standard library only.

Files:

| File | Purpose |
| --- | --- |
| `tiktok_auth.py` | Token storage, expiry check, refresh, atomic save |
| `tiktok_postar.py` | CLI that uploads a video and polls until processed |

`tiktok_tokens.json` lives at the **project root** (not here), is created by
the OAuth callback flow, and is gitignored.

## Setup

1. Deploy / open the Netlify authorization page (in `../tiktok-auth/netlify-app/`).
2. Complete the TikTok login. The callback page offers a **Download tiktok_tokens.json** button.
3. Move the downloaded file to the **project root** (the same folder that contains `tiktok_auto_post/`). If a previous `tiktok_tokens.json` is there, it's overwritten. The file should contain these 7 fields:

   ```json
   {
     "client_key": "...",
     "client_secret": "...",
     "access_token": "...",
     "refresh_token": "...",
     "open_id": "...",
     "scope": "video.publish",
     "access_expires_at": "2026-09-11T14:23:00.000Z"
   }
   ```

4. Confirm it worked:

   ```sh
   python3 tiktok_auth.py check
   ```

If `check` says `expired`, the next call to `tiktok_postar.py` will refresh it
automatically (or run `python3 tiktok_auth.py refresh`).

## Quick start

```sh
# 1. Is the token valid?
python3 tiktok_auth.py check

# 2. Post a generated video. Because a sidecar
#    saida_auto/video_20260910_142300.txt exists next to the .mp4,
#    the caption is picked up automatically.
python3 tiktok_postar.py ../saida_auto/video_20260910_142300.mp4

# 3. Post with an explicit caption.
python3 tiktok_postar.py video.mp4 --caption "Hello world" --privacy SELF_ONLY
```

> Until TikTok audits and approves the `video.publish` scope, posts are forced
> to `SELF_ONLY` regardless of `--privacy`. The flag is accepted for the future.

## How Hermes invokes this

When generating **and** posting in one shot, the workflow is:

1. From the repo root, generate the video (the gerador prints JSON on stdout):

   ```sh
   python3 ../auto_gerar.py <tema>
   ```

   Its JSON includes `arquivo_local` (the `.mp4`) and `legenda` (the caption).
   The caption is also written to `<arquivo_local>.txt`.

2. Post it. Use `--caption-file` to be explicit about the caption source:

   ```sh
   python3 tiktok_postar.py <arquivo_local> --caption-file <arquivo_local>.txt
   ```

   Returns JSON on **stdout** with `publish_id` and `status`.

Rules for the caller (Hermes):

- Progress logs go to **stderr**; the final result is a single JSON object on
  **stdout**. Parse stdout only.
- Check the **exit code** before trusting the JSON (see below).
- A sidecar `<VIDEO_PATH>.txt` is read automatically only when neither
  `--caption` nor `--caption-file` is passed.
- `--caption` and `--caption-file` are mutually exclusive.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success — JSON result on stdout |
| `1` | User error — bad arguments, missing/unreadable file, empty/oversized caption |
| `2` | Auth error — `tiktok_tokens.json` missing, or refresh failed |
| `3` | Upload error — init, chunk upload, or processing poll failed |

## Troubleshooting

- **`401 Unauthorized`** — the access token was rejected. Run
  `python3 tiktok_auth.py check`; if expired, `python3 tiktok_auth.py refresh`.
- **`403 Forbidden`** — the `video.publish` scope was not granted. Re-check the
  TikTok app configuration and redo the OAuth flow.
- **`tiktok_tokens.json not found`** — run the OAuth flow at the Netlify page
  first (see Setup).
- **`rate limit`** — TikTok is throttling. Wait a minute and retry.
- **`video too large`** — TikTok accepts at most 128 MB per video. Re-encode
  smaller.
- **`TikTok processing timed out`** — processing took longer than 60s. The
  upload itself likely succeeded; re-check with the `publish_id` or retry.
