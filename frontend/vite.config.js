import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const backendTarget = process.env.VITE_API_BASE_URL || 'http://localhost:5409'
const frontendPort = Number(process.env.VITE_FRONTEND_PORT || 5173)
const shouldOpenDevServer = process.env.VITE_DEV_OPEN !== 'false'

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
    port: frontendPort,
    open: shouldOpenDevServer,
    proxy: {
      '/login': {
        target: backendTarget,
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/upload': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/uploadSave': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/getFiles': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/getFile': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/deleteFile': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/getAccounts': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/getValidAccounts': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/deleteAccount': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/postVideo': {
        target: backendTarget,
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/postVideoBatch': {
        target: backendTarget,
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/updateUserinfo': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/uploadCookie': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/downloadCookie': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/syncProfile': {
        target: backendTarget,
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/openCreatorCenter': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/checkAccount': {
        target: backendTarget,
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/api': {
        target: backendTarget,
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
