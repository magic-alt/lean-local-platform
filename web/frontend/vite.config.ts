import { readFileSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const frontendRoot = fileURLToPath(new URL(".", import.meta.url));
const repoRoot = fileURLToPath(new URL("../../", import.meta.url));

function firstNonEmpty(...values: Array<string | undefined>): string {
  return values.find((value) => Boolean(value?.trim()))?.trim() ?? "";
}

function readApiToken(env: Record<string, string>): string {
  const directToken = firstNonEmpty(
    process.env.LEAN_API_TOKEN,
    env.LEAN_API_TOKEN
  );
  if (directToken) return directToken;

  const configuredTokenFile = firstNonEmpty(
    process.env.LEAN_API_TOKEN_FILE,
    env.LEAN_API_TOKEN_FILE
  ) || "web/runtime/secrets/api_token";
  const tokenFile = isAbsolute(configuredTokenFile)
    ? configuredTokenFile
    : resolve(repoRoot, configuredTokenFile);
  try {
    return readFileSync(tokenFile, "utf-8").trim();
  } catch {
    return "";
  }
}

function authRequired(env: Record<string, string>): boolean {
  const value = firstNonEmpty(
    process.env.LEAN_API_AUTH_REQUIRED,
    env.LEAN_API_AUTH_REQUIRED
  ) || "1";
  return !["0", "false", "no", "off"].includes(value.toLowerCase());
}

export default defineConfig(({ mode }) => {
  // Vite normally loads .env from web/frontend, while the platform contract
  // keeps private runtime credentials in the repository-root .env. Merge both
  // for server-side proxy configuration only. The platform token deliberately
  // uses LEAN_* names rather than VITE_* so it can never become client env.
  const env = {
    ...loadEnv(mode, repoRoot, ""),
    ...loadEnv(mode, frontendRoot, "")
  };
  const apiProxyTarget = firstNonEmpty(
    process.env.VITE_API_PROXY_TARGET,
    env.VITE_API_PROXY_TARGET
  ) || "http://127.0.0.1:8000";
  const apiToken = readApiToken(env);
  const proxyHeaders = apiToken ? { Authorization: `Bearer ${apiToken}` } : undefined;

  if (authRequired(env) && !apiToken) {
    console.warn(
      "[vite] API authentication is enabled but no platform API token was found. " +
      "Set LEAN_API_TOKEN or LEAN_API_TOKEN_FILE in the repository-root .env."
    );
  }

  return {
    plugins: [react()],
    build: {
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) {
              return undefined;
            }
            // ECharts and zrender contain intentional cross-package cycles. Keep
            // them in one chunk so Rollup does not turn those cycles into chunk
            // initialization-order warnings.
            if (id.includes("/echarts/") || id.includes("/zrender/")) {
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
  };
});
