// ============================================================================
// 前端入口文件 main.tsx：浏览器最先执行的模块之一
// ============================================================================
import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import "./styles/index.css";
import "./styles/qa-workbench.css";

/** Nexora 门户同款主题：墨海军 + 香槟金点缀（对齐 HomePortal） */
const nexoraTheme = {
  token: {
    colorPrimary: "#1e293b",
    colorInfo: "#1e293b",
    colorSuccess: "#c5a572",
    colorLink: "#c5a572",
    borderRadius: 8,
    fontFamily:
      '"Segoe UI", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif',
    colorBgLayout: "#f3f4f6",
    colorText: "#111827",
    colorBorder: "#e5e7eb",
  },
  components: {
    Button: {
      controlHeight: 32,
      fontWeight: 500,
      primaryShadow: "none",
    },
    Menu: {
      darkItemBg: "transparent",
      darkItemSelectedBg: "#1e293b",
      darkItemHoverBg: "rgba(197, 165, 114, 0.18)",
    },
    Layout: {
      headerBg: "#ffffff",
      siderBg: "#0f172a",
    },
  },
};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={nexoraTheme}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
);
