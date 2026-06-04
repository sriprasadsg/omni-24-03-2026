import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  return {
    server: {
      port: 3000,
      host: '0.0.0.0',
      hmr: {
        overlay: true,
        // Use a dedicated port for HMR WebSocket so it doesn't compete
        // with the /socket.io proxy upgrade on port 3000.
        port: 24678,
        clientPort: 24678,
      },
      proxy: {
        '/api': {
          target: env.VITE_PROXY_TARGET || 'http://127.0.0.1:5000',
          changeOrigin: true,
          ws: true,       // proxy WebSocket upgrades for /api/tunnel/* and /api/ws/*
          rewrite: (path) => path.replace(/^\/api/, '/api'),
        },
        '/static': {
          target: env.VITE_PROXY_TARGET || 'http://127.0.0.1:5000',
          changeOrigin: true,
        },
        '/socket.io': {
          target: env.VITE_PROXY_TARGET || 'http://127.0.0.1:5000',
          ws: true,
          changeOrigin: true,
        },
        '/health': {
          target: env.VITE_PROXY_TARGET || 'http://127.0.0.1:5000',
          changeOrigin: true,
        }
      }
    },
    plugins: [react()],
    define: {
      // API keys must NEVER be inlined into the browser bundle.
      // Gemini calls are proxied through the backend (/api/ai/... endpoints).
      // Remove VITE_GEMINI_API_KEY from .env to prevent accidental exposure.
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      }
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/__tests__/setup.ts'],
    }
  };
});
