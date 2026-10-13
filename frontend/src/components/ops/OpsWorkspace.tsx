/**
 * 运维排障工作台（Phase1）
 * 左：对话；右：最近一次调查的工具调用摘要。
 * 数据全部走 /api/ops，不直连 Holmes。
 */
import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Input, Space, Typography } from "antd";
import { CloudServerOutlined, SendOutlined } from "@ant-design/icons";
import { fetchOpsHealth, postOpsAsk } from "../../api/endpoints";
import type { OpsChatTurn, OpsHealth } from "../../types/ops";
import { SandboxApprovalSheet } from "../sandbox/SandboxApprovalSheet";
import { OpsTerminalPanel } from "./OpsTerminalPanel";

export function OpsWorkspace() {
  const [health, setHealth] = useState<OpsHealth | null>(null);
  const [chat, setChat] = useState<OpsChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  // 多轮必需：Holmes 上一轮返回的 conversation_history
  const [history, setHistory] = useState<Record<string, unknown>[] | null>(null);
  const [toolCalls, setToolCalls] = useState<unknown[]>([]);
  // P3：终端侧写观察，下一次「调查」时带给 Holmes
  const [termCtx, setTermCtx] = useState<{
    text: string;
    sessionId: string;
  } | null>(null);
  const { TextArea } = Input;
  // 进入页面探活
  useEffect(() => {
    void (async () => {
      try {
        const h = await fetchOpsHealth();
        setHealth(h);
        if (!h.holmesOk) {
          setNotice(`Holmes 不可达：${h.holmesBase}（请先 docker compose up / 启动 server.py）`);
        }
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      }
    })();
  }, []);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;
    setBusy(true);
    setNotice("");
    setInput("");
    const pendingCtx = termCtx;
    setTermCtx(null);
    // 先画用户气泡（若带了终端上下文，气泡里提示一眼）
    const bubble =
      pendingCtx?.text
        ? `${text}\n\n[已附带终端观察]\n${pendingCtx.text}`
        : text;
    setChat((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: "user", text: bubble },
    ]);
    try {
      const res = await postOpsAsk({
        message: text,
        conversation_history: history,
        terminalContext: pendingCtx?.text ?? null,
        sandboxSessionId: pendingCtx?.sessionId ?? null,
      });
      setHistory(res.conversationHistory || null);
      setToolCalls(res.toolCalls || []);
      setChat((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: res.analysis || "（无分析文本）",
        },
      ]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setNotice(msg);
      setChat((prev) => [
        ...prev,
        { id: `e-${Date.now()}`, role: "assistant", text: `错误：${msg}` },
      ]);
    } finally {
      setBusy(false);
    }
  }, [input, busy, history, termCtx]);

  return (
    <div className="qa-app" style={{ display: "flex", minHeight: "70vh" }}>
      {/* 打开交互终端 / 沙箱高危命令共用的底部审批卡 */}
      <SandboxApprovalSheet />
      {/* 左侧对话 */}
      <section className="qa-pane qa-center-page" style={{ flex: 1, padding: 16 }}>
        <div className="qa-pane-head">
          <Space>
            <CloudServerOutlined />
            <span>运维排障</span>
            {health ? (
              <Typography.Text type={health.holmesOk ? "success" : "danger"}>
                 {health.holmesOk ? "在线" : "离线"} · {health.model || "默认模型"}
              </Typography.Text>
            ) : null}
          </Space>
        </div>

        {notice ? (
          <Alert type="warning" showIcon message={notice} style={{ marginBottom: 12 }} />
        ) : null}
        {termCtx ? (
          <Alert
            type="info"
            showIcon
            closable
            onClose={() => setTermCtx(null)}
            style={{ marginBottom: 12 }}
            message="已附带终端观察，下次点「调查」将发给 Holmes"
            description={termCtx.text}
          />
        ) : null}

        <div
          style={{
            minHeight: 320,
            maxHeight: 480,
            overflow: "auto",
            marginBottom: 12,
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            padding: 12,
          }}
        >
          {chat.length === 0 ? (
            <Typography.Paragraph type="secondary">
              例如：「default 命名空间有哪些不健康的 Pod？原因是什么？」
            </Typography.Paragraph>
          ) : (
            chat.map((m) => (
              <div
                key={m.id}
                style={{
                  marginBottom: 12,
                  whiteSpace: "pre-wrap",
                  textAlign: m.role === "user" ? "right" : "left",
                }}
              >
                <Typography.Text strong>
                  {m.role === "user" ? "我" : "Holmes"}
                </Typography.Text>
                <div>{m.text}</div>
              </div>
            ))
          )}
        </div>

        <Space.Compact style={{ width: "100%" }}>
          <TextArea
            value={input}
            disabled={busy}
            rows={20}
            placeholder="描述告警或现象…"
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={() => void send()}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={busy}
            onClick={() => void send()}
          >
            调查
          </Button>
        </Space.Compact>
      </section>

      {/* 右侧：工具轨迹 + 沙箱终端 */}
      <aside
        style={{
          width: 420,
          borderLeft: "1px solid #e5e7eb",
          padding: 16,
          overflow: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <div>
          <Typography.Title level={5} style={{ marginTop: 0 }}>
            调查过程（tool_calls）
          </Typography.Title>
          {toolCalls.length === 0 ? (
            <Typography.Text type="secondary">尚无工具调用</Typography.Text>
          ) : (
            <pre style={{ fontSize: 11, whiteSpace: "pre-wrap" }}>
              {JSON.stringify(toolCalls, null, 2)}
            </pre>
          )}
        </div>
        <div style={{ minHeight: 320, flex: 1 }}>
          <OpsTerminalPanel
            onSendContext={(text, s) => {
              setTermCtx({ text, sessionId: s.sandboxSessionId });
              setInput(
                (prev) =>
                  prev || "请结合我在沙箱终端观察到的现象继续分析",
              );
            }}
          />
        </div>
      </aside>
    </div>
  );
}