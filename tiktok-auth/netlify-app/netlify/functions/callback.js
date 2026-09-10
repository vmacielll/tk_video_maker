"use strict";

const https = require("https");

const TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/";
const SAVE_DIR = "/Users/vmaciel/tk_video_maker/tiktok-auth/python";

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function pyStr(value) {
  return (
    '"' +
    String(value == null ? "" : value)
      .replace(/\\/g, "\\\\")
      .replace(/"/g, '\\"')
      .replace(/\r/g, "\\r")
      .replace(/\n/g, "\\n") +
    '"'
  );
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
    "  body { margin: 0; padding: 2rem 1rem; font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #111; background: #f7f7f8; }\n" +
    "  main { max-width: 46rem; margin: 0 auto; background: #fff; border: 1px solid #e2e2e4; border-radius: 8px; padding: 2rem; }\n" +
    "  h1 { font-size: 1.4rem; margin: 0 0 1.25rem; }\n" +
    "  h2 { font-size: 1.05rem; margin: 1.75rem 0 0.5rem; }\n" +
    "  p { font-size: 0.95rem; }\n" +
    "  .ok { color: #0a7d32; font-weight: 600; }\n" +
    "  .bad { color: #b00020; font-weight: 600; }\n" +
    "  .error-box { margin: 1rem 0; padding: 1rem; border: 1px solid #b00020; border-radius: 6px; background: #fff5f6; color: #b00020; display: none; }\n" +
    "  pre { position: relative; margin: 0; padding: 1rem; background: #f2f2f4; border: 1px solid #e2e2e4; border-radius: 6px; overflow-x: auto; }\n" +
    "  code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.82rem; white-space: pre; }\n" +
    "  .block { margin-bottom: 0.75rem; }\n" +
    "  .copy { margin: 0 0 0.5rem; padding: 0.4rem 0.8rem; font: inherit; font-size: 0.8rem; font-weight: 600; color: #fff; background: #111; border: none; border-radius: 6px; cursor: pointer; }\n" +
    "  .copy:hover { background: #333; }\n" +
    "  a { color: #0b5fff; }\n" +
    "</style>\n</head>\n<body>\n<main>\n" +
    inner +
    "\n</main>\n</body>\n</html>\n"
  );
}

function requestToken(payload) {
  return new Promise(function (resolve, reject) {
    const body = JSON.stringify(payload);
    const req = https.request(
      TOKEN_URL,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
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

function buildSnippet(tokens) {
  return [
    "cd " + SAVE_DIR + " && python3 <<'PYEOF'",
    "import json, pathlib",
    'p = pathlib.Path("tiktok_tokens.json").resolve()',
    'data = json.loads(p.read_text()) if p.exists() else {}',
    "data.update({",
    '    "client_key": ' + pyStr(tokens.client_key) + ",",
    '    "client_secret": ' + pyStr(tokens.client_secret) + ",",
    '    "access_token": ' + pyStr(tokens.access_token) + ",",
    '    "refresh_token": ' + pyStr(tokens.refresh_token) + ",",
    '    "open_id": ' + pyStr(tokens.open_id) + ",",
    '    "scope": ' + pyStr(tokens.scope) + ",",
    '    "access_expires_at": ' + pyStr(tokens.access_expires_at) + ",",
    "})",
    'p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\\n")',
    'print("Updated:", p)',
    "PYEOF",
  ].join("\n");
}

function copyButton(targetId) {
  return (
    '<button class="copy" type="button" data-target="' +
    escapeHtml(targetId) +
    '">Copy</button>'
  );
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
  const snippet = buildSnippet(tokens);
  const stateJson = JSON.stringify(state);

  const inner =
    "<h1>Authorization successful</h1>\n" +
    '<div id="state-error" class="error-box">State validation failed &mdash; possible CSRF. Do not use these tokens.</div>\n' +
    '<div id="content">\n' +
    '<p class="ok">TikTok returned an access token.</p>\n' +
    "<h2>Tokens received</h2>\n" +
    '<div class="block">' +
    copyButton("tokens-json") +
    "<pre><code id=\"tokens-json\">" +
    escapeHtml(tokensJson) +
    "</code></pre></div>\n" +
    "<h2>Run this to save</h2>\n" +
    '<div class="block">' +
    copyButton("snippet") +
    "<pre><code id=\"snippet\">" +
    escapeHtml(snippet) +
    "</code></pre></div>\n" +
    '<p>Run the command from the directory shown. It writes the tokens to <code>tiktok_tokens.json</code> next to the tool.</p>\n' +
    "</div>\n" +
    "<script>\n" +
    "(function () {\n" +
    "  var expected = " +
    stateJson +
    ";\n" +
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
    "  }\n" +
    "  var buttons = document.querySelectorAll(\".copy\");\n" +
    "  for (var i = 0; i < buttons.length; i++) {\n" +
    "    buttons[i].addEventListener(\"click\", function () {\n" +
    '      var target = document.getElementById(this.getAttribute("data-target"));\n' +
    "      if (!target) { return; }\n" +
    "      var text = target.textContent;\n" +
    "      var btn = this;\n" +
    "      function done() { btn.textContent = \"Copied\"; setTimeout(function () { btn.textContent = \"Copy\"; }, 1500); }\n" +
    "      if (navigator.clipboard && navigator.clipboard.writeText) {\n" +
    "        navigator.clipboard.writeText(text).then(done, function () { window.prompt(\"Copy manually:\", text); });\n" +
    "      } else {\n" +
    "        window.prompt(\"Copy manually:\", text);\n" +
    "      }\n" +
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
