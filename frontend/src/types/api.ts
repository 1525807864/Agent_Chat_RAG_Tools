// ============================================================================
// api.ts：与后端 FastAPI / Pydantic 契约对齐的前端类型
// ============================================================================

// Mode：对话主模式，须与后端 schemas.Mode、/health.modes 同步
export type Mode = "chat" | "rag" | "graph-rag" | "agent" | "multi";

// MultiMode：仅 mode=multi 时有意义的子模式
export type MultiMode = "sequential" | "debate" | "router";

/** 随请求带给后端的工作区文件（相对 workspace_root） */
export interface WorkspaceFileDTO {
  path: string;
  content: string;
}

// ChatRequest：POST /api/chat 与 /api/chat/stream 的请求体
export interface ChatRequest {
  // 用户输入（可已拼接附件全文）
  message: string;
  // 会话 ID，前端生成如 web-xxxxx
  session_id: string;
  // 主模式
  mode: Mode;
  // 多智能体子模式（可选）
  multi_mode?: MultiMode;
  // agent 模式下的智能体名（可选）
  agent_name?: string;
  // 大模型 API Key；空则后端用 .env
  api_key?: string;
  // 大模型 OpenAI 兼容 Base（不是 VITE_API_BASE）
  api_base?: string;
  // 模型名称
  model_name?: string;
  /** 桌面端工作区绝对路径；Agent 工具读写都限制在此根下 */
  workspace_root?: string;
  /** 本轮已打开的文件内容（避免大文件塞进 message） */
  files?: WorkspaceFileDTO[];
  /** 本轮要测的网站 origin，如 https://example.com */
  e2e_base_url?: string;
  /** 该站点测试文档的知识库租户 id */
  qa_tenant_id?: string;
}

// LlmSettings：localStorage 里保存的模型凭证结构
export interface LlmSettings {
  // API Key 字符串（可为空串）
  api_key: string;
  // 厂商 Base URL
  api_base: string;
  // 模型名
  model_name: string;
}

// ChatResponse：非流式聊天响应
export interface ChatResponse {
  // 回显会话 id
  session_id: string;
  // 实际使用的模式
  mode: string;
  // 助手最终回答
  answer: string;
  // 额外元数据（检索等）
  meta: Record<string, unknown>;
}

// SessionMessage：后端历史里的一条消息
export interface SessionMessage {
  // 角色字符串（后端可能多种取值）
  role: string;
  // 消息正文
  content: string;
}

// SessionHistoryResponse：GET /api/sessions/{id}
export interface SessionHistoryResponse {
  // 会话 id
  session_id: string;
  // 消息数组
  messages: SessionMessage[];
}

// SessionListResponse：GET /api/sessions
export interface SessionListResponse {
  // 会话 id 列表
  sessions: string[];
}

// BuildKBRequest：POST /api/knowledge/build
export interface BuildKBRequest {
  // 服务端允许根下的文档目录，如 data/docs
  doc_dir?: string;
}

// BuildKBResponse：构建知识库结果
export interface BuildKBResponse {
  // 实际使用的目录
  doc_dir: string;
  // 切分块数量
  chunk_count: number;
  // 人类可读说明
  message: string;
}

//上传接口返回
export interface UploadDocResponse {
  ok: boolean;
  tenant_id: string;
  path: string; //保存后的文件名
  size: number; //文件大小
  suffix?:string;
}

//文档列表
export interface DocInfo {
  name: string;
  size: number;
  path: string;
}
//文档列表响应
export interface DocListResponse {
  tenant_id: string;
  docs: DocInfo[];
}

// HealthResponse：GET /health
export interface HealthResponse {
  // 状态字，如 ok
  status: string;
  // 后端支持的 mode 列表
  modes: string[];
}

// GraphStatsResponse：GET /api/knowledge/graph/stats
export interface GraphStatsResponse {
  // 图谱统计键值
  stats: Record<string, unknown>;
}

// UiMessage：前端气泡本地模型（多 id，便于 key/流式更新）
export interface UiMessage {
  // 前端唯一 id
  id: string;
  // 收窄后的角色
  role: "user" | "assistant" | "system";
  // 展示正文
  content: string;
}
