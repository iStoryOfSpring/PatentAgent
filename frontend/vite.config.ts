import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // VisualizationPanel is an intentionally lazy-loaded ECharts workspace.
    // Keep the warning threshold below 1 MiB while treating that isolated
    // optional chunk separately from the 430 KiB application shell.
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        // Keep the optional visualization runtime cacheable and under the
        // per-chunk gzip budget. ECharts computation and zrender drawing have
        // different change rates and do not need to invalidate each other.
        manualChunks(id) {
          if (id.includes("/node_modules/zrender/")) return "zrender-runtime";
          if (id.includes("/node_modules/echarts/")) return "echarts-runtime";
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        // SSE needs unbuffered streaming — disable proxy buffering
        configure: (proxy) => {
          proxy.on("proxyReq", (_proxyReq, req) => {
            if (req.headers.accept === "text/event-stream") {
              // Prevent proxy from buffering SSE
              req.headers["cache-control"] = "no-cache";
            }
          });
          proxy.on("proxyRes", (proxyRes, req) => {
            if (req.headers.accept === "text/event-stream") {
              // Disable compression for SSE
              delete proxyRes.headers["content-encoding"];
            }
          });
        },
      },
    },
  },
});
