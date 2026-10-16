/**
 * 运维排障工作台
 * - 先选 / 登记客户项目（Ops Target）
 * - 左：对话；右：工具轨迹 + 沙箱终端
 * - 数据全部走 /api/ops，不直连 Holmes / 客户 Agent
 */
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Input,
  Select,
  Space,
  Typography,
  Modal,
  Form,
  message,
} from "antd";
import { CloudServerOutlined, PlusOutlined, SendOutlined } from "@ant-design/icons";
import {
  createOpsTarget,
  fetchOpsHealth,
  fetchOpsTargets,
  postOpsAsk,
} from "../../api/endpoints";
import type { OpsChatTurn, OpsHealth, OpsTarget } from "../../types/ops";
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
  // 终端侧写观察，下一次「调查」时带给后端
  const [termCtx, setTermCtx] = useState<{
    text: string;
    sessionId: string;
  } | null>(null);

  // ---- 客户项目 ----
  const [targets, setTargets] = useState<OpsTarget[]>([]); // 客户项目列表
  const [targetId, setTargetId] = useState<string>(""); // 当前选中的客户项目 ID
  const [registerOpen, setRegisterOpen] = useState(false); // 登记客户项目弹窗是否打开
  const [registering, setRegistering] = useState(false);// 登记客户项目是否正在提交
  const [form] = Form.useForm();// 登记客户项目表单

  const { TextArea } = Input; // 文本域组件

  const reloadTargets = useCallback(async () => {
    const res = await fetchOpsTargets();
    // 只显示已启用的项目
    const items = (res.items || []).filter((t) => t.enabled);
    setTargets(items);
    setTargetId((prev) => {
      if (prev && items.some((t) => t.id === prev)) return prev;
      return items[0]?.id ?? "";
    });
  }, []);

  // 进入页面：探活 + 拉目标列表
  useEffect(() => {
    void (async () => {
      try {
        const h = await fetchOpsHealth();
        setHealth(h);
        if (!h.holmesOk) {
          setNotice(
            `平台 Holmes 探活失败：${h.holmesBase}（选 platform 目标时需要；remote_agent 看客户 Agent）`,
          );
        }
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      }
      try {
        await reloadTargets();
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [reloadTargets]);

  const onSwitchTarget = (id: string) => {
    setTargetId(id);
    // 换项目必须清空多轮上下文，避免串集群
    setHistory(null);
    setChat([]);
    setToolCalls([]);
    setNotice("");
  };

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;
    if (!targetId) {
      setNotice("请先选择或登记客户项目");
      return;
    }
    setBusy(true);
    setNotice("");
    setInput("");
    const pendingCtx = termCtx;
    setTermCtx(null);
    const bubble = pendingCtx?.text
      ? `${text}\n\n[已附带终端观察]\n${pendingCtx.text}`
      : text;
    setChat((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: "user", text: bubble },
    ]);
    try {
      const res = await postOpsAsk({
        targetId,
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
          usage: res.usage,
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
  }, [input, busy, history, termCtx, targetId]);

  const onRegister = async () => {
    try {
      const values = await form.validateFields();
      setRegistering(true);
      const created = await createOpsTarget({
        name: values.name,
        targetType: values.targetType,
        endpointBase: values.endpointBase || null,
        authToken: values.authToken || null,
        defaultNamespace: values.defaultNamespace || null,
        notes: values.notes || null,
      });
      message.success(`已登记：${created.name}`);
      setRegisterOpen(false);
      form.resetFields();
      await reloadTargets();
      setTargetId(created.id);
      setHistory(null);
      setChat([]);
      setToolCalls([]);
    } catch (e) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error(e instanceof Error ? e.message : String(e));
    } finally {
      setRegistering(false);
    }
  };

  const selected = targets.find((t) => t.id === targetId);

  return (
    <div className="qa-app" style={{ display: "flex", minHeight: "70vh" }}>
      <SandboxApprovalSheet />
      <section className="qa-pane qa-center-page" style={{ flex: 1, padding: 16 }}>
        <div className="qa-pane-head">
          <Space wrap>
            <CloudServerOutlined />
            <span>运维排障</span>
            <Select
              style={{ minWidth: 240 }}
              placeholder="选择客户项目"
              value={targetId || undefined}
              onChange={onSwitchTarget}
              options={targets.map((t) => ({
                value: t.id,
                label: `${t.name} · ${t.targetType}`,
              }))}
              notFoundContent="暂无项目，请先登记"
            />
            <Button
              icon={<PlusOutlined />}
              onClick={() => setRegisterOpen(true)}
            >
              登记项目
            </Button>
            {health ? (
              <Typography.Text type={health.holmesOk ? "success" : "danger"}>
                平台Holmes {health.holmesOk ? "在线" : "离线"} ·{" "}
                {health.model || "默认模型"}
              </Typography.Text>
            ) : null}
            {selected ? (
              <Typography.Text type="secondary">
                当前：{selected.name}
                {selected.defaultNamespace
                  ? ` · ns=${selected.defaultNamespace}`
                  : ""}
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
            message="已附带终端观察，下次点「调查」将发给目标引擎"
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
              先选择客户项目，再描述告警。例如：「default 命名空间有哪些不健康的 Pod？」
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
                {m.role === "assistant" && m.usage ? (
                  <div className="msg-usage" title="本轮 Token（ops → 平台账本）">
                    命中Token {m.usage.tokens_in} · 输出Token {m.usage.tokens_out} · 总计{" "}
                    {m.usage.tokens_total}
                    {m.usage.model ? ` · ${m.usage.model}` : ""}
                  </div>
                ) : null}
              </div>
            ))
          )}
        </div>

        <Space.Compact style={{ width: "100%" }}>
          <TextArea
            value={input}
            disabled={busy || !targetId}
            rows={8}
            placeholder={
              targetId ? "描述告警或现象…" : "请先选择或登记客户项目"
            }
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={busy}
            disabled={!targetId}
            onClick={() => void send()}
          >
            调查
          </Button>
        </Space.Compact>
      </section>

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

      <Modal
        title="登记客户运维项目"
        open={registerOpen}
        onCancel={() => setRegisterOpen(false)}
        onOk={() => void onRegister()}
        confirmLoading={registering}
        okText="登记"
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ targetType: "platform" }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: "必填" }]}
          >
            <Input placeholder="如：本平台集群 / Acme 生产" />
          </Form.Item>
          <Form.Item
            name="targetType"
            label="类型"
            rules={[{ required: true }]}
            extra="platform=本平台 Holmes；remote_agent=客户侧 Agent；dedicated_holmes=客户专用 Holmes"
          >
            <Select
              options={[
                { value: "platform", label: "platform（本平台）" },
                { value: "remote_agent", label: "remote_agent（客户 Agent）" },
                {
                  value: "dedicated_holmes",
                  label: "dedicated_holmes（专用 Holmes）",
                },
              ]}
            />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.targetType !== cur.targetType}
          >
            {({ getFieldValue }) =>
              getFieldValue("targetType") !== "platform" ? (
                <Form.Item
                  name="endpointBase"
                  label="Endpoint（无尾斜杠）"
                  rules={[{ required: true, message: "客户目标必须填地址" }]}
                >
                  <Input placeholder="https://ops-agent.customer.example" />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item
            name="authToken"
            label="Auth Token（可选，入库加密，不会回显）"
          >
            <Input.Password placeholder="与客户 AGENT_TOKEN 一致" />
          </Form.Item>
          <Form.Item name="defaultNamespace" label="默认 Namespace（可选）">
            <Input placeholder="如 production" />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
