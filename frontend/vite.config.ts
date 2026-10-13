/**
 * Vite 配置
 * - 开发：port 5173，与后端 CORS 白名单对齐
 * - /api 反代到 8020（含 WebSocket），终端 iframe 可走同源相对路径
 * - 打包：base 必须是 "./"，否则 Electron 用 loadFile 加载 dist 时 CSS/JS 路径会 404
 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // 相对路径：桌面端 file:// 或 asar 内打开页面时能找到 assets
  base: "./",
  server: {
    port: 5173,
    host: "127.0.0.1",
    cors: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8020",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    assetsDir: "assets",
    sourcemap: true,
  },
});
