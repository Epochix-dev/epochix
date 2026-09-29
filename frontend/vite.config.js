import { defineConfig } from 'vite';

// Fonts are inlined into the stylesheet in every build: an exported HTML
// report inlines the stylesheet's text, so a font referenced as a separate
// file would be missing from it. See src/themes/fonts.css.
const inlineFonts = (file) => (/\.woff2?$/.test(file) ? true : undefined);

export default defineConfig({
  root: '.',
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2020',
    assetsInlineLimit: inlineFonts,
    rollupOptions: {
      input: 'index.html',
      output: {
        manualChunks: undefined,
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:7860',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:7860',
        ws: true,
        changeOrigin: true,
      },
      '/sse': {
        target: 'http://127.0.0.1:7860',
        changeOrigin: true,
      },
      '/v': {
        target: 'http://127.0.0.1:7860',
        changeOrigin: true,
      },
    },
  },
});
