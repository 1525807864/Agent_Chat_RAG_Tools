// ============================================================================
// attachment.ts：附件与文件树的 TypeScript 类型定义
// ============================================================================

// Attachment：挂到「即将发送」这一轮对话上的单个附件
export type Attachment = {
  // 前端生成的唯一 id，用作 React key 与删除定位
  id: string;
  // 文件名，例如 README.md
  name: string;
  // 相对路径（选文件夹时有）；普通上传可省略
  path?: string;
  // MIME 类型，例如 text/plain、application/json
  mime: string;
  // 文件字节大小，用于前端限额校验
  size: number;
  // 已读出的文本正文，发送时拼进 message
  content: string;
  // 来源：直接上传 或 从文件树点选
  source: "upload" | "workspace";
};

// FileTreeNode：浏览器内存里的目录/文件树节点（非实时磁盘监视）
export type FileTreeNode = {
  // 节点唯一 id
  id: string;
  // 显示名称（目录名或文件名）
  name: string;
  // 相对根的路径；根可为 ""
  path: string;
  // true=文件夹；false=文件
  isDir: boolean;
  // 子节点列表（仅目录有）
  children?: FileTreeNode[];
  // 文件节点挂着原生 File，点选时再 file.text()
  file?: File;
};
