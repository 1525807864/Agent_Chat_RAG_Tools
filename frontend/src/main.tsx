// ============================================================================
// 前端入口文件 main.tsx：浏览器最先执行的模块之一
// ============================================================================
// 从 React 包导入命名空间对象（StrictMode 要用 React.StrictMode）
import React from "react";
// 从 react-dom/client 导入 React 18 的根 API（createRoot）
import ReactDOM from "react-dom/client";
// 导入页面根组件（整个 UI 从 App 展开）
import App from "./App";
// 导入全局 CSS，让 Vite 把它注入到页面（副作用导入，无绑定名）
import "./styles/index.css";

// 在 DOM 里找到 id="root" 的节点；! 告诉 TypeScript「一定存在，不是 null」
// createRoot：创建 React 18 并发根，替代旧版 ReactDOM.render
ReactDOM.createRoot(document.getElementById("root")!).render(
  // StrictMode：开发环境额外检查（Effect 可能跑两次），帮助发现副作用问题
  <React.StrictMode>
    {/* 真正挂载业务根组件 */}
    <App />
  </React.StrictMode>,
); // render 调用结束
