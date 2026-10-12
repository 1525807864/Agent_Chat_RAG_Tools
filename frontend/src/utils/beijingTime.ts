/** 全站展示/写入统一按北京时间（Asia/Shanghai）。 */

const TZ = "Asia/Shanghai";

/** 当前北京时间 ISO（带 +08:00），给 mock / 本地落盘用。 */
export function nowBeijingIso(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const get = (t: string) => parts.find((p) => p.type === t)?.value || "00";
  const ms = String(new Date().getMilliseconds()).padStart(3, "0");
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}:${get("second")}.${ms}+08:00`;
}

/** 把后端时间字符串格式化为北京时间可读文案。 */
export function formatBeijing(value?: string | null): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", { timeZone: TZ, hour12: false });
}
