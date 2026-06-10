import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  define: { __APP_VERSION__: JSON.stringify('test'), __GIT_SHA__: JSON.stringify('test') },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./frontend-src/vitest.setup.js'],
    include: ['frontend-src/**/*.test.{js,jsx}'],
  },
});
