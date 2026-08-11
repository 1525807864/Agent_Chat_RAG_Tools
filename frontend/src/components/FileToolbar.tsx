/**
 * FileToolbar：
 * - 桌面端：打开 Electron 工作区 + 懒加载树 + openFiles chips
 * - 浏览器：保留「添加文件 / webkitdirectory」附件降级
 */
import { useRef, useState, type InputHTMLAttributes } from "react";
import type { Attachment, FileTreeNode } from "../types/attachment";
import type { OpenFile, WsNode } from "../types/workspace";
import { FileTree, type TreeNode } from "./FileTree";

type WorkspaceProps = {
  root: string | null;
  tree: WsNode[];
  openFiles: OpenFile[];
  error: string | null;
  hasDesktopFs: boolean;
  onOpenWorkspace: () => void | Promise<void>;
  onListChildren: (relPath: string) => Promise<WsNode[]>;
  onOpenFile: (relPath: string) => void | Promise<void>;
  onRemoveOpenFile: (relPath: string) => void;
};

type Props = {
  attachments: Attachment[];
  error: string | null;
  disabled?: boolean;
  onAddFiles: (files: FileList | File[]) => void | Promise<void>;
  onRemove: (id: string) => void;
  onClear: () => void;
  onPickTreeFile: (node: FileTreeNode) => void | Promise<void>;
  workspace?: WorkspaceProps;
};

function buildTreeFromFileList(files: FileList): FileTreeNode {
  const root: FileTreeNode = {
    id: "root",
    name: "workspace",
    path: "",
    isDir: true,
    children: [],
  };

  const ensureDir = (parts: string[], parent: FileTreeNode): FileTreeNode => {
    let cur = parent;
    let acc = "";
    for (const part of parts) {
      acc = acc ? `${acc}/${part}` : part;
      if (!cur.children) cur.children = [];
      let next = cur.children.find((c) => c.isDir && c.name === part);
      if (!next) {
        next = {
          id: `dir:${acc}`,
          name: part,
          path: acc,
          isDir: true,
          children: [],
        };
        cur.children.push(next);
      }
      cur = next;
    }
    return cur;
  };

  Array.from(files).forEach((file, i) => {
    const rel =
      (file as File & { webkitRelativePath?: string }).webkitRelativePath ||
      file.name;
    const parts = rel.split("/").filter(Boolean);
    const fileName = parts.pop()!;
    const dir = parts.length ? ensureDir(parts, root) : root;
    if (!dir.children) dir.children = [];
    dir.children.push({
      id: `file:${rel}:${i}`,
      name: fileName,
      path: rel,
      isDir: false,
      file,
    });
  });

  if (root.children?.length === 1 && root.children[0].isDir) {
    return root.children[0];
  }
  return root;
}

function toTreeNode(n: FileTreeNode): TreeNode {
  return {
    id: n.id,
    name: n.name,
    path: n.path,
    isDir: n.isDir,
    file: n.file,
    children: n.children?.map(toTreeNode),
  };
}

function wsToTreeNode(n: WsNode): TreeNode {
  return {
    id: n.path || n.name,
    name: n.name,
    path: n.path,
    isDir: n.isDir,
    children: n.children?.map(wsToTreeNode),
  };
}

export function FileToolbar({
  attachments,
  error,
  disabled,
  onAddFiles,
  onRemove,
  onClear,
  onPickTreeFile,
  workspace,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const dirRef = useRef<HTMLInputElement>(null);
  const [memTree, setMemTree] = useState<FileTreeNode | null>(null);
  const [showTree, setShowTree] = useState(false);

  const ws = workspace;
  const desktop = Boolean(ws?.hasDesktopFs);
  const combinedError = ws?.error || error;

  const desktopRoot: TreeNode | null =
    ws?.root && ws.tree
      ? {
          id: "ws-root",
          name: ws.root.split(/[/\\]/).filter(Boolean).pop() || "workspace",
          path: "",
          isDir: true,
          children: ws.tree.map(wsToTreeNode),
        }
      : null;

  return (
    <div className="file-toolbar">
      <div className="file-toolbar-actions">
        {desktop ? (
          <>
            <button
              type="button"
              className="btn primary"
              disabled={disabled}
              onClick={() => void ws!.onOpenWorkspace()}
              title="选择本地文件夹作为 Agent 工作区（可读写）"
            >
              打开工作区
            </button>
            {ws!.root && (
              <button
                type="button"
                className="btn"
                onClick={() => setShowTree((v) => !v)}
              >
                {showTree ? "收起目录" : "展开目录"}
              </button>
            )}
            {ws!.openFiles.length > 0 && (
              <button
                type="button"
                className="btn danger"
                onClick={() => {
                  for (const f of [...ws!.openFiles]) {
                    ws!.onRemoveOpenFile(f.path);
                  }
                }}
              >
                清空已打开
              </button>
            )}
          </>
        ) : (
          <>
            <button
              type="button"
              className="btn"
              disabled={disabled}
              onClick={() => fileRef.current?.click()}
              title="浏览器降级：选文本文件读入附件（不能写回磁盘）"
            >
              添加文件
            </button>
            <button
              type="button"
              className="btn"
              disabled={disabled}
              onClick={() => dirRef.current?.click()}
              title="浏览器内存树（不能写盘）"
            >
              打开文件夹
            </button>
            {memTree && (
              <button
                type="button"
                className="btn"
                onClick={() => setShowTree((v) => !v)}
              >
                {showTree ? "收起目录" : "展开目录"}
              </button>
            )}
            {attachments.length > 0 && (
              <button type="button" className="btn danger" onClick={onClear}>
                清空附件
              </button>
            )}
          </>
        )}
      </div>

      {ws?.root && (
        <p className="muted" style={{ margin: 0, fontSize: 12 }}>
          工作区：<code>{ws.root}</code>
          {modeHint()}
        </p>
      )}

      {!desktop && (
        <>
          <input
            ref={fileRef}
            type="file"
            multiple
            hidden
            accept=".txt,.md,.py,.ts,.tsx,.js,.jsx,.json,.css,.html,.yml,.yaml,.csv,.log,.sql"
            onChange={(e) => {
              if (e.target.files?.length) void onAddFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <input
            ref={dirRef}
            type="file"
            hidden
            multiple
            {...({
              webkitdirectory: "",
              directory: "",
            } as InputHTMLAttributes<HTMLInputElement>)}
            onChange={(e) => {
              if (!e.target.files?.length) return;
              setMemTree(buildTreeFromFileList(e.target.files));
              setShowTree(true);
              e.target.value = "";
            }}
          />
        </>
      )}

      {combinedError && (
        <div className="file-toolbar-error">{combinedError}</div>
      )}

      {/* 桌面：已打开文件 chips */}
      {desktop && ws!.openFiles.length > 0 && (
        <div className="file-chips">
          {ws!.openFiles.map((f) => (
            <span className="file-chip" key={f.path} title={f.path}>
              <span className="file-chip-name">{f.path}</span>
              <button
                type="button"
                className="file-chip-x"
                onClick={() => ws!.onRemoveOpenFile(f.path)}
                aria-label="移除"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* 浏览器：附件 chips */}
      {!desktop && attachments.length > 0 && (
        <div className="file-chips">
          {attachments.map((a) => (
            <span className="file-chip" key={a.id} title={a.path || a.name}>
              <span className="file-chip-name">{a.path || a.name}</span>
              <button
                type="button"
                className="file-chip-x"
                onClick={() => onRemove(a.id)}
                aria-label="移除"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {showTree && desktop && desktopRoot && (
        <div className="file-tree-panel">
          <FileTree
            root={desktopRoot}
            onPickFile={(n) => {
              if (!n.isDir) void ws!.onOpenFile(n.path);
            }}
            onLoadChildren={async (relPath) => {
              const kids = await ws!.onListChildren(relPath);
              return kids.map(wsToTreeNode);
            }}
          />
        </div>
      )}

      {showTree && !desktop && memTree && (
        <div className="file-tree-panel">
          <FileTree
            root={toTreeNode(memTree)}
            onPickFile={(n) => {
              // 还原为 FileTreeNode 形状给旧回调
              void onPickTreeFile({
                id: n.id,
                name: n.name,
                path: n.path,
                isDir: n.isDir,
                file: n.file,
              });
            }}
          />
        </div>
      )}
    </div>
  );
}

function modeHint() {
  return " · 改代码请把 mode 设为 agent";
}
