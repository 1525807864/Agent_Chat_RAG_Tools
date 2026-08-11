// ============================================================================
// endpoints.ts：后端路由的一一映射（UI 只调这里）
// ============================================================================

// 导入底层 JSON 客户端与 Base 读取
import { apiJson, getApiBase } from "./client";
// 导入请求/响应类型（仅类型，编译后擦除）
import type {
  BuildKBRequest, // 建库请求
  BuildKBResponse, // 建库响应
  ChatRequest, // 聊天请求
  ChatResponse, // 非流式聊天响应
  GraphStatsResponse, // 图谱统计
  HealthResponse, // 健康检查
  SessionHistoryResponse, // 会话历史
  SessionListResponse, // 会话列表
} from "../types/api";

// GET /health：探活
export function fetchHealth() {
  // 返回 Promise<HealthResponse>
  return apiJson<HealthResponse>("/health");
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

// DELETE /api/sessions/{id}：删历史
export function deleteSession(sessionId: string) {
  // 指定 DELETE 方法
  return apiJson<{ ok: boolean; session_id: string }>(
    `/api/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" }, // 删除语义
  );
}

// POST /api/knowledge/build：构建知识库
export function buildKnowledge(body: BuildKBRequest) {
  // 提交 doc_dir
  return apiJson<BuildKBResponse>("/api/knowledge/build", {
    method: "POST", // 创建/构建用 POST
    body: JSON.stringify(body), // JSON 体
  });
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
    onDone?: (answer: string) => void; // done 定稿
    onError?: (detail: string) => void; // error 或 HTTP 失败
  },
  signal?: AbortSignal, // 可选：停止按钮 abort
): Promise<void> {
  // 直接 fetch 流式地址（不能走 apiJson，因为要读 body 流）
  const res = await fetch(`${getApiBase()}/api/chat/stream`, {
    method: "POST", // POST
    headers: { "Content-Type": "application/json" }, // JSON 头
    body: JSON.stringify(body), // 序列化请求
    signal, // 传入 AbortSignal
  });

  // 失败或无 body：回调 onError 后返回
  if (!res.ok || !res.body) {
    // 尽量读文本错误信息
    const errText = await res.text().catch(() => res.statusText);
    // 通知上层
    handlers.onError?.(errText || "stream 请求失败");
    // 结束函数
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
      // 增量消息
      const d = payload as { delta?: string };
      // 有 delta 才回调
      if (d.delta) handlers.onDelta?.(d.delta);
    } else if (eventName === "done") {
      // 结束帧
      const d = payload as { answer?: string; delta?: string };
      // 优先 answer，否则 delta，再否则空串
      handlers.onDone?.(d.answer ?? d.delta ?? "");
    } else if (eventName === "error") {
      // 业务错误帧
      const d = payload as { detail?: string };
      // 回调错误详情
      handlers.onError?.(d.detail || "未知流式错误");
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
