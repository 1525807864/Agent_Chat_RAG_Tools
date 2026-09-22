// ============================================================================
// ModeBar.tsx：顶部模式条 —— mode / multi / agent / SSE / 探活
// ============================================================================

// 导入模式类型
import type { Mode, MultiMode } from "../types/api";

// 主模式下拉选项（与后端 Mode 对齐）
const MODES: Mode[] = ["chat", "rag", "graph-rag", "agent", "multi", "consult"];
// multi 子模式选项
const MULTI_MODES: MultiMode[] = ["sequential", "debate", "router"];

// Props：全部受控
type Props = {
  mode: Mode; // 当前主模式
  setMode: (m: Mode) => void; // 改主模式
  multiMode: MultiMode; // 当前子模式
  setMultiMode: (m: MultiMode) => void; // 改子模式
  agentName: string; // agent 名
  setAgentName: (n: string) => void; // 改 agent 名
  e2eBaseUrl: string;
  setE2eBaseUrl: (n: string) => void;
  qaTenantId: string;
  setQaTenantId: (n: string) => void;
  useStream: boolean; // 是否 SSE
  setUseStream: (v: boolean) => void; // 切换 SSE
  healthLabel: string; // 探活文案
  healthOk: boolean | null; // 探活结果
};

// 导出 ModeBar
export function ModeBar({
  mode, // 解构各 props
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
  // 渲染顶栏
  return (
    <div className="topbar">
      {/* 主模式选择 */}
      <label>
        mode
        <select value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
          {MODES.map((m) => (
            // 每个 mode 一个 option
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>

      {/* 仅 multi 显示子模式 */}
      {mode === "multi" && (
        <label>
          multi_mode
          <select
            value={multiMode} // 受控值
            onChange={(e) => setMultiMode(e.target.value as MultiMode)} // 更新
          >
            {MULTI_MODES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
      )}

      {/* 仅 agent 显示名称输入 */}
      {mode === "agent" && (
        <>
          <label>
            agent_name
            <input
              type="text"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              style={{ width: 120 }}
            />
          </label>
          <label>
            e2e_base_url
            <input
              type="url"
              placeholder="https://被测站点"
              value={e2eBaseUrl}
              onChange={(e) => setE2eBaseUrl(e.target.value)}
              style={{ width: 200 }}
            />
          </label>
          <label>
            qa_tenant_id
            <input
              type="text"
              placeholder="qa-acme"
              value={qaTenantId}
              onChange={(e) => setQaTenantId(e.target.value)}
              style={{ width: 100 }}
            />
          </label>
        </>
      )}

      {/* SSE 开关 */}
      <label title="开：POST /api/chat/stream；关：POST /api/chat">
        <input
          type="checkbox" // 复选框
          checked={useStream} // 受控勾选
          onChange={(e) => setUseStream(e.target.checked)} // 更新布尔
        />
        SSE 流式
      </label>

      {/* 健康状态：按 ok/bad 加 class */}
      <span
        className={`health${healthOk === true ? " ok" : healthOk === false ? " bad" : ""}`}
        title="GET /health" // 悬停提示接口
      >
        {healthLabel}
      </span>
    </div>
  );
}
