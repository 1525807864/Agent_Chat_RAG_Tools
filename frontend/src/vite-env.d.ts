// ============================================================================
// vite-env.d.ts：仅类型声明，无运行时代码
// ============================================================================
// 三斜线指令：引入 Vite 客户端类型（import.meta.env / HMR 等）
/// <reference types="vite/client" />

// 扩展 Vite 识别的环境变量表（.env 里 VITE_ 前缀才会进前端）
interface ImportMetaEnv {
  // 后端 API 根地址，例如 http://127.0.0.1:8020
  readonly VITE_API_BASE: string;
}

// 扩展标准 ImportMeta，使 import.meta.env 带上上面的字段
interface ImportMeta {
  // env 对象只读，防止业务代码误改
  readonly env: ImportMetaEnv;
}

// Electron preload 通过 contextBridge 注入到 window 的白名单 API
interface ElectronAPI {
  // 是否运行在 Electron 壳内（网页里为 undefined，此字段在壳内为 true）
  isElectron: boolean;
  // 桌面端约定的后端 Base URL
  apiBase: string;
  // 操作系统平台字符串：win32 / darwin / linux
  platform: string;
}

interface WorkspaceAPI {
  /** 选择工作区目录 */
  selectDirectory: () => Promise<string | null>;
  /** 列出目录内容 */
  listDir: (
    /** 绝对路径 */
    absRoot: string,
    /** 相对路径，目录也不要末尾 / */
    relPath?: string,
  ) => Promise<
    { name: string; path: string; isDir: boolean; children?: unknown[] }[]
  >;
  /** 读取文件内容 */
  readFile: (absRoot: string, relPath: string) => Promise<string>;
  /** 写入文件内容 */
  writeFile: (absRoot: string, relPath: string, content: string) => Promise<void>;
}


// 把可选的 electronAPI / workspaceAPI 挂到全局 Window 类型上
interface Window {
  // 浏览器访问时可能不存在，故用 ?
  electronAPI?: ElectronAPI;
  /** 桌面端工作区文件 API；纯浏览器为 undefined */
  workspaceAPI?: WorkspaceAPI;
}
