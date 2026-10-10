import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ command }) => ({
  plugins: [react()],
  // GitHub Pages project site path; dev server stays at / for convenience.
  base: command === 'build' ? '/Deterministic-FIX-explainer-with-bounded-AI-assistance/' : '/',
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
}));
