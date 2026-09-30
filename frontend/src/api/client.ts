// ============================================================================
// client.ts：HTTP 底层 —— 解析 Base URL + 统一 apiJson
// ============================================================================
import { authHeaders } from "../auth/token";
import { clearToken } from "../auth/token";
// 解析后端根地址：Electron > .env > 默认 8020；并去掉末尾斜杠
function resolveApiBase(): string {
  const fromElectron = window.electronAPI?.apiBase?.replace(/\/$/, "");
  const fromEnv = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(
    /\/$/,
    "",
  );
  // 桌面与网页共用云 API：Vite 里配的 VITE_API_BASE 优先，避免 preload 默认 127.0.0.1
  if (fromEnv) return fromEnv;
  if (fromElectron) return fromElectron;
  // 网页由 Nginx 同源反代 /api；空 base 让 fetch("/api/...") 打到当前域名
  if (typeof window !== "undefined" && !window.electronAPI) {
    return "";
  }
  return "http://127.0.0.1:8020";
}

// 模块加载时计算一次，避免每次请求重复解析
const API_BASE = resolveApiBase();

// 导出给探活文案、SSE 等需要裸 Base 的调用方
export function getApiBase(): string {
  // 原样返回缓存的 Base
  return API_BASE;
}

// 把失败的 Response 转成 Error（解析 FastAPI detail）
async function parseError(res: Response): Promise<Error> {
  // 默认文案用 HTTP 状态码 + statusText
  let detail = `${res.status} ${res.statusText}`;
  try {
    // 尝试按 JSON 解析响应体
    const body = await res.json();
    // detail 为字符串时直接使用
    if (typeof body?.detail === "string") {
      // 覆盖为后端业务错误信息
      detail = body.detail;
    } else if (body?.detail != null) {
      // detail 为数组/对象时序列化成字符串展示
      detail = JSON.stringify(body.detail);
    }
  } catch {
    // 非 JSON：保留 statusText，什么都不做
  }
  // 包装成 Error 抛给上层 catch
  return new Error(detail);
}

/** 401 时清 token 并广播 auth:logout；登录/注册接口返回 false。 */
export function handleUnauthorized(res: Response, path: string): boolean {
  if (res.status !== 401) return false;
  if (
    path.startsWith("/api/auth/login") ||
    path.startsWith("/api/auth/register")
  ) {
    return false;
  }
  clearToken();
  window.dispatchEvent(new CustomEvent("auth:logout"));
  return true;
}

// 通用 JSON 请求：拼 URL、设 Header、校验 ok、返回 T
export async function apiJson<T>(
  path: string, // 以 / 开头的路径
  init?: RequestInit, // 标准 fetch 选项
): Promise<T> {
  // 发起请求：Base + path
  const res = await fetch(`${API_BASE}${path}`, {
    // 展开调用方传入的 method/body/signal 等
    ...init,
    // 合并 headers：默认 JSON，再覆盖调用方自定义头
    headers: {
      // 告诉后端请求体是 JSON
      "Content-Type": "application/json",
      ...authHeaders(),
      // 调用方额外 headers（若有）
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    // 业务接口 Token 失效：清 token + 通知 App 回登录页（登录/注册 401 除外）
    if (handleUnauthorized(res, path)) {
      throw new Error("登录已失效，请重新登录");
    }
    throw await parseError(res);
  }
  return (await res.json()) as T;
}