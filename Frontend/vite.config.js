import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 개발할 때(npm run dev) 화면은 5173 포트, 서버(FastAPI)는 8000 포트라서
    // 서버로 가는 요청을 8000 포트로 전달해 줍니다.
    proxy: {
      '/floors': 'http://localhost:8000',
      '/subscribe': 'http://localhost:8000',
      '/vapid-public-key': 'http://localhost:8000',
      '/lost-items': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
