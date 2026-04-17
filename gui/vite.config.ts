import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/run': 'http://localhost:8000',
      '/stream': 'http://localhost:8000',
      '/pause': 'http://localhost:8000',
      '/abort': 'http://localhost:8000',
      '/resume': 'http://localhost:8000',
      '/review-queue': 'http://localhost:8000',
      '/status': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
