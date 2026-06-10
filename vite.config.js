import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'fs';
import { execSync } from 'child_process';

const toml = readFileSync('./pyproject.toml', 'utf8');
const appVersion = toml.match(/^version\s*=\s*"([^"]+)"/m)?.[1] ?? 'unknown';

let gitSha = 'unknown';
try { gitSha = execSync('git rev-parse --short HEAD').toString().trim(); } catch {}

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
    __GIT_SHA__: JSON.stringify(gitSha),
  },
  plugins: [react()],
  root: 'frontend-src',
  build: { outDir: '../dist', emptyOutDir: true },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api/': process.env.API_URL || 'http://localhost:5001',
    },
  },
});
