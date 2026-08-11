// ============================================================================
// TypewriterText.tsx：打字机 —— instant 全文 / 非 instant 逐字追上
// ============================================================================

// 导入 Effect 与 State
import { useEffect, useState } from "react";

// Props
type Props = {
  text: string; // 目标全文
  instant?: boolean; // true=无动画
  speedMs?: number; // 每字间隔毫秒
};

// 导出组件
export function TypewriterText({
  text, // 目标文本
  instant = false, // 默认要打字
  speedMs = 22, // 默认 22ms/字
}: Props) {
  // shown：当前已显示前缀；instant 时初始即全文
  const [shown, setShown] = useState(() => (instant ? text : ""));

  // instant 模式：text 变化立刻对齐
  useEffect(() => {
    if (instant) {
      setShown(text); // 同步全文
    }
  }, [instant, text]); // 依赖 instant 与 text

  // 非 instant：用 timeout 逐字增加 shown
  useEffect(() => {
    if (instant) return; // instant 不跑动画

    // 已经追上或超过
    if (shown.length >= text.length) {
      // 目标变短时对齐
      if (shown !== text && text.length < shown.length) {
        setShown(text);
      }
      return; // 停表
    }

    // 安排下一字
    const timer = window.setTimeout(() => {
      setShown(text.slice(0, shown.length + 1)); // 多显示 1 个字符
    }, speedMs);

    // 清理定时器，防重叠
    return () => window.clearTimeout(timer);
  }, [instant, text, shown, speedMs]); // shown 变化会触发下一拍

  // text 清空时重置 shown
  useEffect(() => {
    if (!text) setShown(""); // 空助手气泡重置
  }, [text]);

  // 用 Fragment 输出文本，不额外包节点
  return <>{shown}</>;
}
