// ============================================================================
// useAttachments.ts：本轮附件状态 + 拼进 message 的工具函数
// ============================================================================

// 导入 Hook
import { useCallback, useState } from "react";
// 导入附件类型
import type { Attachment } from "../types/attachment";

// 单文件最大 200KB
const MAX_FILE_BYTES = 200 * 1024;
// 全部附件合计最大 1MB
const MAX_TOTAL_BYTES = 1024 * 1024;
// 允许的文本扩展名（MIME 不准时的兜底）
const TEXT_EXT =
  /\.(txt|md|markdown|py|ts|tsx|js|jsx|json|css|html|xml|yml|yaml|toml|ini|csv|log|sh|bat|ps1|c|cpp|h|java|go|rs|sql)$/i;

// 生成短唯一 id
function uid() {
  // 时间戳 + 随机串
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// 判断是否按文本处理
function isTextFile(file: File): boolean {
  // text/* 一律接受
  if (file.type.startsWith("text/")) return true;
  // JSON 常见 MIME
  if (file.type === "application/json") return true;
  // 否则看扩展名
  return TEXT_EXT.test(file.name);
}

// 把用户文字与附件拼成一条后端 message
export function buildMessageWithAttachments(
  text: string, // 输入框原文
  attachments: Attachment[], // 当前附件列表
): string {
  // 去掉首尾空白
  const body = text.trim();
  // 无附件：直接返回正文
  if (attachments.length === 0) return body;

  // 每个附件变成一个 markdown 代码块段落
  const blocks = attachments.map((a) => {
    // 显示路径优先，否则文件名
    const label = a.path || a.name;
    // 固定格式，便于模型识别
    return `---\n[附件: ${label}]\n\`\`\`\n${a.content}\n\`\`\``;
  });
  // 拼接：空 body 时 filter 掉假值，避免多余空段
  return [body, ...blocks].filter(Boolean).join("\n\n");
}

// Hook：附件列表增删清
export function useAttachments() {
  // 当前附件数组
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  // 最近一次错误/跳过原因
  const [error, setError] = useState<string | null>(null);

  // 已挂附件总字节
  const totalBytes = attachments.reduce((s, a) => s + a.size, 0);

  // 从 FileList 批量添加（上传按钮）
  const addFiles = useCallback(async (files: FileList | File[]) => {
    // 清旧错误
    setError(null);
    // 转成真正数组
    const list = Array.from(files);
    // 本批待追加
    const next: Attachment[] = [];
    // 本批已计入大小
    let addedBytes = 0;

    // 逐个处理
    for (const file of list) {
      // 非文本跳过
      if (!isTextFile(file)) {
        setError(`跳过非文本：${file.name}`);
        continue;
      }
      // 单文件超限
      if (file.size > MAX_FILE_BYTES) {
        setError(`过大（>${MAX_FILE_BYTES}B）：${file.name}`);
        continue;
      }
      // 合计超限则停止继续添加
      if (totalBytes + addedBytes + file.size > MAX_TOTAL_BYTES) {
        setError("附件总大小超限");
        break;
      }

      try {
        // 异步读全文
        const content = await file.text();
        // 文件夹选择时浏览器填充的相对路径
        const rel = (file as File & { webkitRelativePath?: string })
          .webkitRelativePath;
        // 推入本批
        next.push({
          id: uid(), // 新 id
          name: file.name, // 文件名
          path: rel || undefined, // 有相对路径才存
          mime: file.type || "text/plain", // MIME 兜底
          size: file.size, // 大小
          content, // 正文
          source: rel ? "workspace" : "upload", // 来源标记
        });
        // 累计本批字节
        addedBytes += file.size;
      } catch {
        // 读失败提示
        setError(`读取失败：${file.name}`);
      }
    }

    // 有成功项则合并进 state
    if (next.length > 0) {
      setAttachments((prev) => [...prev, ...next]);
    }
  }, [totalBytes]); // totalBytes 变化时重建，限额才准

  // 追加一条已读好的附件（文件树点选）
  const addAttachment = useCallback((item: Omit<Attachment, "id">) => {
    // 清错误
    setError(null);
    // 单文件限额
    if (item.size > MAX_FILE_BYTES) {
      setError(`过大：${item.name}`);
      return;
    }
    // 函数式更新，便于去重与合计
    setAttachments((prev) => {
      // 当前合计
      const sum = prev.reduce((s, a) => s + a.size, 0);
      // 超总限则不动列表
      if (sum + item.size > MAX_TOTAL_BYTES) {
        setError("附件总大小超限");
        return prev;
      }
      // 去重键：path 或 name
      const key = item.path || item.name;
      // 去掉同名旧项
      const filtered = prev.filter((a) => (a.path || a.name) !== key);
      // 追加新项（补 id）
      return [...filtered, { ...item, id: uid() }];
    });
  }, []);

  // 按 id 删除一个 chip
  const remove = useCallback((id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }, []);

  // 清空全部
  const clear = useCallback(() => {
    setAttachments([]); // 列表置空
    setError(null); // 错误清除
  }, []);

  // 导出 API
  return {
    attachments, // 列表
    error, // 错误文案
    addFiles, // 上传添加
    addAttachment, // 树点选添加
    remove, // 删单个
    clear, // 清空
  };
}
