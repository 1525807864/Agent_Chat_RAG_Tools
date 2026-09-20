/**
 * useChat：对话核心状态；send 可附带 workspace_root + files。
 */
import { useCallback, useRef, useState } from "react";
import { postChat, postChatStream } from "../api/endpoints";
import type { LlmSettings, Mode, MultiMode, UiMessage } from "../types/api";
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
  const abortRef = useRef<AbortController | null>(null);

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
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: text } : m,
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
              onDone: (answer) => {
                sawDone = true;
                const merged = (answer || acc).trim() ? answer || acc : "";
                const finalText = merged || emptyAnswerFallback();
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, content: finalText } : m,
                  ),
                );
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
    send,
    stop,
    switchSession,
    newSession,
  };
}
