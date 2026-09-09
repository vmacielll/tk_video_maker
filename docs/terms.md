# Terms of Service

**Last updated:** September 9, 2026

## What this is

tk_video_maker is a self-hosted automation tool that generates vertical short videos (9:16) and publishes them to TikTok on behalf of the user. It is free, open-source, and runs entirely on infrastructure you control.

## How it works

The tool combines several services to produce each video:

1. **Groq** (LPU inference) generates the spoken phrases and the caption for each video based on a chosen theme.
2. **Pexels** provides free-license background images that match the theme.
3. **ffmpeg + Pillow** render the final `.mp4` (1080x1920, 30 fps) on your own machine.
4. **Backblaze B2** stores each rendered `.mp4` in a private bucket and produces a signed HTTPS URL valid for 24 hours. TikTok fetches the file from this URL via its Content Posting API.
5. **Postiz** (self-hosted) orchestrates the publish flow and the OAuth handshake with TikTok.
6. **TikTok** receives the signed URL, downloads the video, and posts it to the authorized account.

Each of these services is operated by an independent third party with its own terms:

- Groq: https://wow.groq.com/terms-of-use/
- Pexels: https://www.pexels.com/license/
- Backblaze B2: https://www.backblaze.com/terms_of_service.html
- Postiz (AGPL-3.0): https://github.com/gitroomhq/postiz-app/blob/main/LICENSE
- TikTok for Developers: https://developers.tiktok.com/terms-and-conditions

By using tk_video_maker you agree to also follow the terms of each linked service.

## What you are responsible for

- The content of the videos you choose to publish (themes, captions, edits).
- The TikTok account you connect and what it posts.
- Compliance with TikTok's Community Guidelines and Content Posting API rules.
- The legality of any third-party content (images from Pexels are royalty-free but still have attribution and use restrictions).
- Keeping your API keys (`segredos.txt`, environment variables) secret. Anyone with access to those keys can post on your behalf.

## What we do not do

- We do not collect analytics.
- We do not sell or share your data with anyone outside the services listed above.
- We do not moderate or review the content before publishing. The AI-generated phrases and captions may contain errors or content you do not intend. Review every video in TikTok's "drafts" or private mode before making it public.
- We do not guarantee any specific reach, engagement, or that TikTok will approve your developer app.

## Disclaimers

This software is provided "as is", without warranty of any kind, express or implied. The authors are not liable for any claim, damages, or other liability arising from the use of the software or from content posted via it.

If you publish via the TikTok Content Posting API while your developer app is unaudited, posts are forced to private (`SELF_ONLY`) visibility by TikTok until your app passes audit. After audit you may publish publicly, subject to TikTok's rules.

## Changes to these terms

We may update these terms. The date at the top will always reflect the latest revision. Material changes will be noted in the project's commit history.

## Contact

Open an issue at https://github.com/vmacielll/tk_video_maker/issues or contact the maintainer via the GitHub profile.
