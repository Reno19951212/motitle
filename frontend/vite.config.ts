/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api':       { target: 'http://localhost:5001', changeOrigin: true },
      '/socket.io': { target: 'http://localhost:5001', changeOrigin: true, ws: true },
      '/fonts':     { target: 'http://localhost:5001', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes('/pages/Proofread/')) return 'Proofread';
          if (id.includes('node_modules')) {
            if (id.includes('react-router')) return 'vendor-router';
            if (id.includes('@radix-ui') || id.includes('lucide-react')) return 'vendor-ui';
            if (id.includes('react-hook-form') || id.includes('@hookform') || id.includes('zod')) return 'vendor-forms';
            if (id.includes('@dnd-kit')) return 'vendor-dnd';
            if (id.includes('socket.io') || id.includes('engine.io')) return 'vendor-socket';
            if (id.includes('zustand')) return 'vendor-state';
            if (id.includes('react-dom') || id.includes('react/') || id.includes('scheduler')) return 'vendor-react';
          }
          return undefined;
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/tests/setup.ts',
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', 'dist', 'tests-e2e'],
  },
});
