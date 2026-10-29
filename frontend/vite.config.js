import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  resolve: {
    // Windows junction（C:\...\WorkBuddy -> D:\WorkBuddy）下，
    // 禁用符号链接解析，让 Vite 直接用传入的符号路径，避免 realpath 导致的路径不一致。
    preserveSymlinks: true,
  },
  build: {
    rollupOptions: {
      input: { main: 'index.html' },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
