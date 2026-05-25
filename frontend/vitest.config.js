import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // jsdom gives us window, location, WebSocket stub, etc.
    environment: 'jsdom',
    globals: true,
    coverage: {
      provider: 'v8',
      include: ['src/store.js', 'src/ws-client.js'],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 70,
        statements: 80,
      },
      reporter: ['text', 'lcov'],
    },
  },
});
