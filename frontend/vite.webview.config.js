import { defineConfig } from 'vite';

/**
 * Webview build for the VS Code extension.
 *
 * The extension's webview runs under a strict Content-Security-Policy that
 * allows exactly ONE nonce'd <script>. So unlike the server build we must:
 *  - inline every dynamic import (Chart.js) into a single `main.js` — a lazy
 *    chunk would be both unreferenced and CSP-blocked at runtime;
 *  - emit a single, un-split `main.css`;
 *  - keep flat, predictable filenames so the loader can rewrite them to
 *    `webview.asWebviewUri(...)`.
 *
 * Output goes straight into the extension's `webview-dist/`. The built
 * `index.html` carries the full app markup, which the loader reads and adapts
 * (see epochix-vscode/src/webview/webview.html.ts).
 */
export default defineConfig({
  root: '.',
  base: './',
  build: {
    outDir: '../epochix-vscode/webview-dist',
    emptyOutDir: true,
    target: 'es2020',
    cssCodeSplit: false,
    rollupOptions: {
      input: 'index.html',
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'main.js',
        assetFileNames: (info) => {
          const name = info.name ?? '';
          return name.endsWith('.css') ? 'main.css' : 'assets/[name][extname]';
        },
      },
    },
  },
});
