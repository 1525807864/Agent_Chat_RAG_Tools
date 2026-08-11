/**
 * FileTree：支持内存树（浏览器）与懒加载工作区树（Electron）。
 */
import { useState } from "react";

/** 统一树节点（浏览器 FileTreeNode / 工作区 WsNode 都映射成这个） */
export type TreeNode = {
  id: string;
  name: string;
  path: string;
  isDir: boolean;
  children?: TreeNode[];
  /** 浏览器内存树才有 */
  file?: File;
};

type Props = {
  root: TreeNode;
  onPickFile: (node: TreeNode) => void;
  /** 展开目录时懒加载子节点（Electron 工作区） */
  onLoadChildren?: (relPath: string) => Promise<TreeNode[]>;
};

function TreeNodeView({
  node,
  depth,
  onPickFile,
  onLoadChildren,
}: {
  node: TreeNode;
  depth: number;
  onPickFile: (n: TreeNode) => void;
  onLoadChildren?: (relPath: string) => Promise<TreeNode[]>;
}) {
  const [open, setOpen] = useState(depth < 1);
  const [children, setChildren] = useState<TreeNode[] | undefined>(node.children);
  const [loadingKids, setLoadingKids] = useState(false);

  if (!node.isDir) {
    return (
      <button
        type="button"
        className="file-tree-item file"
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => onPickFile(node)}
        title={node.path}
      >
        📄 {node.name}
      </button>
    );
  }

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    // 首次展开且可懒加载、尚无 children → 拉取
    if (
      next &&
      onLoadChildren &&
      (children === undefined || children.length === 0) &&
      !loadingKids
    ) {
      setLoadingKids(true);
      try {
        const kids = await onLoadChildren(node.path);
        setChildren(kids);
      } finally {
        setLoadingKids(false);
      }
    }
  };

  return (
    <div>
      <button
        type="button"
        className="file-tree-item dir"
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => void toggle()}
        title={node.path}
      >
        {open ? "📂" : "📁"} {node.name}
        {loadingKids ? " …" : ""}
      </button>
      {open &&
        (children ?? []).map((c) => (
          <TreeNodeView
            key={c.id}
            node={c}
            depth={depth + 1}
            onPickFile={onPickFile}
            onLoadChildren={onLoadChildren}
          />
        ))}
    </div>
  );
}

export function FileTree({ root, onPickFile, onLoadChildren }: Props) {
  return (
    <div className="file-tree">
      <TreeNodeView
        node={root}
        depth={0}
        onPickFile={onPickFile}
        onLoadChildren={onLoadChildren}
      />
    </div>
  );
}
