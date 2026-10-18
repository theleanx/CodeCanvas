import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // Keeps the frontend talking to '/api/...' in dev, with the real
      // FastAPI backend (uvicorn on :8000) behind it. Avoids hardcoding a
      // base URL in every fetch call and sidesteps CORS in local dev.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
