/**
 * Electron 预加载脚本（preload）
 * ==============================
 * 在「主进程」和「网页渲染进程」之间搭一座窄桥：
 * - 网页不能直接碰 Node/Electron API（安全）
 * - 这里用 contextBridge 只暴露白名单字段
 *
 * 前端用法：
 *   window.electronAPI?.isElectron  → true
 *   window.electronAPI?.apiBase     → 云 API 或 LANGCHAIN_API_BASE
 */

/**
 * preload：只暴露白名单桥，渲染进程不能直接 require('fs')
 */
const { contextBridge, ipcRenderer } = require("electron");
const { API_BASE } = require("./api-base.cjs");

contextBridge.exposeInMainWorld("electronAPI", {
  isElectron: true,
  apiBase: API_BASE,
  platform: process.platform,
});

/**
 * 工作区 API：全部转到主进程 IPC
 * 渲染进程调用：await window.workspaceAPI.readFile(root, "src/a.py")
 */
contextBridge.exposeInMainWorld("workspaceAPI", {
  // 弹出系统选文件夹对话框，返回绝对路径或 null
  selectDirectory: () => ipcRenderer.invoke("ws:select-directory"),
  // 列出某相对目录下的一层子节点（懒加载树）
  listDir: (absRoot, relPath = "") =>
    ipcRenderer.invoke("ws:list-dir", { absRoot, relPath }),
  // 读文本文件（主进程做扩展名/大小校验）
  readFile: (absRoot, relPath) =>
    ipcRenderer.invoke("ws:read-file", { absRoot, relPath }),
  // 写文本文件（必须落在 absRoot 内）
  writeFile: (absRoot, relPath, content) =>
    ipcRenderer.invoke("ws:write-file", { absRoot, relPath, content }),
});