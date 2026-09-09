# Privacy Policy

**Last updated:** September 9, 2026

## What data tk_video_maker handles

Because tk_video_maker is self-hosted, all your data lives on your own machine. The tool itself does not run a server that other people connect to, does not have a database you do not control, and does not collect telemetry.

The data involved in a typical run is:

- **Theme / topic input** — the subject you choose for a video (for example "lei da atracao"). Sent to Groq to generate phrases and a caption.
- **Generated phrases and caption** — produced by Groq based on your theme. Sent back to your machine and written to disk next to the video file.
- **Background image** — fetched from Pexels using a free-license search query derived from your theme.
- **Rendered video file** — a `.mp4` produced locally by ffmpeg + Pillow on your machine.
- **TikTok access token** — issued by TikTok after you authorize the app via OAuth. Stored in your local Postiz database (PostgreSQL, Docker volume on your machine).
- **Posted video + caption** — handed to TikTok together with the signed B2 URL of the rendered video.

## What we do not collect

- We do not run analytics, tracking pixels, or third-party cookies.
- We do not log your activity to any external server.
- We do not sell or transfer your data to advertisers, brokers, or anyone not listed below.

## Third-party services that receive data

The tool itself is offline. The third parties involved, and what they receive, are:

| Service | What it receives | Why | Their privacy policy |
|---|---|---|---|
| **Groq** | The theme you selected, and the prompts to generate phrases and a caption | To produce the video content | https://wow.groq.com/privacy-policy/ |
| **Pexels** | The image-search query derived from your theme | To find royalty-free background photos | https://www.pexels.com/privacy-policy/ |
| **Backblaze B2** | The rendered `.mp4` file, stored in a private bucket you own | To host the file temporarily so TikTok can fetch it via HTTPS | https://www.backblaze.com/company/privacy.html |
| **Postiz** | The same data above, plus the TikTok OAuth callback | To orchestrate the publish flow | https://docs.postiz.com/privacy |
| **TikTok** | The video (via the signed B2 URL), the caption, and any flags you set (`video_made_with_ai = true`, privacy level) | To publish the post on the authorized TikTok account | https://www.tiktok.com/legal/privacy-policy |

Each of those services operates under its own privacy policy. tk_video_maker cannot control what they do with the data once it leaves your machine, but the data sent is limited to what each service strictly needs to perform its part.

## Cookies

The tool itself sets no cookies. The Postiz web UI may set cookies on its own domain (`http://localhost:4007` by default, or the tunnel URL during setup) for session management. Those cookies never leave the Postiz instance running on your machine.

## Where data lives on your side

- `segredos.txt` (or your `.env`) — your API keys. Gitignored. Never sent to GitHub.
- `~/.hermes/.env` — your OpenRouter key for Hermes. Never sent to GitHub.
- The Postiz Docker volume — your TikTok OAuth tokens.
- The Backblaze B2 bucket — your rendered `.mp4` files.
- `saida_auto/` (gitignored) — the local copy of each rendered video before upload.

You can delete any of these at any time. Deleting the B2 bucket also deletes every uploaded video. Rotating the OpenRouter, Groq, Pexels, or TikTok keys invalidates them immediately.

## AI-generated content disclosure

Every video produced by the tool is generated with AI (text via Groq, image composition via Pillow, video assembly via ffmpeg). The tool sets the `video_made_with_ai = true` flag on every post so TikTok displays the "AI-generated" label automatically. This is required by TikTok's Content Posting API rules.

## Your rights

- **Access** — all the data above lives on your machine and your own cloud accounts. You can inspect it any time.
- **Deletion** — delete the local files, the B2 bucket, the Docker volume, or the entire `tk_video_maker` directory at any time.
- **Revoke TikTok access** — go to TikTok Settings > Security > Apps > "Postiz Local" > Revoke. The token stored in your Postiz database becomes invalid immediately and Postiz will stop being able to post on your behalf.
- **Portability** — everything is plain text or open formats (Markdown, JSON, MP4). Nothing is locked into a proprietary format.

## Changes

We may update this policy. The date at the top will always reflect the latest revision. Material changes will be noted in the project's commit history.

## Contact

See the project repository at https://github.com/vmacielll/tk_video_maker for maintainer contact information.
