/**
 * icon-preload.cjs — 划词图标小窗桥
 * 渲染进程只能：点击触发分析
 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("iconAPI", {
  /** 用户点击图标 → 主进程用缓存文本跑分析 */
  analyze: () => ipcRenderer.send("icon:analyze"),
});
