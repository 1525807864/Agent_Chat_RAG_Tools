// ============================================================================
// ChatInput.tsx：底部输入区 —— Enter 发送 / Shift+Enter 换行 / 停止
// ============================================================================

import { useState, type KeyboardEvent } from "react";
import { Button, Input } from "antd";
import { PauseCircleOutlined, SendOutlined } from "@ant-design/icons";

type Props = {
  loading: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  allowEmptySend?: boolean;
};

export function ChatInput({
  loading,
  onSend,
  onStop,
  allowEmptySend = false,
}: Props) {
  const [text, setText] = useState("");

  const submit = () => {
    const t = text.trim();
    if ((!t && !allowEmptySend) || loading) return;
    onSend(t);
    setText("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="composer ant-composer">
      <Input.TextArea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="输入消息… Enter 发送，Shift+Enter 换行"
        disabled={loading}
        autoSize={{ minRows: 3, maxRows: 8 }}
        className="ant-composer-input"
      />
      <div className="composer-actions">
        {loading ? (
          <Button danger icon={<PauseCircleOutlined />} onClick={onStop}>
            停止
          </Button>
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={submit}
            disabled={!text.trim() && !allowEmptySend}
          >
            发送
          </Button>
        )}
      </div>
    </div>
  );
}
