// ============================================================================
// ModeBar.tsx：顶部模式条 —— mode / multi / agent / SSE / 探活
// ============================================================================

import { Input, Select, Space, Switch, Tag } from "antd";
import type { Mode, MultiMode } from "../types/api";

const MODES: Mode[] = ["chat", "rag", "graph-rag", "agent", "multi", "consult"];
const MULTI_MODES: MultiMode[] = ["sequential", "debate", "router"];

type Props = {
  mode: Mode;
  setMode: (m: Mode) => void;
  multiMode: MultiMode;
  setMultiMode: (m: MultiMode) => void;
  agentName: string;
  setAgentName: (n: string) => void;
  e2eBaseUrl: string;
  setE2eBaseUrl: (n: string) => void;
  qaTenantId: string;
  setQaTenantId: (n: string) => void;
  useStream: boolean;
  setUseStream: (v: boolean) => void;
  healthLabel: string;
  healthOk: boolean | null;
};

export function ModeBar({
  mode,
  setMode,
  multiMode,
  setMultiMode,
  agentName,
  setAgentName,
  e2eBaseUrl,
  setE2eBaseUrl,
  qaTenantId,
  setQaTenantId,
  useStream,
  setUseStream,
  healthLabel,
  healthOk,
}: Props) {
  const healthColor =
    healthOk === true ? "success" : healthOk === false ? "error" : "default";

  return (
    <div className="topbar ant-modebar">
      <Space wrap size={[12, 8]} align="center">
        <Space size={6}>
          <span className="ant-modebar-label">mode</span>
          <Select
            size="small"
            value={mode}
            style={{ minWidth: 120 }}
            onChange={(v) => setMode(v)}
            options={MODES.map((m) => ({ value: m, label: m }))}
          />
        </Space>

        {mode === "multi" && (
          <Space size={6}>
            <span className="ant-modebar-label">multi</span>
            <Select
              size="small"
              value={multiMode}
              style={{ minWidth: 120 }}
              onChange={(v) => setMultiMode(v)}
              options={MULTI_MODES.map((m) => ({ value: m, label: m }))}
            />
          </Space>
        )}

        {mode === "agent" && (
          <>
            <Input
              size="small"
              style={{ width: 120 }}
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              placeholder="agent_name"
              addonBefore="agent"
            />
            <Input
              size="small"
              style={{ width: 220 }}
              type="url"
              value={e2eBaseUrl}
              onChange={(e) => setE2eBaseUrl(e.target.value)}
              placeholder="https://被测站点"
              addonBefore="e2e"
            />
            <Input
              size="small"
              style={{ width: 140 }}
              value={qaTenantId}
              onChange={(e) => setQaTenantId(e.target.value)}
              placeholder="qa-acme"
              addonBefore="tenant"
            />
          </>
        )}

        <Space size={6}>
          <Switch
            size="small"
            checked={useStream}
            onChange={setUseStream}
            checkedChildren="SSE"
            unCheckedChildren="JSON"
          />
          <span className="ant-modebar-label">流式</span>
        </Space>

        <Tag
          className="health-tag"
          color={healthColor}
          title={`${healthLabel}\nGET /health/ready`}
        >
          {healthLabel}
        </Tag>
      </Space>
    </div>
  );
}
