import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        // 移除自动导入，改用@use语法
      }
    }
  },
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/login': {
        target: 'http://localhost:5409',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/upload': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/uploadSave': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/getFiles': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/getFile': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/deleteFile': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/getAccounts': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/getValidAccounts': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/deleteAccount': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/postVideo': {
        target: 'http://localhost:5409',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/postVideoBatch': {
        target: 'http://localhost:5409',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/updateUserinfo': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/uploadCookie': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/downloadCookie': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/syncProfile': {
        target: 'http://localhost:5409',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/openCreatorCenter': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/checkAccount': {
        target: 'http://localhost:5409',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/api/v2': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          elementPlus: ['element-plus'],
          utils: ['axios']
        }
      }
    }
  }
})
