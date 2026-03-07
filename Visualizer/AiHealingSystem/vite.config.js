import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: [['babel-plugin-react-compiler']],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      // FastAPI backend (error analysis, logs, WebSocket, etc.)
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // AST visualization (now served by FastAPI)
      '/upload': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/parse': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/languages': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
