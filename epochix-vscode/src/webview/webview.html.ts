/**
 * Returns the HTML shell for the Epochix WebView panel.
 *
 * In sidecar mode the webview navigates directly to the server's iframe URL.
 * In standalone mode it loads the vendored frontend bundle from webview-dist/.
 */
import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";

export interface WebviewHtmlOptions {
  extensionUri: vscode.Uri;
  webview: vscode.Webview;
  /** If set, embed an iframe pointing at the sidecar server. */
  sidecarUrl?: string;
  theme: "light" | "dark";
  locale: string;
}

export function buildWebviewHtml(opts: WebviewHtmlOptions): string {
  const { extensionUri, webview, sidecarUrl, theme, locale } = opts;

  // Sidecar mode: simple iframe — no CSP issues, server handles everything.
  if (sidecarUrl) {
    return `<!DOCTYPE html>
<html lang="${locale}" data-theme="${theme}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Epochix</title>
  <style>
    body, html { margin: 0; padding: 0; height: 100vh; overflow: hidden; background: #0f0f10; }
    iframe { width: 100%; height: 100vh; border: none; }
  </style>
</head>
<body>
  <iframe src="${sidecarUrl}" allowfullscreen></iframe>
</body>
</html>`;
  }

  // Standalone mode: read the vendored, built index.html (which carries the
  // FULL app markup the frontend mounts into) and adapt it for the webview —
  // rewrite asset URLs to `asWebviewUri`, inject the CSP + nonce, and expose
  // the VS Code API bridge before the bundle runs.
  const distUri = vscode.Uri.joinPath(extensionUri, "webview-dist");
  const nonce = getNonce();
  const indexPath = path.join(distUri.fsPath, "index.html");

  let html: string;
  try {
    html = fs.readFileSync(indexPath, "utf-8");
  } catch {
    return buildMissingBundleHtml(theme, locale);
  }

  const scriptUri = webview
    .asWebviewUri(vscode.Uri.joinPath(distUri, "main.js"))
    .toString();
  const styleUri = webview
    .asWebviewUri(vscode.Uri.joinPath(distUri, "main.css"))
    .toString();

  // Point the document at the resolved theme/locale.
  html = html.replace(
    /<html[^>]*>/,
    `<html lang="${locale}" data-theme="${theme}">`,
  );

  // Rewrite the built relative asset refs to webview-resource URIs, dropping
  // the `crossorigin` attribute (not meaningful for vscode-resource URIs).
  html = html
    .replace(/\s*crossorigin/g, "")
    .replace(/(?:\.\/)?main\.js/g, scriptUri)
    .replace(/(?:\.\/)?main\.css/g, styleUri);

  // Add the nonce to the module entry script so the CSP admits it.
  html = html.replace(
    /<script type="module"/,
    `<script type="module" nonce="${nonce}"`,
  );

  // Strict CSP + the VS Code API bridge, injected into <head>. `connect-src
  // 'none'` because standalone mode is fed entirely via postMessage. Inline
  // styles (the @property block + Google Fonts) need 'unsafe-inline'.
  const csp = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${webview.cspSource} https: data:; style-src ${webview.cspSource} 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; script-src 'nonce-${nonce}'; connect-src 'none';">`;
  const bridge = `<script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    window.__EPOCHIX_VSCODE__ = vscode;
    window.__EPOCHIX_THEME__ = ${JSON.stringify(theme)};
    window.__EPOCHIX_LOCALE__ = ${JSON.stringify(locale)};
  </script>`;
  html = html.replace(/<\/head>/, `${csp}\n${bridge}\n</head>`);

  return html;
}

/** Fallback shown when the webview bundle hasn't been built/vendored yet. */
function buildMissingBundleHtml(
  theme: "light" | "dark",
  locale: string,
): string {
  return `<!DOCTYPE html>
<html lang="${locale}" data-theme="${theme}">
<head><meta charset="UTF-8"><title>Epochix</title>
<style>body{font-family:system-ui,sans-serif;padding:2rem;color:#cbd5e1;background:#0f1424}
code{background:#1e293b;padding:2px 6px;border-radius:4px}</style></head>
<body>
  <h2>Dashboard bundle not found</h2>
  <p>The webview assets are missing. Build them with:</p>
  <p><code>cd frontend &amp;&amp; npm run build:webview</code></p>
</body>
</html>`;
}

/** Resolve the asset file path relative to webview-dist/. */
export function resolveAsset(
  extensionUri: vscode.Uri,
  ...segments: string[]
): string {
  return path.join(extensionUri.fsPath, "webview-dist", ...segments);
}

function getNonce(): string {
  let text = "";
  const possible =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}
