import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发期把 /api 与 /ws 代理到后端 localhost:8000
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 注意顺序:WS 规则必须在前,否则会被 /api 规则抢先匹配导致 upgrade 失败
      '/api/v1/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
