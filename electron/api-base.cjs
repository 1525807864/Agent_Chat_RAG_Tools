/**
 * 桌面端 API 根地址。
 * LANGCHAIN_API_BASE 可覆盖；未设置时走云上 Nginx（80，不要写 :8020）。
 */
const DEFAULT_CLOUD_API = "http://39.106.64.240";

function resolveApiBase() {
  const fromEnv = (process.env.LANGCHAIN_API_BASE || "").replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  return DEFAULT_CLOUD_API;
}

function isLocalApi(url) {
  return /127\.0\.0\.1|localhost/i.test(url || "");
}

module.exports = {
  DEFAULT_CLOUD_API,
  API_BASE: resolveApiBase(),
  isLocalApi,
};
