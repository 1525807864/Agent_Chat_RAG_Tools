/**
 * 兼容说明
 * --------
 * 真正的主进程入口是同目录的 ``main.cjs``（见 frontend/package.json 的 "main"）。
 * 本文件保留为空壳，避免误把主进程逻辑写在 preload 里。
 * 请编辑：main.cjs / preload.cjs
 */
console.warn(
  "[electron] 请使用 main.cjs 作为入口；当前 main.js 不会被 package.json 引用。",
);
