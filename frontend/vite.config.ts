import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ command, mode }) => ({
  plugins: [react()],
  // GitHub Pages project site path; dev server stays at / for convenience.
  base: command === 'build' ? '/Deterministic-FIX-explainer-with-bounded-AI-assistance/' : '/',
  server: {
    proxy: {
      '/api': loadEnv(mode, '.', 'VITE_').VITE_API_TARGET || 'http://127.0.0.1:8000',
    },
  },
}));
