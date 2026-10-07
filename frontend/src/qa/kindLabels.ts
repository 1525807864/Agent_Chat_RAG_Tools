/**
 * 用例类型->中文名 + css修饰class后缀
 */
import type { QaKind } from "../types/qa";

export const KIND_LABEL: Record<QaKind,string> = {
    functional: "功能测试",
    api: "接口测试",
    blackbox: "黑盒/探索",
    performance: "性能测试",
    security: "安全测试",
    compat: "兼容性测试",
};
export const STATUS_LABEL: Record<string,string> = {
  draft: "草稿",
  confirmed: "已确认",
  ready: "待执行",
  passed: "通过",
  failed: "失败",
}