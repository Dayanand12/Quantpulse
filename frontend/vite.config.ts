import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
// Backend URL is overridable via VITE_BACKEND_URL / VITE_BACKEND_WS_URL for
// running an isolated dev instance (e.g. verification runs) against a
// different backend port without touching the default.
const backendUrl = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:5000'
const backendWsUrl = process.env.VITE_BACKEND_WS_URL || 'ws://127.0.0.1:5000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true,
      },
      '/ws': {
        target: backendWsUrl,
        ws: true,
      },
    },
  },
})
