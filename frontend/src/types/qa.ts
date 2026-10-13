/**
 * 测试工作台[前端壳]专用类型
 * 
 */
export type QaKind = 
    | "functional"  // 功能测试
    | "api"         // 接口测试
    | "blackbox"    // 黑盒/探索
    | "performance" // 性能测试
    | "security"    // 安全测试
    | "compat"      // 兼容性测试

/**用例生命周期状态：决定绿点 / 灰点 */
export type QaCaseStatus = "draft" | "confirmed" | "ready" | "passed" | "failed";
/**工作台页面态：列表页 or 项目内三栏 */
export type QaView = "list" | "workbench";
/**
 * 内容来源文档
 */
export interface QaSourceDoc {
    id: string,
    name: string,
    kind: "docx" | "pdf" | "md" | "url" | "text"; //类型图标用
    excerpt: string; //摘录，中栏卡片展示
    rows: QaSourceRow[];  //右栏表格行
}
/**右栏[需求表]一行 */
export interface QaSourceRow {
    no: string; //编号
    name: string; //名称
    reqId: string; //关联需求ID
    description: string; //描述
}
export interface QaProject {
    id: string; //API ID
    name: string; //项目名
    baseUrl: string; //基础URL
    goal: string; //目标
    createdAt: string; //创建时间
    sourceDocs: QaSourceDoc[]; //来源文档
}
/** 测试树上的节点（需求包 / 子用例） */
export interface QaCase {
    id: string;
    projectId: string;
    parentId: string | null; // null = 根（需求包）
    code: string; // 展示编号，如 4.1.1
    title: string;
    kind: QaKind;
    requirement: string; // 原始需求文本
    fused: string; // 智能融合稿（可编辑）
    steps: string[]; // 步骤
    expected: string; // 期望
    status: QaCaseStatus;
    sourceDocIds: string[]; // 关联来源文档
  }

/** 一次冒烟/执行（壳阶段 verdict 用 pass/fail） */
export interface QaRun {
  id: string;
  projectId: string;
  caseIds: string[];
  verdict: "pass" | "fail" | "error";
  summary: string;
  artifacts?: Record<string, unknown>;
  createdAt: string;
}

/** hook 对外暴露的状态快照 */
export interface QaShellState {
  view: QaView;
  projects: QaProject[];
  activeProjectId: string | null;
  cases: QaCase[];
  runs: QaRun[];
  selectedCaseId: string | null;
  treeQuery: string;
  settingsOpen: boolean;
  busy: boolean;
  notice: string;
}
/**左侧产品导航，不是用例树 */
export type QaNav = 
    | "projects" //项目空间
    | "cases" //测试内容
    | "runs" //执行记录
    | "report" //报告
    | "members" //用户与权限
    | "knowledge"; //知识库

/**本租户成员角色，只在当前租户内有效 */
export type QaMemberRole = "admin" | "execute" | "view";

export interface QaMember {
  id: string;
  name: string;
  role: QaMemberRole;
  /** 登录用户名，等于 JWT sub */
  userId: string;
}

/** GET /api/qa/me */
export interface QaMe {
  userId: string;
  tenantId: string;
  role: QaMemberRole;
  permissions: {
    canWriteProject: boolean;
    canWriteCase: boolean;
    canExecute: boolean;
    canManageMembers: boolean;
  };
}
/**右侧助手的一条消息 */
export interface QaChatTurn {
  id: string,
  role: "user" | "assistant";
  text: string;
}

/** 右侧实时刷的一步 UI 测试 */
export interface QaUiStep {
  i: number;
  action: string;
  detail: string;
  ok: boolean;
  error?: string;
}