// ============================================================================
// endpoints.ts：后端路由的一一映射（UI 只调这里）
// ============================================================================

// 导入底层 JSON 客户端与 Base 读取
import { apiJson, getApiBase, handleUnauthorized } from "./client";
import { authHeaders } from "../auth/token";

// 导入请求/响应类型（仅类型，编译后擦除）
import type {
  BuildKBRequest, // 建库请求
  BuildKBResponse, // 建库响应
  ChatRequest, // 聊天请求
  ChatResponse, // 非流式聊天响应
  DocListResponse, // 租户文档列表
  GraphStatsResponse, // 图谱统计
  HealthResponse, // 健康检查
  ReadyHealthResponse, // 就绪检查
  SessionHistoryResponse, // 会话历史
  SessionListResponse, // 会话列表
  SessionMemoryResponse, // 会话记忆快照（含意图台账）
  UploadDocResponse, // 上传文档响应
  KbJobResponse, // 建库任务状态
  TurnUsage, // 本轮token用量
  TenantUsageDTO, // 租户用量
  TaskPlan, // 意图台账
  TaskEventPayload, // SSE task 帧
  QaProject, // 测试工作台：被测项目
  QaCase, // 测试工作台：用例
  QaRun, // 测试工作台：运行
} from "../types/api";
import type { QaMember } from "../types/qa";

// GET /health：liveness 探活
export function fetchHealth() {
  return apiJson<HealthResponse>("/health");
}

// GET /health/ready：业务就绪（503 时仍解析 JSON，不抛错）
export async function fetchReady(): Promise<ReadyHealthResponse> {
  const res = await fetch(`${getApiBase()}/health/ready`, {
    headers: { Accept: "application/json" },
  });
  const body = (await res.json()) as ReadyHealthResponse;
  return body;
}

/** 轮询就绪，超时抛错（桌面/网页启动闭环用） */
export async function waitUntilReady(
  timeoutMs = 60_000,
  intervalMs = 500,
): Promise<ReadyHealthResponse> {
  const t0 = Date.now();
  let last: ReadyHealthResponse | null = null;
  while (Date.now() - t0 < timeoutMs) {
    try {
      last = await fetchReady();
      if (last.ready) return last;
    } catch {
      // 后端尚未监听端口时忽略
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  const hint = last?.startup_error || "timeout";
  throw new Error(`后端未就绪：${hint}`);
}

// POST /api/chat：非流式一轮问答
export function postChat(body: ChatRequest) {
  // 调用通用客户端，方法 POST，body 序列化
  return apiJson<ChatResponse>("/api/chat", {
    method: "POST", // HTTP 方法
    body: JSON.stringify(body), // 请求体 JSON 字符串
  });
}

// GET /api/sessions：列出会话 id
export function listSessions() {
  // 无额外 init
  return apiJson<SessionListResponse>("/api/sessions");
}

// GET /api/sessions/{id}：拉历史
export function getSessionHistory(sessionId: string) {
  // encodeURIComponent 防止特殊字符破坏 URL
  return apiJson<SessionHistoryResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
}

// GET /api/sessions/{id}/memory：摘要 + Solip + 意图台账快照
export function getSessionMemory(sessionId: string) {
  return apiJson<SessionMemoryResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/memory`,
  );
}

// DELETE /api/sessions/{id}：删历史
export function deleteSession(sessionId: string) {
  // 指定 DELETE 方法
  return apiJson<{ ok: boolean; session_id: string }>(
    `/api/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" }, // 删除语义
  );
}

// POST /api/knowledge/build：构建知识库（可不传 doc_dir，走租户上传目录）
export function buildKnowledge(body: BuildKBRequest = {}) {
  // 空对象 {} 时后端默认 data/tenants/<tenant>/docs
  return apiJson<BuildKBResponse>("/api/knowledge/build", {
    method: "POST", // 创建/构建用 POST
    body: JSON.stringify(body), // JSON 体
  });
}
// POST /api/knowledge/build/async:异步建库，返回 job_id
export function startKnowledgeBuild() {
  return apiJson<{ job_id: string }>("/api/knowledge/build/async", {
    method: "POST", //创建一个后台任务
    body: JSON.stringify({}), //目录由后端按当前租户自动选择
  });
}
// GET /api/knowledge/build/{job_id}:轮询建库状态
export function getKnowledgeBuild(jobId: string) {
  return apiJson<KbJobResponse>(
    `/api/knowledge/build/${encodeURIComponent(jobId)}`
  );
}


// GET /api/knowledge/docs：列出当前租户已上传文件
export function listKnowledgeDocs() {
  // 无 body
  return apiJson<DocListResponse>("/api/knowledge/docs");
}

// POST /api/knowledge/docs/upload：multipart 上传单个文件
export async function uploadKnowledgeDoc(file: File): Promise<UploadDocResponse> {
  // FormData：浏览器自动带 multipart boundary
  const form = new FormData();
  // 字段名必须与 FastAPI 参数 File(...) 一致：file
  form.append("file", file);

  // 不要设置 Content-Type，否则会缺 boundary
  const res = await fetch(`${getApiBase()}/api/knowledge/docs/upload`, {
    method: "POST",
    headers: {
      ...authHeaders(),
    },
    body: form,
  });

  if (!res.ok) {
    if (handleUnauthorized(res, "/api/knowledge/docs/upload")) {
      throw new Error("登录已失效，请重新登录");
    }
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (body?.detail != null) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      // 非 JSON：保留 statusText
    }
    throw new Error(detail);
  }

  // 成功：解析上传结果
  return (await res.json()) as UploadDocResponse;
}

// GET /api/knowledge/graph/stats：图谱统计
export function getGraphStats() {
  // 无 body
  return apiJson<GraphStatsResponse>("/api/knowledge/graph/stats");
}

// POST /api/chat/stream：SSE 流式（手写 fetch + ReadableStream）
export async function postChatStream(
  body: ChatRequest, // 与非流式相同的请求体
  handlers: {
    onStart?: (data: { session_id: string; mode: string }) => void; // start 事件
    onDelta?: (delta: string) => void; // message 增量
    onDone?: (answer: string,meta?:{
      usage?: TurnUsage;
      tenant_usage?: TenantUsageDTO;
      task_plan?: TaskPlan;
    }) => void; // done 定稿
    onTask?: (payload: TaskEventPayload) => void; // task：意图追踪帧
    onError?: (detail: string) => void; // error 或 HTTP 失败
  },
  signal?: AbortSignal, // 可选：停止按钮 abort
): Promise<void> {
  // 直接 fetch 流式地址（不能走 apiJson，因为要读 body 流）
  const res = await fetch(`${getApiBase()}/api/chat/stream`, {
    method: "POST", // POST
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(body), // 序列化请求
    signal, // 传入 AbortSignal
  });
  // 必须先于通用 !res.ok：否则 401 会先 return，登出逻辑跑不到
  if (handleUnauthorized(res, "/api/chat/stream")) {
    handlers.onError?.("登录已失效，请重新登录");
    return;
  }
  if (!res.ok || !res.body) {
    const errText = await res.text().catch(() => res.statusText);
    handlers.onError?.(errText || "stream 请求失败");
    return;
  }

  // 获取字节流读取器
  const reader = res.body.getReader();
  // UTF-8 解码器
  const decoder = new TextDecoder("utf-8");
  // 未完成行的缓冲
  let buffer = "";

  // 当前 SSE 事件名，默认 message
  let eventName = "message";
  // 当前事件积攒的 data 行
  let dataLines: string[] = [];

  // 空行触发：结算一帧 SSE 事件
  const flushEvent = () => {
    // 没有 data 则忽略
    if (dataLines.length === 0) return;
    // 多行 data 用换行拼回
    const raw = dataLines.join("\n");
    // 清空积攒，准备下一帧
    dataLines = [];
    // 默认 payload 先当原始字符串
    let payload: unknown = raw;
    try {
      // 尝试 JSON 解析
      payload = JSON.parse(raw);
    } catch {
      // 解析失败：保留 raw，多数事件会忽略
    }

    // 按事件名分发
    if (eventName === "start") {
      // 流开始
      handlers.onStart?.(payload as { session_id: string; mode: string });
    } else if (eventName === "message") {
      // 增量消息：只接受字符串 delta（避免 null/对象导致空气泡）
      const d = payload as { delta?: unknown };
      if (typeof d.delta === "string" && d.delta.length > 0) {
        handlers.onDelta?.(d.delta);
      }
    } else if (eventName === "done") {
      // 结束帧：统一收成 string
      const d = payload as { answer?: unknown; delta?: unknown };
      const answer =
        typeof d.answer === "string"
          ? d.answer
          : typeof d.delta === "string"
            ? d.delta
            : "";
      handlers.onDone?.(answer,{
        usage: (payload as any).usage,
        tenant_usage: (payload as any).tenant_usage,
        task_plan: (payload as any).task_plan,
      });
    } else if (eventName === "task") {
      // Intent Guard 意图追踪帧：anchor / check / plan_update / finalize
      const t = payload as TaskEventPayload;
      if (t && typeof t.type === "string") {
        handlers.onTask?.(t);
      }
    } else if (eventName === "error") {
      // 业务错误帧
      const d = payload as { detail?: unknown };
      const detail =
        typeof d.detail === "string" && d.detail
          ? d.detail
          : "未知流式错误";
      handlers.onError?.(detail);
    }
    // 重置事件名为默认
    eventName = "message";
  };

  // 循环读流直到结束
  while (true) {
    // 读一块 Uint8Array
    const { value, done } = await reader.read();
    // 流结束跳出
    if (done) break;
    // 解码并追加到 buffer（stream:true 正确处理多字节字符边界）
    buffer += decoder.decode(value, { stream: true });

    // 按换行切成行
    const parts = buffer.split("\n");
    // 最后一段可能是半行，放回 buffer
    buffer = parts.pop() ?? "";

    // 逐行解析 SSE
    for (const line of parts) {
      // event: 行 → 更新事件名
      if (line.startsWith("event:")) {
        // 去掉前缀并 trim
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        // data: 行 → 积攒（兼容 data: 后有无空格）
        dataLines.push(line.slice(5).trimStart());
      } else if (line.trim() === "") {
        // 空行 → 结算一帧
        flushEvent();
      }
    }
  }
  // 连接结束后再 flush 一次残留
  flushEvent();
}
/**
 * 登录请求体
 */
export interface LoginRequest {
  username: string;
  password: string;
}
/** 登录响应 */
export interface LoginResponse {
  access_token: string;
  token_type: string;
  auth_enabled: boolean;
  user_id: string;
  tenant_id: string;
}
/** POST /api/auth/login */
export function postLogin(body: LoginRequest) {
  return apiJson<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** GET /api/billing/usage：当前租户累计 Token */
export function fetchTenantUsage() {
  return apiJson<{ tenant_id?: string; usage: TenantUsageDTO }>(
    "/api/billing/usage",
  );
}

/** 安装包是否可下载。available 为 false 时 detail 是给人看的原因。 */
export interface DesktopDownloadMeta {
  available: boolean;
  filename: string;
  size_bytes: number;
  platform: string;
  detail: string;
}

/** GET /api/downloads/desktop/meta */
export function fetchDesktopDownloadMeta() {
  return apiJson<DesktopDownloadMeta>("/api/downloads/desktop/meta");
}

/** 浏览器直接打开这个地址即可下载，文件名由响应头 Content-Disposition 决定。 */
export function desktopDownloadUrl(): string {
  return `${getApiBase()}/api/downloads/desktop`;
}

/** POST /api/auth/register。用户名 3–32，密码至少 8 位，与后端 RegisterRequest 一致。 */
export function postRegister(body: LoginRequest) {
  return apiJson<LoginResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchQaProjects() {
  return apiJson<{items:QaProject[]}>("/api/qa/projects");
}

export function createQaProject(body: {name:string;base_url:string;goal:string}) {
  return apiJson<QaProject>("/api/qa/projects",{
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function patchQaProject(
  projectId: string,
  body: { name?: string; base_url?: string; goal?: string },
) {
  return apiJson<QaProject>(`/api/qa/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function fetchQaCases(projectId: string) {
  return apiJson<{items:QaCase[]}>(`/api/qa/projects/${projectId}/cases`);
}

export function generateQaCases(projectId: string, goal?: string) {
  return apiJson<{ items: QaCase[] }>(
    `/api/qa/projects/${projectId}/generate`,
    {
      method: "POST",
      body: JSON.stringify({ goal: goal || null }),
    },
  );
}
/** POST confirm */
export function confirmQaCase(projectId: string, caseId: string, fused?: string) {
  return apiJson<QaCase>(
    `/api/qa/projects/${projectId}/cases/${caseId}/confirm`,
    { method: "POST", body: JSON.stringify({ fused: fused ?? null }) },
  );
}
/** GET runs */
export function fetchQaRuns(projectId: string) {
  return apiJson<{ items: QaRun[] }>(`/api/qa/projects/${projectId}/runs`);
}
/** POST 冒烟 */
export function runQaSmoke(projectId: string, case_ids?: string[]) {
  return apiJson<QaRun>(`/api/qa/projects/${projectId}/runs`, {
    method: "POST",
    body: JSON.stringify({ case_ids: case_ids ?? null }),
  });
}

/** DELETE 项目 */
export function deleteQaProject(projectId: string) {
  return apiJson<{ ok: boolean }>(`/api/qa/projects/${projectId}`, {
    method: "DELETE",
  });
}

/** DELETE 用例（含子节点） */
export function deleteQaCase(projectId: string, caseId: string) {
  return apiJson<{ items: QaCase[] }>(
    `/api/qa/projects/${projectId}/cases/${caseId}`,
    { method: "DELETE" },
  );
}

/** GET 成员 */
export function fetchQaMembers() {
  return apiJson<{ items: QaMember[] }>("/api/qa/members");
}

/** POST 成员 */
export function addQaMember(body: { name: string; role: string }) {
  return apiJson<{ items: QaMember[] }>("/api/qa/members", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** PATCH 成员角色 */
export function patchQaMember(memberId: string, role: string) {
  return apiJson<{ items: QaMember[] }>(
    `/api/qa/members/${memberId}`,
    { method: "PATCH", body: JSON.stringify({ role }) },
  );
}

/** DELETE 成员 */
export function deleteQaMember(memberId: string) {
  return apiJson<{ items: QaMember[] }>(`/api/qa/members/${memberId}`, {
    method: "DELETE",
  });
}

/** POST 测试助手 */
export function postQaAssistant(
  projectId: string,
  body: { text: string; case_id?: string | null },
) {
  return apiJson<{
    reply: string;
    selectedId: string | null;
    cases: QaCase[];
  }>(`/api/qa/projects/${projectId}/assistant`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** 一步 UI 测试（与后端 SSE data JSON 对齐） */
export type QaUiStreamEvent =
  | {
      type: "step";
      i: number;
      action: string;
      detail: string;
      ok: boolean;
      error?: string;
    }
  | {
      type: "done";
      verdict: string;
      summary: string;
      run?: QaRun;
    };

/**
 * POST /api/qa/projects/:id/runs/ui
 * 读 SSE：每帧 data: {json}
 */
export async function streamQaUiRun(
  projectId: string,
  body: { name: string; base_url: string; goal?: string },
  handlers: {
    onStep?: (s: Extract<QaUiStreamEvent, { type: "step" }>) => void;
    onDone?: (d: Extract<QaUiStreamEvent, { type: "done" }>) => void;
    onError?: (msg: string) => void;
  },
  signal?: AbortSignal,
): Promise<void> {
  const path = `/api/qa/projects/${projectId}/runs/ui`;
  const res = await fetch(`${getApiBase()}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (handleUnauthorized(res, path)) {
    handlers.onError?.("登录已失效，请重新登录");
    return;
  }
  if (!res.ok || !res.body) {
    const errText = await res.text().catch(() => res.statusText);
    handlers.onError?.(errText || "UI 测试请求失败");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const flushBlock = (block: string) => {
    const lines = block.split("\n");
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }
    if (!dataLines.length) return;
    try {
      const ev = JSON.parse(dataLines.join("\n")) as QaUiStreamEvent;
      if (ev.type === "step") handlers.onStep?.(ev);
      if (ev.type === "done") handlers.onDone?.(ev);
    } catch {
      // 半包或非 JSON，忽略
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const p of parts) flushBlock(p);
    if (done) {
      if (buffer.trim()) flushBlock(buffer);
      break;
    }
  }
}

/**POST 项目资料 */
export async function uploadQaSource(projectId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${getApiBase()}/api/qa/projects/${projectId}/sources`, 
  {method: "POST", headers :{...authHeaders()}, body: form});
  if (handleUnauthorized(res, `/api/qa/projects/${projectId}/sources`)) {
    throw new Error("登录已失效，请重新登录");
  }
  if (!res.ok) {
    const errText = await res.text().catch(() => res.statusText);
    throw new Error(errText || "上传项目资料失败");
  }
  return res.json() as Promise<import("../types/api").QaProject>;
}

/** GET /api/qa/projects/:id/runs/:runId/export?fmt=xlsx|docx|pdf */
export async function downloadQaRunExport(
  projectId: string,
  runId: string,
  fmt: "xlsx" | "docx" | "pdf" = "xlsx",
): Promise<void> {
  const path = `/api/qa/projects/${projectId}/runs/${runId}/export?fmt=${fmt}`;
  const res = await fetch(`${getApiBase()}${path}`, {
    headers: { ...authHeaders() },
  });
  if (handleUnauthorized(res, path)) {
    throw new Error("登录已失效，请重新登录");
  }
  if (!res.ok) {
    const errText = await res.text().catch(() => res.statusText);
    throw new Error(errText || "导出失败");
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${runId}.${fmt}`;
  a.click();
  URL.revokeObjectURL(a.href);
}