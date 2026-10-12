/**
 * 沙箱高危命令确认卡（Claude 风格底部 Sheet，Nexora teal 工作台语言）
 * - Esc 拒绝；在允许按钮聚焦时 Enter 允许
 * - 同时只展示队列队首
 */
import { useEffect, useState } from "react"; // 订阅与本地 state
import { Button, Typography } from "antd"; // 按钮与文案
import {
  getCurrentApproval, // 读队首
  settleApproval, // 结算
  subscribeApproval, // 订阅
} from "../../sandbox/approvalStore";
import type { PendingSandboxApproval } from "../../sandbox/types";

/** 把 argv 或 command 格式化成展示用多行字符串 */
function formatCommand(item: PendingSandboxApproval): string {
  // 优先展示 argv：每行一个参数，便于阅读
  if (item.argv && item.argv.length) {
    return item.argv.map((a) => JSON.stringify(a)).join(" ");
  }
  // 回退到单字符串命令
  return item.command || "(空命令)";
}

export function SandboxApprovalSheet() {
  // 本地镜像队首；null 表示不展示
  const [item, setItem] = useState<PendingSandboxApproval | null>(
    getCurrentApproval(),
  );

  // 挂载时订阅 store
  useEffect(() => {
    // 订阅：队列变化时同步到 React state
    const unsub = subscribeApproval(() => {
      setItem(getCurrentApproval());
    });
    // 卸载退订
    return unsub;
  }, []);

  // 键盘快捷键
  useEffect(() => {
    // 没有卡片时不监听
    if (!item) return;
    // 按键处理
    const onKey = (e: KeyboardEvent) => {
      // Esc → 拒绝
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        settleApproval(false);
        return;
      }
      // Enter → 允许；遮罩打开时吞掉按键，避免底下聊天框误提交
      if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        e.stopPropagation();
        settleApproval(true);
      }
    };
    // 捕获阶段监听，减少被其他 handler 吃掉
    window.addEventListener("keydown", onKey, true);
    // 清理
    return () => window.removeEventListener("keydown", onKey, true);
  }, [item]);

  // 无待确认项：不渲染 DOM
  if (!item) return null;

  // 命令展示文本
  const cmd = formatCommand(item);

  return (
    // 遮罩层：点击遮罩 = 拒绝（可选；若不想点遮罩关闭可去掉 onClick）
    <div
      className="sbx-approval-overlay"
      role="presentation"
      onClick={() => settleApproval(false)}
    >
      {/* 卡片本体：阻止冒泡，避免点卡片也触发拒绝 */}
      <div
        className="sbx-approval-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sbx-approval-title"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶栏：标题 + 会话元信息 */}
        <div className="sbx-approval-head">
          <div>
            <Typography.Text id="sbx-approval-title" strong className="sbx-approval-title">
              需要确认 · 沙箱命令
            </Typography.Text>
            <Typography.Paragraph type="secondary" className="sbx-approval-meta">
              会话 {item.sessionId}
              {item.vertical ? ` · ${item.vertical}` : ""}
              {" · "}
              {item.kind}
            </Typography.Paragraph>
          </div>
          <span className="sbx-approval-badge">高危</span>
        </div>

        {/* 命令等宽区 */}
        <pre className="sbx-approval-cmd" tabIndex={0}>
          {cmd}
        </pre>

        {/* 风险原因 */}
        <Typography.Paragraph className="sbx-approval-risk">
          {item.risk || "该命令可能产生不可逆影响，请确认后执行。"}
        </Typography.Paragraph>

        {/* 操作区 */}
        <div className="sbx-approval-actions">
          <Button onClick={() => settleApproval(false)}>拒绝 Esc</Button>
          <Button type="primary" className="sbx-approval-allow" onClick={() => settleApproval(true)}>
            仅本次允许 Enter
          </Button>
        </div>
      </div>
    </div>
  );
}