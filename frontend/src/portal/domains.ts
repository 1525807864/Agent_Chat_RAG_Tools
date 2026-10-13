// ============================================================================
// domains.ts：门户首页的「领域 / 垂直 Agent」清单（配置驱动）
// - status: "ready" 可进入已有工作台；"soon" 只展示「即将开放」
// - workspace: 对应 App 里的工作区标识（chat / qa / ops）
// ============================================================================

/** 侧栏 / 筛选用的分组 id */
export type DomainGroupId =
  | "rd" // 研发与测试
  | "ops" // 运维与数据
  | "biz"; // 业务与内容

/** 筛选 pill 的取值（含「全部」） */
export type DomainFilterId = "all" | DomainGroupId | "test" | "data" | "content";

/** 单个领域卡片的数据结构 */
export type DomainItem = {
  id: string; // 唯一 id，用作 React key
  name: string; // 卡片标题，如「对话平台」
  group: DomainGroupId; // 所属侧栏分组
  subtitle: string; // 标题下灰色副标
  description: string; // 两行简介
  tags: string[]; // 底部小标签
  status: "ready" | "soon"; // ready=可进；soon=占位
  workspace?: "chat" | "qa" | "ops"; // ready 时跳转的工作区；soon 可省略
  filters: DomainFilterId[]; // 出现在哪些筛选 pill 下（不含 all）
  badge?: number; // 侧栏可选数字徽章；没有就不显示
};

/** 侧栏分组标题 */
export const DOMAIN_GROUPS: { id: DomainGroupId; label: string }[] = [
  { id: "rd", label: "研发与测试" }, // 对话 / 测试 / 评审
  { id: "ops", label: "运维与数据" }, // 运维 / 数据 / 安全
  { id: "biz", label: "业务与内容" }, // 知识库 / 内容 / 营销
];

/** 主区筛选 pills（顺序即展示顺序） */
export const DOMAIN_FILTERS: { id: DomainFilterId; label: string }[] = [
  { id: "all", label: "全部" }, // 不过滤
  { id: "rd", label: "研发" }, // group=rd
  { id: "test", label: "测试" }, // filters 含 test
  { id: "ops", label: "运维" }, // group=ops 里偏运维
  { id: "data", label: "数据" }, // filters 含 data
  { id: "content", label: "内容" }, // filters 含 content
];

/** 全量领域列表：已上线 2 个，其余 soon 占位，方便以后接入 */
export const DOMAINS: DomainItem[] = [
  {
    id: "chat", // 对话平台
    name: "对话平台", // 卡片标题
    group: "rd", // 研发与测试
    subtitle: "多模型 · 问答 · 联网", // 副标
    description: "统一接入大模型与知识库，支持 chat / rag / agent 等模式。", // 简介
    tags: ["对话", "RAG", "Agent"], // 标签
    status: "ready", // 已对接 App chat
    workspace: "chat", // 进入对话三栏
    filters: ["rd"], // 研发筛选项下可见
    badge: 1, // 侧栏徽章（可按需改）
  },
  {
    id: "qa", // 自动测试
    name: "自动测试平台", // 标题
    group: "rd", // 同组
    subtitle: "用例 · 执行 · 报告", // 副标
    description: "生成与管理测试用例，覆盖 API / UI / 回归，查看运行与报告。", // 简介
    tags: ["API", "E2E", "回归"], // 标签
    status: "ready", // 已对接 QaWorkspace
    workspace: "qa", // 进入测试工作台
    filters: ["rd", "test"], // 研发 + 测试筛选
    badge: 1, // 徽章
  },
  {
    id: "code-review", // 代码评审（占位）
    name: "代码评审", // 标题
    group: "rd", // 分组
    subtitle: "Diff · 规范 · 建议", // 副标
    description: "围绕合并请求做自动审查与规范检查（即将开放）。", // 简介
    tags: ["Diff", "规范"], // 标签
    status: "soon", // 暂不可进
    filters: ["rd"], // 筛选
  },
  {
    id: "ops", // 运维排障
    name: "运维排障", // 标题
    group: "ops", // 运维与数据
    subtitle: "告警 · 根因 · Holmes", // 副标
    description: "接入 HolmesGPT：自然语言调查集群与可观测数据。", // 简介
    tags: ["Holmes", "告警", "根因"], // 标签
    status: "ready", // 已对接 OpsWorkspace
    workspace: "ops", // 进入运维工作台
    filters: ["ops"], // 运维筛选
    badge: 1,
  },
  {
    id: "data", // 数据分析（占位）
    name: "数据分析", // 标题
    group: "ops", // 同组
    subtitle: "NL2SQL · 报表 · 归因", // 副标
    description: "自然语言查数、报表与归因分析（即将开放）。", // 简介
    tags: ["NL2SQL", "报表"], // 标签
    status: "soon", // 占位
    filters: ["ops", "data"], // 运维 + 数据
  },
  {
    id: "security", // 安全合规（占位）
    name: "安全合规", // 标题
    group: "ops", // 同组
    subtitle: "策略 · 审计 · 合规", // 副标
    description: "安全策略检查与合规审计辅助（即将开放）。", // 简介
    tags: ["审计", "合规"], // 标签
    status: "soon", // 占位
    filters: ["ops"], // 运维筛选
  },
  {
    id: "kb", // 企业知识库独立台（占位；聊天侧栏知识库仍可用）
    name: "企业知识库", // 标题
    group: "biz", // 业务与内容
    subtitle: "向量 · 图谱 · 问答", // 副标
    description: "文档向量化与知识图谱问答的独立工作台（即将开放）。", // 简介
    tags: ["向量", "图谱"], // 标签
    status: "soon", // 占位
    filters: ["content"], // 内容筛选
  },
  {
    id: "content", // 内容创作（占位）
    name: "内容创作", // 标题
    group: "biz", // 同组
    subtitle: "文案 · 翻译 · 素材", // 副标
    description: "品牌一致的文案与素材生成（即将开放）。", // 简介
    tags: ["文案", "翻译"], // 标签
    status: "soon", // 占位
    filters: ["content"], // 内容筛选
  },
  {
    id: "growth", // 营销增长（占位）
    name: "营销增长", // 标题
    group: "biz", // 同组
    subtitle: "投放 · 增长 · 洞察", // 副标
    description: "增长实验与投放分析助手（即将开放）。", // 简介
    tags: ["增长", "洞察"], // 标签
    status: "soon", // 占位
    filters: ["content"], // 内容筛选
  },
];

/**
 * 按筛选 id 过滤领域列表
 * @param filter 当前选中的 pill
 */
export function filterDomains(filter: DomainFilterId): DomainItem[] {
  if (filter === "all") return DOMAINS; // 全部不过滤
  if (filter === "rd" || filter === "ops" || filter === "biz") {
    return DOMAINS.filter((d) => d.group === filter); // 按侧栏分组
  }
  return DOMAINS.filter((d) => d.filters.includes(filter)); // 按 tags 侧筛选
}