/**
 * 兼容说明
 * --------
 * 真正的预加载脚本是 ``preload.cjs``（由 main.cjs 的 webPreferences.preload 加载）。
 * 之前若把主进程代码误写在 preload.js，请改去维护 main.cjs。
 */
console.warn(
  "[electron] 请使用 preload.cjs；当前 preload.js 不会被主进程加载。",
);
