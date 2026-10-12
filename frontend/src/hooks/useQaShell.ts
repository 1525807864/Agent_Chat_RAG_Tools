/**
 * useQaShell.ts —— 测试工作台状态与动作（全部走真后端 /api/qa）
 * 组件只消费本 hook；不再写 localStorage mock。
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { readTenantId } from "../auth/token";
import type {
  QaCase,
  QaChatTurn,
  QaMember,
  QaMemberRole,
  QaNav,
  QaProject,
  QaRun,
  QaUiStep,
  QaView,
} from "../types/qa";
import {
  addQaMember,
  confirmQaCase,
  createQaProject,
  deleteQaCase,
  deleteQaMember,
  deleteQaProject,
  fetchQaCases,
  fetchQaMembers,
  fetchQaProjects,
  fetchQaRuns,
  generateQaCases,
  patchQaMember,
  patchQaProject,
  postQaAssistant,
  runQaSmoke,
  downloadQaRunExport,
  streamQaUiRun,
  uploadQaSource,
} from "../api/endpoints";

/** API camelCase → 前端 QaProject（补默认 sourceDocs / rows） */
function mapProject(p: {
  id: string;
  name: string;
  baseUrl: string;
  goal: string;
  createdAt: string;
  sourceDocs?: Array<{
    id: string;
    name: string;
    kind: string;
    excerpt: string;
    rows?: QaProject["sourceDocs"][number]["rows"];
  }>;
}): QaProject {
  return {
    id: p.id,
    name: p.name,
    baseUrl: p.baseUrl || "",
    goal: p.goal || "",
    createdAt: p.createdAt || "",
    sourceDocs: (p.sourceDocs || []).map((d) => ({
      id: d.id,
      name: d.name,
      kind: d.kind as QaProject["sourceDocs"][number]["kind"],
      excerpt: d.excerpt || "",
      rows: d.rows || [],
    })),
  };
}

function mapCase(c: {
  id: string;
  projectId: string;
  parentId: string | null;
  code?: string;
  title: string;
  kind: string;
  requirement: string;
  fused: string;
  steps: string[];
  expected: string;
  status: string;
  sourceDocIds?: string[];
}): QaCase {
  return {
    id: c.id,
    projectId: c.projectId,
    parentId: c.parentId,
    code: c.code || "",
    title: c.title,
    kind: c.kind as QaCase["kind"],
    requirement: c.requirement,
    fused: c.fused,
    steps: c.steps || [],
    expected: c.expected || "",
    status: c.status as QaCase["status"],
    sourceDocIds: c.sourceDocIds || [],
  };
}

function mapRun(r: {
  id: string;
  projectId: string;
  caseIds: string[];
  verdict: string;
  summary: string;
  artifacts?: Record<string, unknown>;
  createdAt: string;
}): QaRun {
  const verdict =
    r.verdict === "pass" || r.verdict === "fail" || r.verdict === "error"
      ? r.verdict
      : "error";
  return {
    id: r.id,
    projectId: r.projectId,
    caseIds: r.caseIds || [],
    verdict,
    summary: r.summary,
    artifacts: r.artifacts,
    createdAt: r.createdAt,
  };
}

export function useQaShell() {
  const tenantId = readTenantId() || "default";

  const [view, setView] = useState<QaView>("list");
  const [nav, setNav] = useState<QaNav>("projects");
  const [chat, setChat] = useState<QaChatTurn[]>([]);
  const [materialsOpen, setMaterialsOpen] = useState(true);
  const [members, setMembers] = useState<QaMember[]>([]);
  const [projects, setProjects] = useState<QaProject[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [cases, setCases] = useState<QaCase[]>([]);
  const [runs, setRuns] = useState<QaRun[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [treeQuery, setTreeQuery] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [uiSteps, setUiSteps] = useState<QaUiStep[]>([]);
  const [uiRunning, setUiRunning] = useState(false);

  const activeProject = useMemo(
    () => projects.find((p) => p.id === activeProjectId) || null,
    [projects, activeProjectId],
  );
  const selectedCase = useMemo(
    () => cases.find((c) => c.id === selectedCaseId) || null,
    [cases, selectedCaseId],
  );

  /** 启动拉项目 + 成员 */
  const refreshProjects = useCallback(async () => {
    const res = await fetchQaProjects();
    setProjects((res.items || []).map(mapProject));
  }, []);

  const refreshMembers = useCallback(async () => {
    const res = await fetchQaMembers();
    setMembers(
      (res.items || []).map((m) => ({
        id: m.id,
        name: m.name,
        role: m.role as QaMemberRole,
      })),
    );
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        await Promise.all([refreshProjects(), refreshMembers()]);
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [refreshProjects, refreshMembers]);

  const openProject = useCallback(async (projectId: string) => {
    setBusy(true);
    setNotice("");
    try {
      const [cRes, rRes] = await Promise.all([
        fetchQaCases(projectId),
        fetchQaRuns(projectId),
      ]);
      const list = (cRes.items || []).map(mapCase);
      const runList = (rRes.items || []).map(mapRun);
      setActiveProjectId(projectId);
      setCases(list);
      setRuns(runList);
      setSelectedCaseId(list[0]?.id ?? null);
      setTreeQuery("");
      setView("workbench");
      setNav("cases");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const backToList = useCallback(() => {
    setView("list");
    setActiveProjectId(null);
    setCases([]);
    setRuns([]);
    setSelectedCaseId(null);
    setSettingsOpen(false);
    setNav("projects");
    setUiSteps([]);
  }, []);

  /** 未进项目时点侧栏：强制回项目空间并提示（商业产品常见 guard） */
  const setNavGuarded = useCallback(
    (next: QaNav) => {
      if (next === "projects") {
        backToList();
        return;
      }
      if (!activeProjectId) {
        setNotice("请先进入一个项目，再使用该功能");
        setNav("projects");
        return;
      }
      setNav(next);
    },
    [activeProjectId, backToList],
  );

  const createProject = useCallback(
    async (name: string, baseUrl: string, goal: string) => {
      setBusy(true);
      try {
        const p = mapProject(
          await createQaProject({
            name,
            base_url: baseUrl,
            goal,
          }),
        );
        await refreshProjects();
        await openProject(p.id);
        setNotice("已创建项目");
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [openProject, refreshProjects],
  );

  const saveProject = useCallback(
    async (patch: Partial<Pick<QaProject, "name" | "baseUrl" | "goal">>) => {
      if (!activeProjectId) return;
      setBusy(true);
      try {
        await patchQaProject(activeProjectId, {
          name: patch.name,
          base_url: patch.baseUrl,
          goal: patch.goal,
        });
        await refreshProjects();
        setNotice("项目设置已保存");
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [activeProjectId, refreshProjects],
  );

  const generateCases = useCallback(async () => {
    if (!activeProjectId) return;
    setBusy(true);
    try {
      const res = await generateQaCases(
        activeProjectId,
        activeProject?.goal,
      );
      const list = (res.items || []).map(mapCase);
      setCases(list);
      setSelectedCaseId(list[0]?.id ?? null);
      setNotice("已生成测试项");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [activeProjectId, activeProject?.goal]);

  const confirmCase = useCallback(
    async (fused: string) => {
      if (!activeProjectId || !selectedCaseId) return;
      setBusy(true);
      try {
        const c = mapCase(
          await confirmQaCase(activeProjectId, selectedCaseId, fused),
        );
        setCases((prev) => prev.map((x) => (x.id === c.id ? c : x)));
        setNotice("已确认当前条目");
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [activeProjectId, selectedCaseId],
  );

  const runSmoke = useCallback(async () => {
    if (!activeProjectId) return;
    setBusy(true);
    try {
      const run = mapRun(await runQaSmoke(activeProjectId));
      setRuns((prev) => [run, ...prev]);
      setNotice(run.summary);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [activeProjectId]);

  const runUi = useCallback(
    async (name: string, baseUrl: string, goal = "") => {
      if (!activeProjectId) return;
      setUiSteps([]);
      setUiRunning(true);
      setBusy(true);
      setNav("runs");
      try {
        await streamQaUiRun(
          activeProjectId,
          {
            name: name.trim() || "UI 测试",
            base_url: baseUrl.trim(),
            goal: goal.trim(),
          },
          {
            onStep: (s) =>
              setUiSteps((prev) => [
                ...prev,
                {
                  i: s.i,
                  action: s.action,
                  detail: s.detail,
                  ok: s.ok,
                  error: s.error,
                },
              ]),
            onDone: (d) => {
              if (d.run) setRuns((prev) => [mapRun(d.run!), ...prev]);
              setNotice(d.summary || "UI 测试结束");
            },
            onError: (msg) => setNotice(msg),
          },
        );
      } finally {
        setUiRunning(false);
        setBusy(false);
      }
    },
    [activeProjectId],
  );

  const exportRun = useCallback(
    async (runId: string, fmt: "xlsx" | "docx" | "pdf") => {
      if (!activeProjectId) return;
      try {
        await downloadQaRunExport(activeProjectId, runId, fmt);
        setNotice(`已导出 ${fmt.toUpperCase()}`);
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      }
    },
    [activeProjectId],
  );

  const sendAssistant = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || !activeProjectId) return;
      setChat((prev) => [
        ...prev,
        { id: `u-${Date.now()}`, role: "user", text: content },
      ]);
      setBusy(true);
      try {
        const res = await postQaAssistant(activeProjectId, {
          text: content,
          case_id: selectedCaseId,
        });
        setCases((res.cases || []).map(mapCase));
        if (res.selectedId) setSelectedCaseId(res.selectedId);
        setChat((prev) => [
          ...prev,
          { id: `a-${Date.now()}`, role: "assistant", text: res.reply },
        ]);
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [activeProjectId, selectedCaseId],
  );

  const addMember = useCallback(
    async (name: string, role: QaMemberRole) => {
      try {
        const res = await addQaMember({ name, role });
        setMembers(
          (res.items || []).map((m) => ({
            id: m.id,
            name: m.name,
            role: m.role as QaMemberRole,
          })),
        );
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      }
    },
    [],
  );

  const setMemberRole = useCallback(async (id: string, role: QaMemberRole) => {
    try {
      const res = await patchQaMember(id, role);
      setMembers(
        (res.items || []).map((m) => ({
          id: m.id,
          name: m.name,
          role: m.role as QaMemberRole,
        })),
      );
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const deleteMember = useCallback(async (id: string) => {
    if (!window.confirm("确定移除该成员？")) return;
    try {
      const res = await deleteQaMember(id);
      setMembers(
        (res.items || []).map((m) => ({
          id: m.id,
          name: m.name,
          role: m.role as QaMemberRole,
        })),
      );
      setNotice("已移除成员");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const deleteCase = useCallback(
    async (caseId?: string) => {
      if (!activeProjectId) return;
      const id = caseId || selectedCaseId;
      if (!id) return;
      if (!window.confirm("确定删除该测试内容？")) return;
      setBusy(true);
      try {
        const res = await deleteQaCase(activeProjectId, id);
        const list = (res.items || []).map(mapCase);
        setCases(list);
        setSelectedCaseId((prev) =>
          prev && list.some((c) => c.id === prev) ? prev : list[0]?.id ?? null,
        );
        setNotice("已删除测试内容");
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [activeProjectId, selectedCaseId],
  );

  const deleteProject = useCallback(
    async (projectId: string) => {
      if (!window.confirm("确定删除项目？")) return;
      setBusy(true);
      try {
        await deleteQaProject(projectId);
        await refreshProjects();
        if (activeProjectId === projectId) backToList();
        setNotice("已删除项目");
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [activeProjectId, backToList, refreshProjects],
  );

  /** 项目资料上传：POST /api/qa/projects/:id/sources */
  const addLocalSource = useCallback(
    async (file: File) => {
      if (!activeProjectId) return;
      setBusy(true);
      try {
        const p = mapProject(await uploadQaSource(activeProjectId, file));
        setProjects((prev) => prev.map((x) => (x.id === p.id ? p : x)));
        setNotice(`已添加来源：${file.name}`);
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [activeProjectId],
  );

  const resetDemo = useCallback(() => {
    setNotice("已接真后端，无需本地重置；删除项目即可清空数据");
  }, []);

  return {
    view,
    projects,
    activeProject,
    cases,
    runs,
    selectedCase,
    selectedCaseId,
    setSelectedCaseId,
    treeQuery,
    setTreeQuery,
    settingsOpen,
    setSettingsOpen,
    busy,
    notice,
    setNotice,
    openProject,
    backToList,
    createProject,
    saveProject,
    generateCases,
    confirmCase,
    runSmoke,
    runUi,
    exportRun,
    uiSteps,
    uiRunning,
    addLocalSource,
    resetDemo,
    deleteCase,
    deleteProject,
    tenantId,
    nav,
    setNav: setNavGuarded, // 侧栏用这个，带项目守卫
    chat,
    materialsOpen,
    setMaterialsOpen,
    members,
    sendAssistant,
    addMember,
    setMemberRole,
    deleteMember,
    refreshMembers,
  };
}