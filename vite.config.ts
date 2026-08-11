import path from 'path';
import fs from 'fs';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');

  // Self-hosted TLS: if certs/server.{key,crt} exist, serve HTTPS. Generated via
  // openssl with SubjectAltName IP:192.168.10.70 (see certs/). Disable by setting
  // VITE_HTTPS=false or removing the cert files.
  const certKey = path.resolve(__dirname, 'certs/server.key');
  const certCrt = path.resolve(__dirname, 'certs/server.crt');
  const httpsEnabled = env.VITE_HTTPS !== 'false' && fs.existsSync(certKey) && fs.existsSync(certCrt);
  const httpsOpts = httpsEnabled
    ? { key: fs.readFileSync(certKey), cert: fs.readFileSync(certCrt) }
    : undefined;
  // Default to 443 for HTTPS (so the app is reachable at https://192.168.10.70
  // with no port), else 3000. Override with VITE_PORT.
  const serverPort = Number(env.VITE_PORT) || (httpsEnabled ? 443 : 3000);

  return {
    server: {
      port: serverPort,
      host: '0.0.0.0',
      https: httpsOpts,
      watch: {
        // Exclude Rust build artifacts — Windows locks .exe files during compilation
        // and chokidar throws EBUSY trying to watch them.
        ignored: ['**/agent-install/omni-agent-rs/target/**'],
      },
      hmr: {
        overlay: true,
        // Use a dedicated port for HMR WebSocket so it doesn't compete
        // with the /socket.io proxy upgrade.
        protocol: httpsEnabled ? 'wss' : 'ws',
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
    optimizeDeps: {
      // Scan only the real app entry — by default Vite crawls every *.html
      // under the root, which picks up backend/venv (strawberry's
      // pathfinder.html) and aborts dependency pre-bundling.
      entries: ['index.html'],
    },
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
    build: {
      chunkSizeWarningLimit: 1500,
      outDir: 'dist-new',       // bypass permission-locked dist/
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/__tests__/setup.ts', './servers/src/__tests__/setup.ts'],
      exclude: [
        '**/node_modules/**',
        '**/dist/**',
        '**/.claude/worktrees/**',
        '**/.claude/plugins/**',
        'code-review-graph-main/**',
      ],
      include: ['src/**/*.{test,spec}.?(c|m)[jt]s?(x)', 'servers/**/*.{test,spec}.?(c|m)[jt]s?(x)'],
    }
  };
});
