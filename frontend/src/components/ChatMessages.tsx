// ============================================================================
// ChatMessages.tsx：气泡列表 —— 加载点 / 打字机 / 历史瞬间显示
// ============================================================================

// 导入 Hook
import { useEffect, useRef, useState } from "react";
// 导入消息类型
import type { UiMessage } from "../types/api";
// 导入打字机组件
import { TypewriterText } from "./TypewriterText";

// Props
type Props = {
  messages: UiMessage[]; // 气泡数据
  loading: boolean; // 是否请求中
};

// 三点加载动画（样式在 CSS）
function TypingDots() {
  return (
    <span className="typing-dots" aria-label="正在输入">
      <span /> {/* 第 1 个点 */}
      <span /> {/* 第 2 个点 */}
      <span /> {/* 第 3 个点 */}
    </span>
  );
}

// 导出消息列表
export function ChatMessages({ messages, loading }: Props) {
  // 滚底锚点
  const bottomRef = useRef<HTMLDivElement>(null);
  // 本轮需要打字机的助手消息 id
  const [typingMsgId, setTypingMsgId] = useState<string | null>(null);

  // 锁定本轮空助手气泡 id
  useEffect(() => {
    // 列表清空 → 重置
    if (messages.length === 0) {
      setTypingMsgId(null);
      return;
    }
    // 未 loading 不锁定新目标
    if (!loading) return;
    // 看最后一条
    const last = messages[messages.length - 1];
    // 空助手 → 记下 id
    if (last?.role === "assistant" && !last.content) {
      setTypingMsgId(last.id);
    }
  }, [loading, messages]); // 依赖消息与 loading

  // 自动滚到底
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" }); // 平滑滚动
  }, [messages, loading]);

  // 空列表：引导文案
  if (messages.length === 0) {
    return (
      <div className="messages">
        <div className="empty">
          还没有消息。选好 mode 后在下方输入，默认走 SSE：POST /api/chat/stream。
        </div>
      </div>
    );
  }

  // 有消息：逐条渲染
  return (
    <div className="messages">
      {messages.map((m) => {
        // 是否本轮打字目标
        const isTypingTarget = m.role === "assistant" && m.id === typingMsgId;
        // 是否显示加载点
        const showDots = isTypingTarget && loading && !m.content;
        // 非目标 → 瞬间全文
        const instant = !isTypingTarget;

        return (
          // 单条气泡；class 含角色
          <div key={m.id} className={`msg ${m.role}`}>
            {/* 角色小字 */}
            <span className="role">{m.role}</span>

            {showDots ? (
              // 等待中
              <TypingDots />
            ) : m.role === "assistant" ? (
              // 助手：打字机或瞬间
              <TypewriterText text={m.content} instant={instant} speedMs={22} />
            ) : (
              // 用户/系统：纯文本
              m.content
            )}
          </div>
        );
      })}
      {/* 滚底哨兵 */}
      <div ref={bottomRef} />
    </div>
  );
}
