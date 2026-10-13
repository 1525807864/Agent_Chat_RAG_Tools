/**
 * 运维排障工作台类型（对接 /api/ops/* → Holmes）
 */

/** 聊天气泡 */
export interface OpsChatTurn {
    id: string;
    role: "user" | "assistant";
    /** Markdown / 纯文本 */
    text: string;
}
  
  /** POST /api/ops/ask 响应 */
export interface OpsAskResult {
    analysis: string;
    conversationHistory: Record<string, unknown>[];
    toolCalls: unknown[];
    followUpActions: unknown[];
    raw?: Record<string, unknown>;
}
  
  /** GET /api/ops/health */
export interface OpsHealth {
    enabled: boolean;
    holmesOk: boolean;
    holmesBase: string;
    model: string | null;
}

/** POST /api/ops/terminal/sessions 响应 */
export interface OpsTerminalSession {
  terminalId: string;
  sandboxSessionId: string;
  /** 相对路径，如 /api/ops/terminal/view?ticket=... */
  terminalUrl: string;
  expiresAt: string;
  ttlSec: number;
  readonly: boolean;
  status: "running" | "stopped" | string;
  /** 是否有 typescript 录制可下载 */
  recording?: boolean;
}