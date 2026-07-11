import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiHost = process.env.SQURVE_DEMO_API_HOST || '127.0.0.1'
const apiPort = process.env.SQURVE_DEMO_API_PORT || '7861'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: `http://${apiHost}:${apiPort}`, ws: true } },
  },
  preview: { port: 4173, strictPort: true },
})
