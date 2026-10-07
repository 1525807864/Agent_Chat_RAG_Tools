/**
 * useQaShell.ts
 * 测试工作台全部 UI 状态与动作。组件只消费本 hook，不直接碰 localStorage。
 */
import { useCallback, useMemo, useState } from "react";
import { readTenantId } from "../auth/token";
import type {
  QaCase,
  QaChatTurn,
  QaMember,
  QaMemberRole,
  QaNav,
  QaProject,
  QaRun,
  QaView,
} from "../types/qa";
import {
  getQaTenant,
  loadQaPersist,
  setQaTenant,
  storeAddLocalSource,
  storeApplyChatCommand,
  storeCreateProject,
  storeDeleteCase,
  storeDeleteProject,
  storeGenerateCases,
  storePatchCase,
  storeRunSmoke,
  storeSetMemberRole,
  storeUpdateProject,
  storeUpsertMember,
} from "../qa/mockStore";

export function useQaShell() {
  const tenantId = readTenantId();
  setQaTenant(tenantId);
  const initial = loadQaPersist();
  const [view, setView] = useState<QaView>("list");
  const [nav, setNav] = useState<QaNav>("projects");
  const [chat, setChat] = useState<QaChatTurn[]>([]);
  const [materialsOpen, setMaterialsOpen] = useState(true);
  const [members, setMembers] = useState<QaMember[]>(initial.members || []);
  const [projects, setProjects] = useState<QaProject[]>(initial.projects);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [cases, setCases] = useState<QaCase[]>([]);
  const [runs, setRuns] = useState<QaRun[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [treeQuery, setTreeQuery] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  
  const activeProject = useMemo(
    () => projects.find((p) => p.id === activeProjectId) || null,
    [projects, activeProjectId],
  );

  const selectedCase = useMemo(
    () => cases.find((c) => c.id === selectedCaseId) || null,
    [cases, selectedCaseId],
  );

  const openProject = useCallback((projectId: string) => {
    const data = loadQaPersist();
    const list = data.casesByProject[projectId] || [];
    const runList = data.runsByProject[projectId] || [];
    setActiveProjectId(projectId);
    setCases(list);
    setRuns(runList);
    setSelectedCaseId(list[0]?.id ?? null);
    setTreeQuery("");
    setView("workbench");
    setNav("cases");
    setNotice("");
  }, []);

  const backToList = useCallback(() => {
    setView("list");
    setActiveProjectId(null);
    setCases([]);
    setRuns([]);
    setSelectedCaseId(null);
    setSettingsOpen(false);
    setNav("projects");
  }, []);

  const refreshProjects = useCallback(() => {
    setProjects(loadQaPersist().projects);
  }, []);

  const createProject = useCallback(
    async (name: string, baseUrl: string, goal: string) => {
      setBusy(true);
      try {
        const p = storeCreateProject({ name, baseUrl, goal });
        refreshProjects();
        openProject(p.id);
        setNotice("已新建项目（本地壳数据）");
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
        storeUpdateProject(activeProjectId, patch);
        refreshProjects();
        setNotice("项目设置已保存");
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
      const list = storeGenerateCases(activeProjectId, activeProject?.goal);
      setCases(list);
      setSelectedCaseId(list[list.length - 5]?.id ?? list[0]?.id ?? null);
      setNotice("已生成测试项（模板，未调用模型）");
    } finally {
      setBusy(false);
    }
  }, [activeProjectId, activeProject?.goal]);

  const confirmCase = useCallback(
    async (fused: string) => {
      if (!activeProjectId || !selectedCaseId) return;
      setBusy(true);
      try {
        const c = storePatchCase(activeProjectId, selectedCaseId, {
          fused,
          status: "confirmed",
        });
        setCases((prev) => prev.map((x) => (x.id === c.id ? c : x)));
        setNotice("已确认当前条目");
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
      const run = storeRunSmoke(activeProjectId);
      setRuns((prev) => [run, ...prev]);
      setNotice(run.summary);
    } finally {
      setBusy(false);
    }
  }, [activeProjectId]);

  const addLocalSource = useCallback(
    async (file: File) => {
      if (!activeProjectId) return;
      setBusy(true);
      try {
        const p = await storeAddLocalSource(activeProjectId, file);
        refreshProjects();
        setProjects((prev) => prev.map((x) => (x.id === p.id ? p : x)));
        setNotice(`已添加来源：${file.name}`);
      } finally {
        setBusy(false);
      }
    },
    [activeProjectId, refreshProjects],
  );

  const resetDemo = useCallback(() => {
    localStorage.removeItem(`nexora.qa.${getQaTenant()}`);
    const data = loadQaPersist();
    setProjects(data.projects);
    setMembers(data.members || []);
    setChat([]);
    backToList();
    setNotice("已重置为演示数据");
  }, [backToList]);

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
        const result = storeApplyChatCommand(
          activeProjectId,
          selectedCaseId,
          content,
        );
        setCases(result.cases);
        setSelectedCaseId(result.selectedId);
        setChat((prev) => [
          ...prev,
          { id: `a-${Date.now()}`, role: "assistant", text: result.reply },
        ]);
      } finally {
        setBusy(false);
      }
    },
    [activeProjectId, selectedCaseId],
  );

  const addMember = useCallback((name: string, role: QaMemberRole) => {
    setMembers(storeUpsertMember(name, role));
  }, []);

  const setMemberRole = useCallback((id: string, role: QaMemberRole) => {
    setMembers(storeSetMemberRole(id, role));
  }, []);
  

  const deleteCase = useCallback(
    async (caseId?: string) => {
      if (!activeProjectId) return;
      const id = caseId || selectedCaseId;
      if (!id) return;
      const target = cases.find((c) => c.id === id);
      const childCount = cases.filter((c) => c.parentId === id).length;
      const extra =
        childCount > 0 ? `（将同时删除 ${childCount} 条子项）` : "";
      const label = target ? `「${target.code} ${target.title}」` : "该测试内容";
      if (!window.confirm(`确定删除${label}${extra}？删除后无法恢复。`)) return;
      setBusy(true);
      try {
        const list = storeDeleteCase(activeProjectId, id);
        setCases(list);
        setSelectedCaseId((prev) => {
          if (prev && list.some((c) => c.id === prev)) return prev;
          return list[0]?.id ?? null;
        });
        setNotice("已删除测试内容");
      } finally {
        setBusy(false);
      }
    },
    [activeProjectId, selectedCaseId, cases],
  );

  const deleteProject = useCallback(
    async (projectId: string) => {
      const target = projects.find((p) => p.id === projectId);
      const label = target ? `「${target.name}」` : "该项目";
      if (!window.confirm(`确定删除项目${label}？其下测试内容也会一并删除。`)) {
        return;
      }
      setBusy(true);
      try {
        const next = storeDeleteProject(projectId);
        setProjects(next);
        if (activeProjectId === projectId) {
          backToList();
        }
        setNotice("已删除项目");
      } finally {
        setBusy(false);
      }
    },
    [projects, activeProjectId, backToList],
  );
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
    addLocalSource,
    resetDemo,
    deleteCase,
    deleteProject,
    tenantId: getQaTenant(),
    nav,
    setNav,
    chat,
    materialsOpen,
    setMaterialsOpen,
    members,
    sendAssistant,
    addMember,
    setMemberRole,
  };
}
