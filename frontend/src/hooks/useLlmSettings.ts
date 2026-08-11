// ============================================================================
// useLlmSettings.ts：模型凭证 localStorage Hook（draft / settings 双缓冲）
// ============================================================================

// 导入 React Hook
import { useCallback, useState } from "react";
// 导入设置类型
import type { LlmSettings } from "../types/api";

// localStorage 键名；结构变更时请改版本号
const STORAGE_KEY = "llm.settings.v1";

// 默认设置：Key 空，Base/Model 给 DeepSeek 常用值
const DEFAULTS: LlmSettings = {
  api_key: "", // 空 Key → 后端用 .env
  api_base: "https://api.deepseek.com/v1", // 默认厂商地址
  model_name: "deepseek-v4-flash", // 默认模型名
};

// 从 localStorage 安全读取，坏数据回退默认
function load(): LlmSettings {
  try {
    // 读原始字符串
    const raw = localStorage.getItem(STORAGE_KEY);
    // 没有存过 → 返回默认副本
    if (!raw) return { ...DEFAULTS };
    // 解析 JSON（可能缺字段）
    const parsed = JSON.parse(raw) as Partial<LlmSettings>;
    // 逐字段校验类型后组装
    return {
      // api_key 必须是 string，否则用默认
      api_key: typeof parsed.api_key === "string" ? parsed.api_key : DEFAULTS.api_key,
      // api_base 同理
      api_base: typeof parsed.api_base === "string" ? parsed.api_base : DEFAULTS.api_base,
      // model_name 同理
      model_name:
        typeof parsed.model_name === "string" ? parsed.model_name : DEFAULTS.model_name,
    };
  } catch {
    // JSON 损坏等 → 全体默认
    return { ...DEFAULTS };
  }
}

// Hook 主体：对外暴露 settings/draft/save/clear
export function useLlmSettings() {
  // 正式生效的设置（发消息用）；懒初始化只读盘一次
  const [settings, setSettings] = useState<LlmSettings>(() => load());
  // 表单草稿（输入框绑定）
  const [draft, setDraft] = useState<LlmSettings>(() => load());
  // 保存/清除后的提示文案
  const [savedHint, setSavedHint] = useState<string | null>(null);

  // 保存：draft → localStorage + settings
  const save = useCallback(() => {
    // 组装并 trim 空白
    const next: LlmSettings = {
      api_key: draft.api_key.trim(), // 去掉首尾空格
      api_base: draft.api_base.trim(), // 同上
      model_name: draft.model_name.trim(), // 同上
    };
    // 持久化到浏览器
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    // 更新正式 settings
    setSettings(next);
    // 草稿与正式对齐
    setDraft(next);
    // 提示用户
    setSavedHint("已保存到本机浏览器");
  }, [draft]); // draft 变了要重建回调

  // 清除：删盘并恢复 DEFAULTS
  const clear = useCallback(() => {
    // 删除本地键
    localStorage.removeItem(STORAGE_KEY);
    // 拷贝默认对象
    const next = { ...DEFAULTS };
    // 正式设置复位
    setSettings(next);
    // 草稿复位
    setDraft(next);
    // 提示
    setSavedHint("已清除本地设置");
  }, []); // 无依赖

  // 返回给 App / SettingsPanel
  return {
    settings, // 发消息用
    draft, // 表单用
    setDraft, // 改草稿
    save, // 保存按钮
    clear, // 清除按钮
    savedHint, // 底部提示
    defaults: DEFAULTS, // 需要时可展示默认值
  };
}
