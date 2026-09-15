// ============================================================================
// client.ts：HTTP 底层 —— 解析 Base URL + 统一 apiJson
// ============================================================================
import { authHeaders } from "../auth/token";
// 解析后端根地址：Electron > .env > 默认 8020；并去掉末尾斜杠
function resolveApiBase(): string {
  // 尝试读 Electron preload 注入的 apiBase
  const fromElectron = window.electronAPI?.apiBase?.replace(/\/$/, "");
  // 若桌面端有值，优先使用
  if (fromElectron) return fromElectron;
  // 再读 Vite 注入的环境变量 VITE_API_BASE
  const fromEnv = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(
    /\/$/, // 正则：去掉结尾 /
    "", // 替换为空串
  );
  // 都没有则硬编码本地默认端口（与前端 .env 常见配置一致）
  return fromEnv || "http://127.0.0.1:8020";
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
  // HTTP 非 2xx：转 Error 抛出
  if (!res.ok) {
    // await 解析错误体后 throw
    throw await parseError(res);
  }
  // 成功：解析 JSON 并断言为泛型 T
  return (await res.json()) as T;
}
 