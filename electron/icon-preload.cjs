/**
 * icon-preload.cjs
 * ================
 * 作用：在「划词圆形图标」这个无框小窗口里，安全地把少量 API 挂到 window.iconAPI 上。
 *
 * 为什么需要 preload？
 * - 渲染进程（icon.html）默认不能直接 require("electron")，也不能随便调主进程。
 * - 通过 contextBridge，只暴露我们允许的几个函数，避免把整个 ipcRenderer 交给页面脚本。
 *
 * 谁加载这个文件？
 * - main.cjs 创建 iconWindow 时，在 webPreferences.preload 里指定本文件路径。
 */

// 从 Electron 取出两个关键模块：
// - contextBridge：把对象挂到隔离的 window 上（配合 contextIsolation: true）
// - ipcRenderer：渲染进程 → 主进程发消息（单向 send，不要求回执）
const { contextBridge, ipcRenderer } = require("electron");

// 把名为 iconAPI 的对象挂到页面的 window 上，页面里写成：window.iconAPI.xxx()
contextBridge.exposeInMainWorld("iconAPI", {
  // 用户「点击」（未拖动）圆形按钮时调用：
  // 通知主进程：用缓存的 pendingExplainText 去跑分析，并打开解释窗
  analyze: () => ipcRenderer.send("icon:analyze"),

  // 鼠标还在图标上（进入 / 拖动中）时调用：
  // 通知主进程：把 5 秒自动隐藏的倒计时清零重来，避免图标突然消失
  ping: () => ipcRenderer.send("icon:ping"),

  // 用户按住按钮拖动时，每一小段位移调用一次：
  // dx / dy 是「相对上一帧」的屏幕像素差（不是窗口绝对坐标）
  // 主进程收到后用 setPosition 把小窗挪过去
  relativeMove: (dx, dy) => ipcRenderer.send("icon:move", { dx, dy }),

  // 用户松开鼠标（或 pointer 被取消）时调用：
  // 通知主进程：拖动结束，清掉 iconDragging 标志，
  // 这样全局 uIOhook 的 mouseup 不再被「正在拖图标」挡住
  dragEnd: () => ipcRenderer.send("icon:drag-end"),
});
