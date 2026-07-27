import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
const apiToken = process.env.VITE_API_TOKEN || "";
const proxyHeaders = apiToken ? { Authorization: `Bearer ${apiToken}` } : undefined;

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          if (id.includes("/echarts/lib/chart/")) {
            return "vendor-echarts-charts";
          }
          if (id.includes("/echarts/lib/component/")) {
            return "vendor-echarts-components";
          }
          if (id.includes("/zrender/")) {
            return "vendor-echarts-renderer";
          }
          if (id.includes("/echarts/")) {
            return "vendor-echarts";
          }
          if (id.includes("/react/") || id.includes("/react-dom/") || id.includes("/react-router-dom/")) {
            return "vendor-react";
          }
          return undefined;
        }
      }
    }
  },
  server: {
    port: 5173,
    host: "127.0.0.1",
    strictPort: true,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
        headers: proxyHeaders
      },
      "/openapi.json": {
        target: apiProxyTarget,
        changeOrigin: true,
        headers: proxyHeaders
      },
      "/docs": {
        target: apiProxyTarget,
        changeOrigin: true,
        headers: proxyHeaders
      }
    }
  }
});
