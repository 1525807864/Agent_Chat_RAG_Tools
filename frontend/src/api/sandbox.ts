// ============================================================================
// 沙箱 HTTP 客户端：遇到 409 审批码时弹出确认卡，允许则带 approved:true 重放
// ============================================================================

import { getApiBase, handleUnauthorized } from "./client"; // Base URL + 401 处理
import { authHeaders } from "../auth/token"; // JWT 头
import { requestApproval } from "../sandbox/approvalStore"; // 弹出确认

/** 后端 ExecResult 的 camelCase 视图 */
export type SandboxExecResult = {
  ok: boolean; // 是否成功
  exitCode: number; // 退出码
  stdout: string; // 标准输出
  stderr: string; // 标准错误
  truncated: boolean; // 是否截断
  durationMs: number; // 耗时
  timedOut: boolean; // 是否超时
  needsApproval?: boolean; // 预留
  riskReason?: string; // 预留
};

/** 解析 FastAPI 409 detail（可能是 string 或对象） */
function parseDetail(body: unknown): { message: string; risk: string; code?: string } {
  // 默认文案
  const fallback = { message: "需要确认高危命令", risk: "" };
  // 非对象直接返回
  if (!body || typeof body !== "object") return fallback;
  // FastAPI 常见 { detail: ... }
  const detail = (body as { detail?: unknown }).detail;
  // detail 是字符串
  if (typeof detail === "string") {
    return { message: detail, risk: detail };
  }
  // detail 是对象：{ message, code, risk, ... }
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    const message = String(d.message || d.detail || "需要确认高危命令");
    const risk = String(d.risk || message);
    const code = typeof d.code === "string" ? d.code : undefined;
    return { message, risk, code };
  }
  return fallback;
}

/** 判断是否为「需要人工审批」的 409 */
function isApprovalRequired(status: number, parsed: { code?: string; message: string }): boolean {
  // 必须是 409
  if (status !== 409) return false;
  // 优先看业务码
  if (parsed.code === "SANDBOX_APPROVAL_REQUIRED") return true;
  // 兼容只返回中文 message 的情况
  return /审批|确认|高危/.test(parsed.message);
}

/** 底层 POST JSON */
async function postJson(
  path: string, // 如 /api/sandbox/sessions/xxx/exec
  body: unknown, // 请求体
): Promise<Response> {
  // 发请求
  return fetch(`${getApiBase()}${path}`, {
    method: "POST", // POST
    headers: {
      "Content-Type": "application/json", // JSON
      ...authHeaders(), // Bearer
    },
    body: JSON.stringify(body), // 序列化
  });
}

/** 把成功响应收成 SandboxExecResult */
async function readExec(res: Response): Promise<SandboxExecResult> {
  // 解析 JSON
  return (await res.json()) as SandboxExecResult;
}

/**
 * 通用：发请求 → 若需审批则弹卡 → 允许则重放。
 * replayBody：用户允许后再次提交的 body（已含 approved:true）。
 */
async function withApproval(
  path: string, // API 路径
  firstBody: Record<string, unknown>, // 首次 body
  replayBody: Record<string, unknown>, // 批准后 body
  meta: {
    sessionId: string; // 会话
    kind: "shell" | "pwsh" | "exec"; // 种类
    argv?: string[]; // argv
    command?: string; // 命令字符串
    vertical?: string; // 垂直
  },
): Promise<SandboxExecResult> {
  // 第一次尝试
  const res = await postJson(path, firstBody);
  // 登录失效
  if (handleUnauthorized(res, path)) {
    throw new Error("登录已失效，请重新登录");
  }
  // 成功
  if (res.ok) {
    return readExec(res);
  }
  // 读错误体
  let raw: unknown = null;
  try {
    raw = await res.json();
  } catch {
    raw = null;
  }
  const parsed = parseDetail(raw);
  // 非审批类错误直接抛
  if (!isApprovalRequired(res.status, parsed)) {
    throw new Error(parsed.message || `请求失败 ${res.status}`);
  }
  // 弹出底部确认卡，等待用户
  const allowed = await requestApproval({
    sessionId: meta.sessionId,
    kind: meta.kind,
    argv: meta.argv,
    command: meta.command,
    risk: parsed.risk || parsed.message,
    vertical: meta.vertical,
  });
  // 用户拒绝
  if (!allowed) {
    throw new Error("用户拒绝执行该命令");
  }
  // 带 approved:true 重放
  const res2 = await postJson(path, replayBody);
  if (handleUnauthorized(res2, path)) {
    throw new Error("登录已失效，请重新登录");
  }
  if (!res2.ok) {
    const t = await res2.text().catch(() => res2.statusText);
    throw new Error(t || "批准后重放失败");
  }
  return readExec(res2);
}

/** 申请沙箱会话 */
export async function acquireSandboxSession(vertical = "generic"): Promise<{
  id: string;
  vertical: string;
  capabilities: string[];
  createdAt: string;
  status: string;
  policy?: { mode: string; networkMode: string; approval: string };
}> {
  const path = "/api/sandbox/sessions";
  const res = await postJson(path, { vertical });
  if (handleUnauthorized(res, path)) throw new Error("登录已失效，请重新登录");
  if (!res.ok) {
    const t = await res.text().catch(() => res.statusText);
    throw new Error(t || "申请沙箱失败");
  }
  return res.json();
}

/** argv 执行（推荐路径） */
export async function sandboxExecArgv(
  sessionId: string,
  argv: string[],
  opts?: { vertical?: string },
): Promise<SandboxExecResult> {
  const path = `/api/sandbox/sessions/${sessionId}/exec`;
  const first = { argv, approved: false };
  const replay = { argv, approved: true };
  return withApproval(path, first, replay, {
    sessionId,
    kind: "exec",
    argv,
    vertical: opts?.vertical,
  });
}

/** 兼容旧 shell 字符串接口 */
export async function sandboxShell(
  sessionId: string,
  command: string,
  opts?: { vertical?: string },
): Promise<SandboxExecResult> {
  const path = `/api/sandbox/sessions/${sessionId}/shell`;
  const first = { command, approved: false };
  const replay = { command, approved: true };
  return withApproval(path, first, replay, {
    sessionId,
    kind: "shell",
    command,
    vertical: opts?.vertical,
  });
}

/** 释放会话 */
export async function releaseSandboxSession(sessionId: string): Promise<void> {
  const path = `/api/sandbox/sessions/${sessionId}`;
  const res = await fetch(`${getApiBase()}${path}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  if (handleUnauthorized(res, path)) throw new Error("登录已失效，请重新登录");
  if (!res.ok) {
    const t = await res.text().catch(() => res.statusText);
    throw new Error(t || "释放沙箱失败");
  }
}