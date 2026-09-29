import { defineConfig } from 'vite';

// Fonts are inlined into the stylesheet in every build: an exported HTML
// report inlines the stylesheet's text, so a font referenced as a separate
// file would be missing from it. See src/themes/fonts.css.
const inlineFonts = (file) => (/\.woff2?$/.test(file) ? true : undefined);

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
    // The webview's CSP admits fonts only as data: URIs (webview.html.ts).
    assetsInlineLimit: inlineFonts,
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
