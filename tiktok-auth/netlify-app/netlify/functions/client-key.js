"use strict";

// Returns the configured TikTok client key as JSON, or an empty string
// if the environment variable is not set. Used by the authorize page
// to avoid forcing the user to copy/paste the client key from the
// TikTok dev dashboard.
//
// Cache-Control: no-store so env var updates take effect immediately
// after a redeploy (and so the key never gets cached in a CDN).

exports.handler = async function () {
  const clientKey = process.env.TIKTOK_CLIENT_KEY || "";
  return {
    statusCode: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store"
    },
    body: JSON.stringify({ client_key: clientKey })
  };
};