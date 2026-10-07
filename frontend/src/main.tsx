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

/** Nexora 商业青绿主题：与测试平台 / 品牌色一致 */
const nexoraTheme = {
  token: {
    colorPrimary: "#0f766e",
    colorInfo: "#0f766e",
    colorSuccess: "#0f766e",
    colorLink: "#0f766e",
    borderRadius: 8,
    fontFamily:
      '"Segoe UI", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif',
    colorBgLayout: "#f3f5f7",
    colorText: "#1a2332",
    colorBorder: "#d8dee6",
  },
  components: {
    Button: {
      controlHeight: 32,
      fontWeight: 500,
    },
    Menu: {
      darkItemBg: "transparent",
      darkItemSelectedBg: "#0f766e",
      darkItemHoverBg: "rgba(15, 118, 110, 0.35)",
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
