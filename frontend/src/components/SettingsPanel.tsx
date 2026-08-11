// ============================================================================
// SettingsPanel.tsx：右侧模型设置 —— 编辑 draft，保存/清除走回调
// ============================================================================

// 导入设置类型
import type { LlmSettings } from "../types/api";

// Props
type Props = {
  draft: LlmSettings; // 草稿
  setDraft: (next: LlmSettings | ((prev: LlmSettings) => LlmSettings)) => void; // 支持函数式更新
  onSave: () => void; // 保存
  onClear: () => void; // 清除
  savedHint: string | null; // 提示文案
};

// 导出面板
export function SettingsPanel({ draft, setDraft, onSave, onClear, savedHint }: Props) {
  // 改单个字段：只动草稿
  const patch = (key: keyof LlmSettings, value: string) => {
    // 函数式更新，保留其它字段
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  // 渲染
  return (
    <aside className="panel settings-panel">
      {/* 标题 */}
      <div className="panel-header">模型设置</div>
      {/* 主体 */}
      <div className="panel-body">
        {/* 说明文字 */}
        <p className="muted settings-hint">
          凭证只保存在本机浏览器。留空 Key 时，后端会用服务端 .env 兜底。
          API Base 是大模型厂商地址，不是前端的 VITE_API_BASE。
        </p>

        {/* 表单 */}
        <div className="settings-form">
          {/* API Key 标签 */}
          <label className="muted" htmlFor="llm-api-key">
            API Key
          </label>
          {/* 密码框防肩窥 */}
          <input
            id="llm-api-key" // 与 label 关联
            type="password" // 掩码
            autoComplete="off" // 禁止自动填充
            value={draft.api_key} // 受控
            onChange={(e) => patch("api_key", e.target.value)} // 写草稿
            placeholder="sk-...（可留空走服务端 .env）" // 占位
          />

          {/* API Base */}
          <label className="muted" htmlFor="llm-api-base">
            API Base
          </label>
          <input
            id="llm-api-base"
            type="text"
            value={draft.api_base}
            onChange={(e) => patch("api_base", e.target.value)}
            placeholder="https://api.deepseek.com/v1"
          />

          {/* Model Name */}
          <label className="muted" htmlFor="llm-model-name">
            Model Name
          </label>
          <input
            id="llm-model-name"
            type="text"
            value={draft.model_name}
            onChange={(e) => patch("model_name", e.target.value)}
            placeholder="deepseek-v4-flash"
          />

          {/* 操作按钮 */}
          <div className="settings-actions">
            <button type="button" className="btn primary" onClick={onSave}>
              保存
            </button>
            <button type="button" className="btn danger" onClick={onClear}>
              清除
            </button>
          </div>

          {/* 有提示才显示 */}
          {savedHint && <div className="settings-saved muted">{savedHint}</div>}
        </div>
      </div>
    </aside>
  );
}
