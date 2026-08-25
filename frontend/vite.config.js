import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { env } from 'node:process'

// https://vitejs.dev/config/
export default defineConfig({
  // GitHub Pages project sites need a subpath, e.g. /P-081-fe-preview/
  base: env.VITE_BASE_PATH || '/',
  plugins: [
    react(),
    tailwindcss()
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: false,
    allowedHosts: true,
    // Same-origin in development, so the app can use relative /api paths and the
    // thumbnail URLs the API returns work unchanged. Also keeps CORS out of the
    // dev loop entirely.
    proxy: {
      '/api': {
        target: env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    css: true
  }
})
