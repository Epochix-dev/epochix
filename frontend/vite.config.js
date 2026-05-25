import { defineConfig } from 'vite';

export default defineConfig({
  root: '.',
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2020',
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
