/**
 * mockStore.ts
 * ---------------------------------------------------------------------------
 * 前端壳数据层：读写 localStorage，模拟后端 CRUD。
 * 以后接真 API 时，只改本文件内部实现，组件尽量不用动。
 * ---------------------------------------------------------------------------
 */
import type { QaCase, QaMember, QaMemberRole, QaProject, QaRun } from "../types/qa";
import {
  createSeedCases,
  createSeedProject,
  qaId,
} from "./mockData";

/** 当前壳所属租户；useQaShell 启动时设置 */
let currentTenant = "default";

/** 切换租户后，后续读写都进 nexora.qa.{tenantId} */
export function setQaTenant(tenantId: string): void {
  currentTenant = (tenantId || "default").trim() || "default";
}

export function getQaTenant(): string {
  return currentTenant;
}

function lsKey(): string {
  return `nexora.qa.${currentTenant}`;
}

/** 持久化整体形状 */
interface QaPersist {
  projects: QaProject[];
  casesByProject: Record<string, QaCase[]>; // projectId -> cases
  runsByProject: Record<string, QaRun[]>;
  members: QaMember[];
}

/** 旧数据没有 members 时补一条管理员，避免页面崩 */
function withMembers(data: QaPersist): QaPersist {
  if (!Array.isArray(data.members) || data.members.length === 0) {
    data.members = [{ id: "me", name: currentTenant, role: "admin" }];
  }
  return data;
}

/** 读盘；没有则种一棵演示数据 */
export function loadQaPersist(): QaPersist {
  try {
    const raw = localStorage.getItem(lsKey());
    if (raw) {
      return withMembers(JSON.parse(raw) as QaPersist);
    }
  } catch {
    // 坏数据时重建
  }
  const seed = createSeedProject();
  const persist: QaPersist = {
    projects: [seed],
    casesByProject: { [seed.id]: createSeedCases(seed.id) },
    runsByProject: { [seed.id]: [] },
    members: [{ id: "me", name: currentTenant, role: "admin" }],
  };
  saveQaPersist(persist);
  return persist;
}

export function saveQaPersist(data: QaPersist): void {
  localStorage.setItem(lsKey(), JSON.stringify(data));
}

/** 新建空项目（带空来源，方便你在设置里填） */
export function storeCreateProject(input: {
  name: string;
  baseUrl: string;
  goal: string;
}): QaProject {
  const data = loadQaPersist();
  const project: QaProject = {
    id: qaId("proj"),
    name: input.name.trim() || "未命名项目",
    baseUrl: input.baseUrl.trim(),
    goal: input.goal.trim(),
    createdAt: new Date().toISOString(),
    sourceDocs: [],
  };
  data.projects.unshift(project);
  data.casesByProject[project.id] = [];
  data.runsByProject[project.id] = [];
  saveQaPersist(data);
  return project;
}

export function storeUpdateProject(
  projectId: string,
  patch: Partial<Pick<QaProject, "name" | "baseUrl" | "goal" | "sourceDocs">>,
): QaProject {
  const data = loadQaPersist();
  const idx = data.projects.findIndex((p) => p.id === projectId);
  if (idx < 0) throw new Error("项目不存在");
  data.projects[idx] = { ...data.projects[idx], ...patch };
  saveQaPersist(data);
  return data.projects[idx];
}

/**
 * 按目标「生成」一棵模板树（壳：规则生成，不调 LLM）。
 * 会追加到现有用例后面。
 */
export function storeGenerateCases(projectId: string, goal?: string): QaCase[] {
  const data = loadQaPersist();
  const project = data.projects.find((p) => p.id === projectId);
  if (!project) throw new Error("项目不存在");
  const text = (goal || project.goal || project.name).trim();
  const rootId = qaId("case");
  const root: QaCase = {
    id: rootId,
    projectId,
    parentId: null,
    code: "1",
    title: text.slice(0, 24) || "需求包",
    kind: "functional",
    requirement: text,
    fused: `围绕「${text}」覆盖打开站点、接口探活、基础功能与非功能占位项。`,
    steps: ["确认来源", "确认融合描述", "生成子用例"],
    expected: "树完整且每条有期望",
    status: "confirmed",
    sourceDocIds: project.sourceDocs.map((d) => d.id),
  };
  const kids: QaCase[] = [
    ["1.1", "探索性冒烟", "blackbox"],
    ["1.2", "核心功能", "functional"],
    ["1.3", "接口探活", "api"],
    ["1.4", "性能占位", "performance"],
    ["1.5", "安全占位", "security"],
  ].map(([code, title, kind], i) => ({
    id: qaId("case"),
    projectId,
    parentId: rootId,
    code,
    title,
    kind: kind as QaCase["kind"],
    requirement: `${title}：${text}`,
    fused: `${title}的可执行描述（壳阶段模板 #${i + 1}）`,
    steps: ["准备环境", "执行检查", "记录结果"],
    expected: "无阻断错误或占位项已确认",
    status: "draft" as const,
    sourceDocIds: project.sourceDocs.slice(0, 1).map((d) => d.id),
  }));
  const next = [...(data.casesByProject[projectId] || []), root, ...kids];
  data.casesByProject[projectId] = next;
  saveQaPersist(data);
  return next;
}

export function storePatchCase(
  projectId: string,
  caseId: string,
  patch: Partial<QaCase>,
): QaCase {
  const data = loadQaPersist();
  const list = data.casesByProject[projectId] || [];
  const idx = list.findIndex((c) => c.id === caseId);
  if (idx < 0) throw new Error("用例不存在");
  list[idx] = { ...list[idx], ...patch, id: caseId, projectId };
  data.casesByProject[projectId] = list;
  saveQaPersist(data);
  return list[idx];
}

/** 壳阶段冒烟：不真发 HTTP，只根据是否填写 baseUrl 给假结果 */
export function storeRunSmoke(projectId: string): QaRun {
  const data = loadQaPersist();
  const project = data.projects.find((p) => p.id === projectId);
  if (!project) throw new Error("项目不存在");
  const ok = Boolean(project.baseUrl.trim());
  const run: QaRun = {
    id: qaId("run"),
    projectId,
    caseIds: (data.casesByProject[projectId] || []).map((c) => c.id),
    verdict: ok ? "pass" : "fail",
    summary: ok
      ? `模拟 GET ${project.baseUrl} -> 200（前端壳，未请求真实网络）`
      : "未配置 Base URL，冒烟失败（请在项目设置中填写）",
    artifacts: { mocked: true, baseUrl: project.baseUrl },
    createdAt: new Date().toISOString(),
  };
  const runs = data.runsByProject[projectId] || [];
  data.runsByProject[projectId] = [run, ...runs].slice(0, 50);
  saveQaPersist(data);
  return run;
}

/** 本地假「上传」一条来源（读文件名 + 文本前几行） */
export async function storeAddLocalSource(
  projectId: string,
  file: File,
): Promise<QaProject> {
  const text = await file.text().catch(() => "");
  const excerpt = text.replace(/\s+/g, " ").trim().slice(0, 180) || "（二进制或空文件，壳阶段无正文）";
  const doc = {
    id: qaId("src"),
    name: file.name,
    kind: (file.name.endsWith(".md")
      ? "md"
      : file.name.endsWith(".pdf")
        ? "pdf"
        : "docx") as "md" | "pdf" | "docx",
    excerpt,
    rows: [
      {
        no: "1",
        name: file.name,
        reqId: "LOCAL-1",
        description: excerpt.slice(0, 80),
      },
    ],
  };
  const data = loadQaPersist();
  const idx = data.projects.findIndex((p) => p.id === projectId);
  if (idx < 0) throw new Error("项目不存在");
  const docs = [...data.projects[idx].sourceDocs, doc];
  data.projects[idx] = { ...data.projects[idx], sourceDocs: docs };
  saveQaPersist(data);
  return data.projects[idx];
}

/** 删除整个项目及其用例、运行记录 */
export function storeDeleteProject(projectId: string): QaProject[] {
  const data = loadQaPersist();
  if (!data.projects.some((p) => p.id === projectId)) {
    throw new Error("项目不存在");
  }
  data.projects = data.projects.filter((p) => p.id !== projectId);
  delete data.casesByProject[projectId];
  delete data.runsByProject[projectId];
  saveQaPersist(data);
  return data.projects;
}

/** 删除一条用例：若是父节点则连同子节点一起删除 */
export function storeDeleteCase(projectId: string, caseId: string): QaCase[] {
    const data = loadQaPersist();
    const list = data.casesByProject[projectId] || [];
    if (!list.some((c)=>c.id === caseId)) throw new Error("用例不存在");
    //收集caseId及其所有子节点
    const remove = new Set<string>([caseId]);
    let grew = true;
    while (grew) {
        grew = false;
        for (const c of list) {
            if (c.parentId && remove.has(c.parentId) && !remove.has(c.id)) {
                remove.add(c.id);
                grew = true;
            }
        }
    }
    const next = list.filter(c => !remove.has(c.id));
    data.casesByProject[projectId] = next;
    saveQaPersist(data);
    return next;
}

export function storeListMembers(): QaMember[] {
  return loadQaPersist().members || [];
}

/** 只改本租户名单 */
export function storeUpsertMember(name: string, role: QaMemberRole): QaMember[] {
  const data = loadQaPersist();
  const members = data.members || [];
  members.push({ id: qaId("mem"), name: name.trim() || "未命名", role });
  data.members = members;
  saveQaPersist(data);
  return members;
}

export function storeSetMemberRole(id: string, role: QaMemberRole): QaMember[] {
  const data = loadQaPersist();
  data.members = (data.members || []).map((m) =>
    m.id === id ? { ...m, role } : m,
  );
  saveQaPersist(data);
  return data.members;
}

/**
 * 右侧对话改草稿：按关键词改当前用例，不调用模型。
 * 返回给助手气泡的一句说明。
 */
export function storeApplyChatCommand(
  projectId: string,
  selectedId: string | null,
  text: string,
): { cases: QaCase[]; selectedId: string | null; reply: string } {
  const raw = text.trim();
  let cases = loadQaPersist().casesByProject[projectId] || [];
  let nextSelected = selectedId;

  if (/删(掉|除).*安全/.test(raw)) {
    const secs = cases.filter((c) => c.kind === "security");
    for (const s of secs) {
      cases = storeDeleteCase(projectId, s.id);
    }
    if (nextSelected && !cases.some((c) => c.id === nextSelected)) {
      nextSelected = cases[0]?.id ?? null;
    }
    return {
      cases,
      selectedId: nextSelected,
      reply: secs.length
        ? `已删除 ${secs.length} 条安全相关用例。`
        : "当前项目没有安全类用例。",
    };
  }

  if (/性能|p95/i.test(raw)) {
    const target =
      cases.find((c) => c.kind === "performance") ||
      cases.find((c) => c.id === selectedId);
    if (!target) {
      return { cases, selectedId, reply: "没有可改的用例，请先生成测试项。" };
    }
    const patched = storePatchCase(projectId, target.id, {
      fused: raw,
      steps: ["按目标发起压测", "记录 p95 与错误率"],
      expected: "p95 < 300ms，错误率低于约定阈值",
      status: "draft",
    });
    cases = (loadQaPersist().casesByProject[projectId] || []).map((c) =>
      c.id === patched.id ? patched : c,
    );
    return {
      cases,
      selectedId: patched.id,
      reply: `已改 ${patched.code} ${patched.title} 的融合稿与期望。`,
    };
  }

  const current = cases.find((c) => c.id === selectedId);
  if (!current) {
    return { cases, selectedId, reply: "请先在中间点一条用例，我再改这一条。" };
  }
  const patched = storePatchCase(projectId, current.id, {
    fused: raw,
    status: "draft",
  });
  cases = cases.map((c) => (c.id === patched.id ? patched : c));
  return {
    cases,
    selectedId: patched.id,
    reply: `已把这句话写入 ${patched.code} ${patched.title}。确认后才会当作正式稿。`,
  };
}