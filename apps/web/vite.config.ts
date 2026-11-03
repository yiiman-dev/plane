import path from "node:path";
import { fileURLToPath } from "node:url";
import * as dotenv from "dotenv";
import { reactRouter } from "@react-router/dev/vite";
import { defineConfig } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";

const dirname = import.meta.dirname ?? path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(dirname, ".env") });

// Expose only vars starting with VITE_
const viteEnv = Object.keys(process.env)
  .filter((k) => k.startsWith("VITE_"))
  .reduce<Record<string, string>>((a, k) => {
    a[k] = process.env[k] ?? "";
    return a;
  }, {});

const defineEnv = Object.keys(viteEnv).reduce<Record<string, string>>(
  (acc, key) => {
    acc[`process.env.${key}`] = JSON.stringify(viteEnv[key]);
    return acc;
  },
  {
    "process.env": JSON.stringify(viteEnv),
    __PLANE_ENV__: JSON.stringify(viteEnv),
  }
);

const apiProxyTarget =
  process.env.VITE_API_INTERNAL_URL ?? (process.env.DOCKER_CONTAINER ? "http://api:8000" : "http://localhost:8000");

export default defineConfig(() => ({
  define: defineEnv,
  build: {
    assetsInlineLimit: 0,
  },
  plugins: [reactRouter(), tsconfigPaths({ projects: [path.resolve(dirname, "tsconfig.json")] })],
  resolve: {
    alias: {
      // Next.js compatibility shims used within web
      "next/link": path.resolve(dirname, "app/compat/next/link.tsx"),
      "next/navigation": path.resolve(dirname, "app/compat/next/navigation.ts"),
      "next/script": path.resolve(dirname, "app/compat/next/script.tsx"),
    },
    dedupe: ["react", "react-dom"],
  },
  server: {
    host: process.env.VITE_SERVER_HOST ?? "0.0.0.0",
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      "/auth": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  // No SSR-specific overrides needed; alias resolves to ESM build
}));
