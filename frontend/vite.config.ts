import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:5001',
      '/health': 'http://127.0.0.1:5001',
      '/version': 'http://127.0.0.1:5001',
    },
  },
});
