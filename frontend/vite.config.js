import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy /api to the FastAPI server so the browser sees one origin and CORS
// never enters the picture during the demo.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The Python virtualenv and the model cache live inside the project root
    // and hold well over a hundred thousand files. Left unignored, chokidar
    // walks them on every start and the dev server drops its client connection
    // repeatedly while anything touches .venv.
    watch: {
      ignored: ['**/.venv/**', '**/.cache/**', '**/fixtures/profiles/**'],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
