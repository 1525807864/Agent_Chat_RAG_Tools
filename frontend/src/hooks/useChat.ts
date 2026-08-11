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

export function useChat(llmSettings?: LlmSettings) {
  const [sessionId, setSessionId] = useState(() => `web-${uid()}`);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [mode, setMode] = useState<Mode>("chat");
  const [multiMode, setMultiMode] = useState<MultiMode>("sequential");
  const [agentName, setAgentName] = useState("assistant");
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
      };

      try {
        if (!useStream) {
          const res = await postChat(body);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: res.answer } : m,
            ),
          );
        } else {
          const ac = new AbortController();
          abortRef.current = ac;
          let acc = "";
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
                const finalText = answer || acc;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, content: finalText } : m,
                  ),
                );
              },
              onError: (detail) => setError(detail),
            },
            ac.signal,
          );
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
    [agentName, loading, llmSettings, mode, multiMode, sessionId, useStream],
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
