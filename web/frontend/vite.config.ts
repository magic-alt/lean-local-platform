import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

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
          if (id.includes("/zrender/")) {
            return "vendor-zrender";
          }
          if (id.includes("/echarts")) {
            return "vendor-echarts";
          }
          if (id.includes("/react/") || id.includes("/react-dom/") || id.includes("/react-router-dom/")) {
            return "vendor-react";
          }
          if (id.includes("/antd/") || id.includes("@ant-design") || id.includes("/rc-")) {
            return "vendor-antd";
          }
          if (id.includes("/monaco-editor") || id.includes("@monaco-editor")) {
            return "vendor-monaco";
          }
          return undefined;
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true
      }
    }
  }
});
