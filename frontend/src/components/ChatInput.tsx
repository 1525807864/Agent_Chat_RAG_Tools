// ============================================================================
// ChatInput.tsx：底部输入区 —— Enter 发送 / Shift+Enter 换行 / 停止
// ============================================================================

// 导入 useState 与键盘事件类型
import { useState, type KeyboardEvent } from "react";

// Props 类型定义
type Props = {
  loading: boolean; // 是否生成中
  onSend: (text: string) => void; // 提交回调
  onStop: () => void; // 停止回调
  allowEmptySend?: boolean; // 有附件时允许空文本发送
};

// 导出输入组件
export function ChatInput({
  loading, // 解构：加载态
  onSend, // 解构：发送
  onStop, // 解构：停止
  allowEmptySend = false, // 解构：默认不允许空发
}: Props) {
  // 输入框受控文本
  const [text, setText] = useState("");

  // 提交逻辑
  const submit = () => {
    const t = text.trim(); // 去掉空白
    // 无字且不允许空发，或正在 loading → 直接返回
    if ((!t && !allowEmptySend) || loading) return;
    onSend(t); // 交给父组件（会拼附件）
    setText(""); // 清空输入框
  };

  // 键盘处理
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter 且未按 Shift → 发送
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault(); // 阻止默认换行
      submit(); // 执行发送
    }
  };

  // 渲染
  return (
    // 输入区容器
    <div className="composer">
      {/* 多行输入 */}
      <textarea
        value={text} // 受控值
        onChange={(e) => setText(e.target.value)} // 同步 state
        onKeyDown={onKeyDown} // 键盘发送
        placeholder="输入消息… Enter 发送，Shift+Enter 换行" // 占位提示
        disabled={loading} // 生成中禁用编辑
        rows={3} // 默认 3 行高
      />
      {/* 右侧按钮列 */}
      <div className="composer-actions">
        {loading ? (
          // 生成中：停止按钮
          <button type="button" className="btn danger" onClick={onStop}>
            停止
          </button>
        ) : (
          // 空闲：发送按钮
          <button
            type="button" // 避免当 submit 进表单
            className="btn primary" // 主色按钮
            onClick={submit} // 点击发送
            disabled={!text.trim() && !allowEmptySend} // 无内容则禁用
          >
            发送
          </button>
        )}
      </div>
    </div>
  );
}
