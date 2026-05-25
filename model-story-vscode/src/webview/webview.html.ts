/**
 * Returns the HTML shell for the Model Story WebView panel.
 *
 * In sidecar mode the webview navigates directly to the server's iframe URL.
 * In standalone mode it loads the vendored frontend bundle from webview-dist/.
 */
import * as vscode from "vscode";
import * as path from "path";

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
  <title>Model Learning Story</title>
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

  // Standalone mode: load vendored webview-dist bundle.
  const distUri = vscode.Uri.joinPath(extensionUri, "webview-dist");
  const nonce = getNonce();

  // Resolve asset URIs (main.js and main.css from dist)
  const scriptUri = webview.asWebviewUri(
    vscode.Uri.joinPath(distUri, "main.js"),
  );
  const styleUri = webview.asWebviewUri(
    vscode.Uri.joinPath(distUri, "main.css"),
  );

  return `<!DOCTYPE html>
<html lang="${locale}" data-theme="${theme}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none';
             style-src ${webview.cspSource} 'nonce-${nonce}';
             script-src 'nonce-${nonce}';
             img-src ${webview.cspSource} data:;
             connect-src 'none';">
  <title>Model Learning Story</title>
  <link rel="stylesheet" href="${styleUri.toString()}">
  <script nonce="${nonce}">
    // Expose VS Code API before the bundle loads
    const vscode = acquireVsCodeApi();
    window.__MS_VSCODE__ = vscode;
    window.__MS_THEME__ = ${JSON.stringify(theme)};
    window.__MS_LOCALE__ = ${JSON.stringify(locale)};
  </script>
</head>
<body>
  <div id="app"></div>
  <script nonce="${nonce}" src="${scriptUri.toString()}"></script>
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
