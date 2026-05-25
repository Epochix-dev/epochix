import { defineConfig } from 'vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

export default defineConfig({
  root: '.',
  base: '/',
  plugins: [viteSingleFile()],
  build: {
    outDir: 'dist-singlefile',
    emptyOutDir: true,
    target: 'es2020',
    assetsInlineLimit: 10_000_000,
    cssCodeSplit: false,
    rollupOptions: {
      input: 'index.html',
      output: {
        inlineDynamicImports: true,
      },
    },
  },
});
