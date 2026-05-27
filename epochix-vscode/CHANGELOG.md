# Changelog — Epochix (VS Code Extension)

Notable changes to the extension. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The extension version tracks the Python package; bug fixes in the shared
frontend ship to both at once.

---

## [0.2.0] — 2026-05-26

### Added

- **Reproducible webview build** — new `npm run build:webview` in the shared
  frontend emits a single flat `main.js` + `main.css` with all dynamic imports
  inlined (Chart.js bundled in) so the strict webview CSP can admit it. The
  build runs automatically during `vsce package` via `vscode:prepublish`.
- **Webview loader reads the built `index.html`** instead of stamping out a
  bare `<div id=app>` shell, so the full app markup (sidebar, panels,
  sections) is preserved.
- **VS Code postMessage bridge** in the shared frontend — gated on
  `window.__EPOCHIX_VSCODE__`. Standalone mode now receives `init` / `frame` /
  `milestone` / `warning` / `complete` / `themeChange` events from the
  extension's StoryEngine and renders the core story.
- **LICENSE** file copied into the extension directory so the packaged
  `.vsix` carries a license alongside the code.

### Changed

- `.vscodeignore` excludes `**/*.map` (was just `*.map`) and `*.vsix` so the
  packaged extension is leaner.
- `vsce package` is now hermetic — no stale source maps, no extra files.

### Inherits all 0.2.0 dashboard improvements

The webview renders the shared epochix dashboard, so every fix in the
Python package's 0.2.0 release reaches extension users immediately:
secure-by-default CORS / write-auth / docs gating, ANSI-stripping parser,
detection-aware skill radar, live architecture detection during streaming,
PhD-level engineer panel (LR chart, multi-loss decomposition, best-epoch
markers), `epochix demo` onboarding, real-YOLO end-to-end verification.

See the Python package CHANGELOG for full details.

---

## [0.1.0] — 2026-05-22

First public release.

### Added

- Webview dashboard panel — opens with `Ctrl+Alt+M` / `Cmd+Alt+M`
- Sidecar mode — auto-discovers the Python `epochix` package and
  streams metrics from the local server
- Standalone mode — built-in TypeScript engine parses logs in-process
- Open Log File command (right-click `.log` files)
- Watch Active Terminal command — streams a live training session
- Compare Runs view
- Status-bar grade + phase indicator
- Tree-view of stored runs in the Explorer sidebar
