/**
 * Ops 交互终端面板（P1–P3）
 * - 打开：可写需审批；只读跳过审批（ttyd -R）
 * - iframe：同源 /api/ops/terminal/proxy/{ticket}/
 * - P3：把终端观察发给 Holmes（父组件拼进下一轮调查）
 */
import { useCallback, useState } from "react";
import { Alert, Button, Input, Space, Switch, Typography } from "antd";
import {
  CodeOutlined,
  CloseOutlined,
  DownloadOutlined,
  SendOutlined,
} from "@ant-design/icons";
import { getApiBase } from "../../api/client";
import {
  closeOpsTerminal,
  downloadOpsTerminalRecording,
  openOpsTerminalWithApproval,
} from "../../api/endpoints";
import type { OpsTerminalSession } from "../../types/ops";

export function OpsTerminalPanel(props: {
  onSessionChange?: (s: OpsTerminalSession | null) => void;
  /** 用户点「发给 Holmes」时回调一段说明文字 */
  onSendContext?: (text: string, sess: OpsTerminalSession) => void;
}) {
  const [sess, setSess] = useState<OpsTerminalSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [readonly, setReadonly] = useState(false);
  const [note, setNote] = useState("");

  const open = useCallback(async () => {
    setBusy(true);
    setErr("");
    try {
      const s = await openOpsTerminalWithApproval({ readonly });
      setSess(s);
      props.onSessionChange?.(s);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [props, readonly]);

  const close = useCallback(async () => {
    if (!sess) return;
    setBusy(true);
    try {
      await closeOpsTerminal(sess.terminalId);
    } catch {
      /* 忽略：进程可能已 --once 退出 */
    } finally {
      setSess(null);
      props.onSessionChange?.(null);
      setBusy(false);
    }
  }, [sess, props]);

  const sendNote = useCallback(() => {
    const t = note.trim();
    if (!t || !sess) return;
    props.onSendContext?.(t, sess);
    setNote("");
  }, [note, sess, props]);

  const downloadRec = useCallback(async () => {
    if (!sess) return;
    setBusy(true);
    setErr("");
    try {
      await downloadOpsTerminalRecording(sess.terminalId);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [sess]);

  // 浏览器一律相对路径（经 Vite/Nginx 同源反代，含 WS）；仅 Electron 拼 API_BASE
  const iframeSrc = sess
    ? typeof window !== "undefined" && window.electronAPI
      ? `${getApiBase()}${sess.terminalUrl}`
      : sess.terminalUrl
    : "";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Space style={{ marginBottom: 8 }} wrap>
        <CodeOutlined />
        <Typography.Text strong>终端</Typography.Text>
        {!sess ? (
          <>
            <Switch
              size="small"
              checked={readonly}
              onChange={setReadonly}
              checkedChildren="只读"
              unCheckedChildren="可写"
            />
            <Button
              type="primary"
              size="small"
              loading={busy}
              onClick={() => void open()}
            >
              打开终端
            </Button>
          </>
        ) : (
          <>
            {sess.recording ? (
              <Button
                size="small"
                icon={<DownloadOutlined />}
                loading={busy}
                onClick={() => void downloadRec()}
              >
                录制
              </Button>
            ) : null}
            <Button
              danger
              size="small"
              icon={<CloseOutlined />}
              loading={busy}
              onClick={() => void close()}
            >
              关闭
            </Button>
          </>
        )}
        {sess ? (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            会话 {sess.sandboxSessionId}
            {sess.readonly ? " · 只读" : ""} · 剩余 {sess.ttlSec}s
          </Typography.Text>
        ) : null}
      </Space>

      {err ? (
        <Alert type="error" showIcon message={err} style={{ marginBottom: 8 }} />
      ) : null}

      {sess ? (
        <iframe
          title="ops-terminal"
          src={iframeSrc}
          style={{
            flex: 1,
            minHeight: 240,
            width: "100%",
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            background: "#0b1220",
          }}
          allow="clipboard-read; clipboard-write"
        />
      ) : (
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          打开后将进入终端。
        </Typography.Paragraph>
      )}

      {sess ? (
        <Space.Compact style={{ width: "100%", marginTop: 8 }}>
          <Input
            placeholder="描述你在终端里看到的现象…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onPressEnter={sendNote}
          />
          <Button
            type="default"
            icon={<SendOutlined />}
            disabled={!note.trim()}
            onClick={sendNote}
          >
            发给 Holmes
          </Button>
        </Space.Compact>
      ) : null}
    </div>
  );
}
