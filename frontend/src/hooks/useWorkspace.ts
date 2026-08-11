/**
 * useWorkspace：完整版工作区状态
 * - 有 window.workspaceAPI → Electron 真磁盘
 * - 否则可降级为空操作 / 接旧 useAttachments
 */
import { useCallback, useState } from "react";
import type { OpenFile, WsNode, WorkspacePayload } from "../types/workspace";

const MAX_OPEN = 12; // 本轮最多带给模型的文件数
const MAX_EACH = 200_000; // 单文件字符上限（按需调）

export function useWorkspace() {
  const [root, setRoot] = useState<string | null>(null); // 绝对路径
  const [tree, setTree] = useState<WsNode[]>([]); // 根下一层（可再扩展缓存）
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]); // 已读入上下文
  const [error, setError] = useState<string | null>(null);

  const api = typeof window !== "undefined" ? window.workspaceAPI : undefined;

  /** 打开工作区 */
  const openWorkspace = useCallback(async () => {
    setError(null);
    if (!api) {
      setError("当前不是桌面端，无法打开本地工作区（请用 Electron 运行）");
      return;
    }
    const dir = await api.selectDirectory();
    if (!dir) return;
    setRoot(dir);
    setOpenFiles([]);
    const nodes = await api.listDir(dir, "");
    setTree(nodes as WsNode[]);
  }, [api]);

  /** 展开某目录：返回子节点（交给 FileTree 懒加载） */
  const listChildren = useCallback(
    async (relPath: string) => {
      if (!api || !root) return [];
      return (await api.listDir(root, relPath)) as WsNode[];
    },
    [api, root],
  );

  /** 点文件：读入并加入 openFiles（供本轮 Agent 使用） */
  const openFile = useCallback(
    async (relPath: string) => {
      if (!api || !root) return;
      setError(null);
      try {
        const content = await api.readFile(root, relPath);
        if (content.length > MAX_EACH) {
          setError(`文件过大：${relPath}`);
          return;
        }
        setOpenFiles((prev) => {
          const rest = prev.filter((f) => f.path !== relPath);
          const next = [
            ...rest,
            { path: relPath, content, size: content.length },
          ];
          // 超出数量丢最旧
          return next.slice(-MAX_OPEN);
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [api, root],
  );

  const removeOpenFile = useCallback((relPath: string) => {
    setOpenFiles((prev) => prev.filter((f) => f.path !== relPath));
  }, []);

  /** 组装发给后端的 payload；无 root 则 null */
  const toPayload = useCallback((): WorkspacePayload | null => {
    if (!root) return null;
    return { workspace_root: root, files: openFiles };
  }, [root, openFiles]);

  /**
   * 可选：Agent 若通过 meta.edits 返回补丁，前端再 writeFile
   * （若你走「Python 工具直接写盘」，这个可不调用）
   */
  const applyEdit = useCallback(
    async (relPath: string, content: string) => {
      if (!api || !root) throw new Error("无工作区");
      await api.writeFile(root, relPath, content);
      // 同步内存中的 openFiles
      setOpenFiles((prev) =>
        prev.map((f) => (f.path === relPath ? { ...f, content, size: content.length } : f)),
      );
    },
    [api, root],
  );

  return {
    root,
    tree,
    openFiles,
    error,
    openWorkspace,
    listChildren,
    openFile,
    removeOpenFile,
    toPayload,
    applyEdit,
    hasDesktopFs: Boolean(api),
  };
}