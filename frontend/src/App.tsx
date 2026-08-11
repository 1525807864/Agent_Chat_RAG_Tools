/**
 * App：整页外壳 = 顶栏 + 三栏布局（会话 / 聊天 / 设置）
 * ------------------------------------------------
 * 新增能力：顶栏消息气泡图标，点击显示/隐藏左侧会话历史。
 */
import { useCallback, useEffect, useState } from "react";
import { fetchHealth, getSessionHistory } from "./api/endpoints";
import { getApiBase } from "./api/client";
import { ChatInput } from "./components/ChatInput";
import { ChatMessages } from "./components/ChatMessages";
import { FileToolbar } from "./components/FileToolbar";
import { KnowledgePanel } from "./components/KnowledgePanel";
import { ModeBar } from "./components/ModeBar";
import { SessionList } from "./components/SessionList";
import { SettingsPanel } from "./components/SettingsPanel";
import {
  buildMessageWithAttachments,
  useAttachments,
} from "./hooks/useAttachments";
import { useChat } from "./hooks/useChat";
import { useLlmSettings } from "./hooks/useLlmSettings";
import { useWorkspace } from "./hooks/useWorkspace";
import type { FileTreeNode } from "./types/attachment";
import type { UiMessage } from "./types/api";

/**
 * ChatBubbleIcon：消息气泡 SVG 图标
 * --------------------------------
 * - 不依赖本地 png，缩放清晰
 * - stroke 用 currentColor，颜色跟随按钮文字色
 */
function ChatBubbleIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      {/* 圆角矩形 + 左下角小三角，常见「消息」外形 */}
      <path
        d="M4 6.5C4 5.12 5.12 4 6.5 4h11C18.88 4 20 5.12 20 6.5v7c0 1.38-1.12 2.5-2.5 2.5H10l-4 3.2V15.5C4.9 15.5 4 14.6 4 13.5v-7z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** 把后端历史消息转成界面用的 UiMessage 列表 */
function toUiMessages(raw: { role: string; content: string }[]): UiMessage[] {
  return raw.map((m, i) => ({
    id: `hist-${i}-${m.role}`,
    role:
      m.role === "user" || m.role === "assistant" || m.role === "system"
        ? m.role
        : "assistant",
    content: m.content,
  }));
}

export default function App() {
  const { settings, draft, setDraft, save, clear, savedHint } = useLlmSettings();

  const {
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
  } = useChat(settings);

  const {
    attachments,
    error: attachError,
    addFiles,
    addAttachment,
    remove,
    clear: clearAttachments,
  } = useAttachments();

  const {
    root,
    tree,
    openFiles,
    error: wsError,
    openWorkspace,
    listChildren,
    openFile,
    removeOpenFile,
    toPayload,
    hasDesktopFs,
  } = useWorkspace();

  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [healthLabel, setHealthLabel] = useState("检测 API…");

  /**
   * sidebarOpen：左侧「会话历史」是否显示
   * - true  → 显示 SessionList
   * - false → 隐藏 SessionList，中间聊天区变宽
   * 默认 true，和改之前行为一致
   */
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const h = await fetchHealth();
        if (cancelled) return;
        setHealthOk(true);
        setHealthLabel(
          `API OK · ${getApiBase()} · modes: ${h.modes.join(", ")}`,
        );
      } catch (e) {
        if (cancelled) return;
        setHealthOk(false);
        const msg = e instanceof Error ? e.message : String(e);
        setHealthLabel(`API 不可用 · ${getApiBase()} · ${msg}`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * toggleSidebar：点击顶栏消息图标
   * 用 prev => !prev，避免闭包拿到过期的 sidebarOpen
   */
  const toggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev);
  }, []);

  const loadSession = useCallback(
    async (id: string) => {
      switchSession(id);
      try {
        const hist = await getSessionHistory(id);
        setMessages(toUiMessages(hist.messages));
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setMessages([
          {
            id: "sys-err",
            role: "system",
            content: `加载历史失败：${msg}`,
          },
        ]);
      }
    },
    [setMessages, switchSession],
  );

  /** 浏览器内存树点选 → 附件 */
  const onPickTreeFile = useCallback(
    async (node: FileTreeNode) => {
      if (node.isDir || !node.file) return;
      const content = await node.file.text();
      addAttachment({
        name: node.name,
        path: node.path,
        mime: node.file.type || "text/plain",
        size: node.file.size,
        content,
        source: "workspace",
      });
    },
    [addAttachment],
  );

  /**
   * 发送：
   * - 桌面有工作区 → 走 workspace_root + files
   * - 否则浏览器附件 → 拼进 message 降级
   */
  const handleSend = useCallback(
    async (text: string) => {
      const ws = toPayload();
      if (ws) {
        const msg = text.trim();
        if (!msg && ws.files.length === 0) return;
        await send(msg || "请根据已打开的工作区文件进行分析或按要求修改。", ws);
        return;
      }

      const merged = buildMessageWithAttachments(text, attachments);
      if (!merged.trim()) return;
      await send(merged, null);
      clearAttachments();
    },
    [attachments, send, clearAttachments, toPayload],
  );

  const canEmptySend =
    (hasDesktopFs && openFiles.length > 0) || attachments.length > 0;

  return (
    /**
     * app-shell：整页外壳
     * 上：顶栏（品牌 + 消息图标）
     * 下：三栏（左会话 / 中聊天 / 右设置）
     */
    <div className="app-shell">
      {/* ========== 顶部栏：品牌名 + 侧栏开关 ========== */}
      <header className="app-header">
        <div className="app-header-brand">
          {/* 小圆点模拟 logo */}
          <span className="app-header-dot" aria-hidden="true" />
          <span className="app-header-title">LangChain Demo Agent</span>
        </div>

        {/*
          消息图标按钮：标题右侧
          - type="button"：避免被当成表单 submit
          - aria-pressed：当前是开还是关
          - title / aria-label：悬停与读屏提示
        */}
        <button
          type="button"
          className={
            sidebarOpen ? "sidebar-toggle is-active" : "sidebar-toggle"
          }
          onClick={toggleSidebar}
          aria-pressed={sidebarOpen}
          aria-label={sidebarOpen ? "隐藏聊天历史" : "显示聊天历史"}
          title={sidebarOpen ? "隐藏聊天历史" : "显示聊天历史"}
        >
          <ChatBubbleIcon />
        </button>
      </header>

      {/*
        三栏网格；sidebar-collapsed 时左列宽度为 0
      */}
      <div className={sidebarOpen ? "app" : "app sidebar-collapsed"}>
        {/* 仅打开时挂载左侧会话列表 */}
        {sidebarOpen && (
          <SessionList
            currentId={sessionId}
            onSelect={(id) => void loadSession(id)}
            onNew={newSession}
          />
        )}

        <main className="main">
          <ModeBar
            mode={mode}
            setMode={setMode}
            multiMode={multiMode}
            setMultiMode={setMultiMode}
            agentName={agentName}
            setAgentName={setAgentName}
            useStream={useStream}
            setUseStream={setUseStream}
            healthLabel={healthLabel}
            healthOk={healthOk}
          />

          {error && <div className="error-banner">{error}</div>}

          <ChatMessages messages={messages} loading={loading} />

          <FileToolbar
            attachments={attachments}
            error={attachError}
            disabled={loading}
            onAddFiles={addFiles}
            onRemove={remove}
            onClear={clearAttachments}
            onPickTreeFile={onPickTreeFile}
            workspace={{
              root,
              tree,
              openFiles,
              error: wsError,
              hasDesktopFs,
              onOpenWorkspace: openWorkspace,
              onListChildren: listChildren,
              onOpenFile: openFile,
              onRemoveOpenFile: removeOpenFile,
            }}
          />

          <ChatInput
            loading={loading}
            onSend={(t) => void handleSend(t)}
            onStop={stop}
            allowEmptySend={canEmptySend}
          />
        </main>

        <div className="side-stack">
          <SettingsPanel
            draft={draft}
            setDraft={setDraft}
            onSave={save}
            onClear={clear}
            savedHint={savedHint}
          />
          <KnowledgePanel />
        </div>
      </div>
    </div>
  );
}
