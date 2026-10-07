/**
 * useChat：对话核心状态；send 可附带 workspace_root + files。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchTenantUsage,
  getSessionMemory,
  postChat,
  postChatStream,
} from "../api/endpoints";
import type {
  LlmSettings,
  Mode,
  MultiMode,
  TaskCheckEvent,
  TaskPlan,
  TenantUsageDTO,
  TurnUsage,
  UiMessage,
} from "../types/api";
import type { WorkspacePayload } from "../types/workspace";

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function llmFields(llm?: LlmSettings): Partial<LlmSettings> {
  if (!llm) return {};
  const out: Partial<LlmSettings> = {};
  const key = llm.api_key.trim();
  const base = llm.api_base.trim();
  const model = llm.model_name.trim();
  if (key) out.api_key = key;
  if (base) out.api_base = base;
  if (model) out.model_name = model;
  return out;
}

function emptyAnswerFallback() {
  return "（空响应）模型未返回内容，请重试或检查 API Key / 模型设置";
}

export function useChat(llmSettings?: LlmSettings) {
  const [sessionId, setSessionId] = useState(() => `web-${uid()}`);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [mode, setMode] = useState<Mode>("chat");
  const [multiMode, setMultiMode] = useState<MultiMode>("sequential");
  const [agentName, setAgentName] = useState("assistant");
  const [e2eBaseUrl, setE2eBaseUrl] = useState("");
  const [qaTenantId, setQaTenantId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useStream, setUseStream] = useState(true);
  const [tenantUsage, setTenantUsage] = useState<TenantUsageDTO | null>(null);
  // 意图台账（Intent Guard）：意图卡片 + 任务清单 + 进度
  const [taskPlan, setTaskPlan] = useState<TaskPlan | null>(null);
  // 最近一次对齐检查结果（drift 拦截展示用）
  const [lastCheck, setLastCheck] = useState<TaskCheckEvent | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  /** 从后端 memory 端点装载意图台账（切会话/加载历史时用） */
  const loadTaskPlan = useCallback(async (id: string) => {
    try {
      const mem = await getSessionMemory(id);
      setTaskPlan(mem.task_plan?.goal ? (mem.task_plan as TaskPlan) : null);
      setLastCheck(null);
    } catch {
      // 会话无台账或后端未启用时忽略
      setTaskPlan(null);
      setLastCheck(null);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchTenantUsage();
        if (cancelled) return;
        const u = res.usage;
        if (u && typeof u.tokens_in === "number") {
          setTenantUsage({
            requests: Number(u.requests) || 0,
            tokens_in: Number(u.tokens_in) || 0,
            tokens_out: Number(u.tokens_out) || 0,
          });
        }
      } catch {
        // 未登录或账本不可用时忽略
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
  }, []);

  /**
   * @param text 用户自然语言（不要塞巨型文件）
   * @param workspace 桌面工作区上下文；无则不传
   */
  const send = useCallback(
    async (text: string, workspace?: WorkspacePayload | null) => {
      const content = text.trim();
      if (!content || loading) return;

      setError(null);
      setLoading(true);
      // 新一轮开始：清掉上一轮的检查结果
      setLastCheck(null);

      // 气泡里只显示用户原话 + 打开文件名提示（不刷全文）
      const fileHint =
        workspace?.files?.length ?
          `\n\n[已附带 ${workspace.files.length} 个工作区文件: ${workspace.files
            .map((f) => f.path)
            .join(", ")}]`
        : "";
      const userMsg: UiMessage = {
        id: uid(),
        role: "user",
        content: content + fileHint,
      };
      const assistantId = uid();
      setMessages((prev) => [
        ...prev,
        userMsg,
        { id: assistantId, role: "assistant", content: "" },
      ]);

      const body = {
        message: content,
        session_id: sessionId,
        mode,
        multi_mode: multiMode,
        agent_name: agentName,
        ...llmFields(llmSettings),
        workspace_root: workspace?.workspace_root,
        files: workspace?.files?.map((f) => ({
          path: f.path,
          content: f.content,
        })),
        e2e_base_url: e2eBaseUrl.trim() || undefined,
        qa_tenant_id: qaTenantId.trim() || undefined,
      };

      try {
        if (!useStream) {
          const res = await postChat(body);
          const text =
            typeof res.answer === "string" && res.answer.trim()
              ? res.answer
              : emptyAnswerFallback();
          const usage = (res.meta?.usage as TurnUsage | undefined) || undefined;
          const tu = res.meta?.tenant_usage as TenantUsageDTO | undefined;
          if (tu) setTenantUsage(tu);
          const tp = res.meta?.task_plan as TaskPlan | undefined;
          if (tp && tp.goal) setTaskPlan(tp);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: text, usage } : m,
            ),
          );
        } else {
          const ac = new AbortController();
          abortRef.current = ac;
          let acc = "";
          let sawDone = false;
          let sawError = false;
          await postChatStream(
            body,
            {
              onDelta: (delta) => {
                acc += delta;
                const snapshot = acc;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, content: snapshot } : m,
                  ),
                );
              },
              onDone: (answer, meta) => {
                sawDone = true;
                const merged = (answer || acc).trim() ? answer || acc : "";
                const finalText = merged || emptyAnswerFallback();
                if (meta?.tenant_usage) setTenantUsage(meta.tenant_usage);
                if (meta?.task_plan?.goal) setTaskPlan(meta.task_plan);
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: finalText, usage: meta?.usage }
                      : m,
                  ),
                );
              },
              onTask: (payload) => {
                // 意图追踪帧：anchor / check / plan_update / finalize
                const d = payload.data || {};
                if (payload.type === "check") {
                  setLastCheck(d as unknown as TaskCheckEvent);
                } else if (
                  payload.type === "plan_update" ||
                  payload.type === "finalize"
                ) {
                  const plan = d.plan as TaskPlan | undefined;
                  if (plan && plan.goal) {
                    setTaskPlan(plan);
                  } else if (Array.isArray(d.tasks)) {
                    setTaskPlan((prev) =>
                      prev
                        ? { ...prev, tasks: d.tasks as TaskPlan["tasks"] }
                        : prev,
                    );
                  }
                } else if (payload.type === "anchor") {
                  // 锚点帧只带 goal 摘要，不覆盖已装载的完整台账
                  const goal = typeof d.goal === "string" ? d.goal : "";
                  if (goal) {
                    setTaskPlan((prev) =>
                      prev ? { ...prev, goal } : null,
                    );
                  }
                }
              },
              onError: (detail) => {
                sawError = true;
                setError(detail);
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: m.content || `（请求失败）${detail}` }
                      : m,
                  ),
                );
              },
            },
            ac.signal,
          );
          if (!sawDone && !sawError) {
            const finalText = acc.trim() ? acc : emptyAnswerFallback();
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: m.content || finalText }
                  : m,
              ),
            );
          }
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: m.content || `（请求失败）${msg}` }
              : m,
          ),
        );
      } finally {
        setLoading(false);
        abortRef.current = null;
      }
    },
    [agentName, e2eBaseUrl, loading, llmSettings, mode, multiMode, qaTenantId, sessionId, useStream],
  );

  const switchSession = useCallback((id: string) => {
    setSessionId(id);
    setMessages([]);
    setError(null);
    setTaskPlan(null);
    setLastCheck(null);
  }, []);

  const newSession = useCallback(() => {
    switchSession(`web-${uid()}`);
  }, [switchSession]);

  return {
    sessionId,
    messages,
    setMessages,
    mode,
    setMode,
    multiMode,
    setMultiMode,
    agentName,
    setAgentName,
    e2eBaseUrl,
    setE2eBaseUrl,
    qaTenantId,
    setQaTenantId,
    loading,
    error,
    useStream,
    setUseStream,
    tenantUsage,
    taskPlan,
    lastCheck,
    send,
    stop,
    switchSession,
    newSession,
    loadTaskPlan,
  };
}
