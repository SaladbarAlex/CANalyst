import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // The dashboard talks to /api and Vite forwards it to FastAPI,
      // so there is no CORS setup to get wrong in development.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
