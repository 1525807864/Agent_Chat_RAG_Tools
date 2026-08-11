/**
 * 工作区领域类型（完整版）
 * - path 一律用「相对 workspace root」的 POSIX 风格：src/app.py
 * - absRoot 只在 Electron 侧使用，不要发给不可信第三方
 */

/** 树节点：目录可懒加载 children */
export type WsNode = {
    /** 文件名或目录名 */
    name: string;
    /** 相对根路径，目录也不要末尾 / */
    path: string;
    /** 是否目录 */
    isDir: boolean;
    /** 子节点，懒加载 */
    children?: WsNode[];
};

/** 已打开/已读入上下文的文件 */
export type OpenFile = {
    /** 相对根路径，目录也不要末尾 / */
    path: string;
    /** 文件内容 */
    content: string;
    /** 字节或字符数，便于限额 */
    size: number;
};

/** 发给后端的工作区上下文（放进 ChatRequest） */
export type WorkspacePayload = {
    /** 绝对路径；仅桌面端本地可信场景使用 */
    workspace_root: string;
    /** 本轮优先塞进上下文的文件（打开的/勾选的） */
    files: OpenFile[];
};

/** Electron 暴露的工作区 API（与 preload 对齐） */
export type WorkspaceAPI = {
    /** 选择工作区目录 */
    selectDirectory: () => Promise<string | null>;
    /** 列出目录内容 */
    listDir: (absRoot: string, relPath?: string) => Promise<WsNode[]>;
    /** 读取文件内容 */
    readFile: (absRoot: string, relPath: string) => Promise<string>;
    /** 写入文件内容 */
    writeFile: (absRoot: string, relPath: string, content: string) => Promise<void>;
};