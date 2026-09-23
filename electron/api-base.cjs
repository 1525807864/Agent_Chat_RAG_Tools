/**
 * 桌面端 API 根地址。
 * LANGCHAIN_API_BASE 可覆盖；未设置时默认本机 8020（与 frontend/.env 一致）。
 * 连公网时显式设置，例如：LANGCHAIN_API_BASE=http://39.106.64.240
 */
const DEFAULT_LOCAL_API = "http://127.0.0.1:8020";
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
  DEFAULT_LOCAL_API,
  DEFAULT_CLOUD_API,
  API_BASE: resolveApiBase(),
  isLocalApi,
};
