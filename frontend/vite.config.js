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
      output: {
        // 把体积大且更新频率低的库拆成独立 chunk，利用浏览器缓存
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          antd: ['antd', '@ant-design/icons'],
          echarts: ['echarts', 'echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers'],
        },
      },
    },
    chunkSizeWarningLimit: 1200,
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
