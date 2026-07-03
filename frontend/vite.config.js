import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 前端 dev server 把 /api 开头的请求转发到后端,绕开跨域(不用改后端加 CORS)
    // 端口 8001:docker-compose 把 app 容器的 8000 映射到宿主机 8001
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
