"use strict";

const https = require("https");

const TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/";

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function pageShell(title, inner) {
  return (
    "<!DOCTYPE html>\n" +
    '<html lang="en">\n<head>\n<meta charset="utf-8">\n' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n' +
    "<title>" +
    escapeHtml(title) +
    "</title>\n" +
    "<style>\n" +
    '  body { margin: 0; padding: 2rem 1rem; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #111; background: #f7f7f8; }\n' +
    "  main { max-width: 46rem; margin: 0 auto; background: #fff; border: 1px solid #e2e2e4; border-radius: 8px; padding: 2rem; }\n" +
    "  h1 { font-size: 1.4rem; margin: 0 0 1.25rem; }\n" +
    "  h2 { font-size: 1.05rem; margin: 1.75rem 0 0.5rem; }\n" +
    "  p { font-size: 0.95rem; }\n" +
    "  ul { padding-left: 1.25rem; }\n" +
    "  li { font-size: 0.95rem; margin: 0.25rem 0; }\n" +
    "  .ok { color: #0a7d32; font-weight: 600; }\n" +
    "  .bad { color: #b00020; font-weight: 600; }\n" +
    "  .error-box { margin: 1rem 0; padding: 1rem; border: 1px solid #b00020; border-radius: 6px; background: #fff5f6; color: #b00020; display: none; }\n" +
    "  .warning-box { margin: 1.5rem 0; padding: 1rem 1.25rem; border: 2px solid #b00020; border-radius: 6px; background: #fff5f6; color: #5a0010; }\n" +
    "  .warning-box strong { color: #b00020; display: block; margin-bottom: 0.5rem; font-size: 1rem; }\n" +
    "  .warning-box ul { margin: 0.5rem 0 0 0; }\n" +
    "  pre { position: relative; margin: 0; padding: 1rem; background: #f2f2f4; border: 1px solid #e2e2e4; border-radius: 6px; overflow-x: auto; }\n" +
    "  code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.82rem; white-space: pre; }\n" +
    "  .download-button { display: inline-block; padding: 0.7rem 1.25rem; background: #111; color: #fff; text-decoration: none; font-weight: 600; border-radius: 6px; font-size: 0.95rem; margin: 0.5rem 0; }\n" +
    "  .download-button:hover { background: #333; }\n" +
    "  a { color: #0b5fff; }\n" +
    "</style>\n</head>\n<body>\n<main>\n" +
    inner +
    "\n</main>\n</body>\n</html>\n"
  );
}

function requestToken(payload) {
  return new Promise(function (resolve, reject) {
    const body = new URLSearchParams(payload).toString();
    const req = https.request(
      TOKEN_URL,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      function (res) {
        let raw = "";
        res.setEncoding("utf8");
        res.on("data", function (chunk) {
          raw += chunk;
        });
        res.on("end", function () {
          let parsed = null;
          try {
            parsed = JSON.parse(raw);
          } catch (err) {
            reject(
              new Error(
                "Non-JSON response (" +
                  res.statusCode +
                  "): " +
                  raw.slice(0, 500)
              )
            );
            return;
          }
          resolve({ statusCode: res.statusCode, data: parsed });
        });
      }
    );
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

function errorPage(statusCode, heading, message) {
  const inner =
    "<h1>" +
    escapeHtml(heading) +
    "</h1>\n" +
    '<p class="bad">' +
    escapeHtml(message) +
    "</p>\n" +
    '<p><a href="/">Back to the authorization page</a></p>';
  return {
    statusCode: statusCode,
    headers: { "Content-Type": "text/html; charset=utf-8" },
    body: pageShell(heading, inner),
  };
}

exports.handler = async function (event) {
  const query = event.queryStringParameters || {};
  const code = query.code;
  const state = query.state || "";

  if (!code) {
    return errorPage(
      400,
      "Authorization failed",
      "No authorization code was received from TikTok. This usually means access was denied, the redirect was interrupted, or this URL was opened directly. Start again from the authorization page."
    );
  }

  const headers = event.headers || {};
  const host = headers.host || headers.Host || "";
  const proto =
    headers["x-forwarded-proto"] || headers["X-Forwarded-Proto"] || "https";
  const origin = proto + "://" + host;
  const redirectUri = origin + "/oauth/callback";

  let result;
  try {
    result = await requestToken({
      client_key: process.env.TIKTOK_CLIENT_KEY,
      client_secret: process.env.TIKTOK_CLIENT_SECRET,
      code: code,
      grant_type: "authorization_code",
      redirect_uri: redirectUri,
    });
  } catch (err) {
    return errorPage(
      502,
      "Token exchange failed",
      "Could not reach TikTok to exchange the authorization code: " +
        (err && err.message ? err.message : String(err))
    );
  }

  const data = result.data || {};
  if (
    result.statusCode < 200 ||
    result.statusCode >= 300 ||
    !data.access_token
  ) {
    const detail =
      data.error_description ||
      data.error ||
      data.message ||
      "HTTP " + result.statusCode;
    return errorPage(
      502,
      "Token exchange failed",
      "TikTok rejected the token exchange: " + detail
    );
  }

  const expiresIn = Number(data.expires_in) || 0;
  const tokens = {
    client_key: process.env.TIKTOK_CLIENT_KEY,
    client_secret: process.env.TIKTOK_CLIENT_SECRET,
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    open_id: data.open_id,
    scope: data.scope,
    access_expires_at: new Date(
      Date.now() + expiresIn * 1000
    ).toISOString(),
  };

  const tokensJson = JSON.stringify(tokens, null, 2);
  const stateJson = JSON.stringify(state);

  const inner =
    "<h1>Authorization successful</h1>\n" +
    '<div id="state-error" class="error-box">State validation failed &mdash; possible CSRF. Do not use these tokens.</div>\n' +
    '<div id="content">\n' +
    '<p class="ok">TikTok returned an access token.</p>\n' +
    "<h2>Save the tokens to your project</h2>\n" +
    "<p>Click the button below to download <code>tiktok_tokens.json</code>, then move the downloaded file to the <strong>root of your project repository</strong> &mdash; the same folder that contains <code>tiktok_auto_post/</code>. If a <code>tiktok_tokens.json</code> already exists there, this will overwrite it.</p>\n" +
    '<p><a class="download-button" id="download-link" href="#" download="tiktok_tokens.json">&#x2B07; Download tiktok_tokens.json</a></p>\n' +
    "<h2>File contents (reference)</h2>\n" +
    "<pre><code>" +
    escapeHtml(tokensJson) +
    "</code></pre>\n" +
    "<h2>After saving</h2>\n" +
    "<p>Your Python scripts read the file automatically. Verify with:</p>\n" +
    "<pre><code>python3 tiktok_auto_post/tiktok_auth.py check</code></pre>\n" +
    '<div class="warning-box">\n' +
    '<strong>&#9888; Sensitive data &mdash; treat this file like a password.</strong>\n' +
    "<ul>\n" +
    "<li>Never share it. Never paste it in chat, email, or screenshots.</li>\n" +
    "<li>Never commit it. The file is already in <code>.gitignore</code>, so git will refuse to add it.</li>\n" +
    "<li>If you suspect it leaked, revoke the app in TikTok Settings &rarr; Security &rarr; Apps, then redo this flow to generate fresh tokens.</li>\n" +
    "</ul>\n" +
    "</div>\n" +
    "</div>\n" +
    "<script>\n" +
    "(function () {\n" +
    "  var expected = " + stateJson + ";\n" +
    "  var params = new URLSearchParams(window.location.search);\n" +
    '  var received = params.get("state") || "";\n' +
    "  var stored = null;\n" +
    '  try { stored = sessionStorage.getItem("tiktok_oauth_state"); } catch (e) {}\n' +
    "  var ok = received && stored && received === stored && received === expected;\n" +
    "  if (!ok) {\n" +
    '    var content = document.getElementById("content");\n' +
    '    if (content) { content.style.display = "none"; }\n' +
    '    var warn = document.getElementById("state-error");\n' +
    '    if (warn) { warn.style.display = "block"; }\n' +
    "    return;\n" +
    "  }\n" +
    "  var tokensJson = " + JSON.stringify(tokensJson) + ";\n" +
    '  var link = document.getElementById("download-link");\n' +
    "  if (link) {\n" +
    "    link.addEventListener(\"click\", function (e) {\n" +
    "      e.preventDefault();\n" +
    "      var blob = new Blob([tokensJson], { type: 'application/json' });\n" +
    "      var url = URL.createObjectURL(blob);\n" +
    "      var a = document.createElement('a');\n" +
    "      a.href = url;\n" +
    "      a.download = 'tiktok_tokens.json';\n" +
    "      document.body.appendChild(a);\n" +
    "      a.click();\n" +
    "      document.body.removeChild(a);\n" +
    "      URL.revokeObjectURL(url);\n" +
    "    });\n" +
    "  }\n" +
    "})();\n" +
    "</script>";

  return {
    statusCode: 200,
    headers: { "Content-Type": "text/html; charset=utf-8" },
    body: pageShell("Authorization successful", inner),
  };
};