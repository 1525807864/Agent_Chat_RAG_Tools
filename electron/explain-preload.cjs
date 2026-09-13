/**
 * explain-preload.cjs — 划词分析小窗的预加载桥
 * 渲染进程只能：听更新、关窗口；不能乱调 Node。
 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("explainAPI", {
  /**
   * 订阅主进程推送：
   * payload: { phase: 'idle'|'loading'|'done'|'error', selected?: string, answer?: string, detail?: string }
   */
  onUpdate: (handler) => {
    const listener = (_evt, payload) => handler(payload);
    ipcRenderer.on("explain:update", listener);
    // 返回取消订阅函数（可选）
    return () => ipcRenderer.removeListener("explain:update", listener);
  },
  close: () => ipcRenderer.send("explain:close"),
});
