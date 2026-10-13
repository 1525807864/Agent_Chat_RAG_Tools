/**
 * App：整页外壳 = 顶栏 +（门户首页 | 对话三栏 | 测试工作台）
 * ------------------------------------------------
 * workspace=home：AgentHub 式领域门户（默认）
 * workspace=chat：原会话 / 聊天 / 设置
 * workspace=qa：测试工作台
 * workspace=ops：运维排障（HolmesGPT）
 */
import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Space, Tag, Tooltip } from "antd";
import {
  CloudServerOutlined,
  CommentOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  HomeOutlined,
  LogoutOutlined,
  MessageOutlined,
} from "@ant-design/icons";
import { HomePortal } from "./components/HomePortal";
import { OpsWorkspace } from "./components/ops/OpsWorkspace";
import { QaWorkspace } from "./components/QaWorkspace";
import {
  desktopDownloadUrl,
  fetchDesktopDownloadMeta,
  getSessionHistory,
  waitUntilReady,
} from "./api/endpoints";
import { getApiBase } from "./api/client";
import { ChatInput } from "./components/ChatInput";
import { ChatMessages } from "./components/ChatMessages";
import { FileToolbar } from "./components/FileToolbar";
import { KnowledgePanel } from "./components/KnowledgePanel";
import { LoginPage } from "./components/LoginPage";
import { ModeBar } from "./components/ModeBar";
import { SessionList } from "./components/SessionList";
import { SettingsPanel } from "./components/SettingsPanel";
import { TaskPlanPanel } from "./components/TaskPlanPanel";
import { TokenPriceCalculator } from "./components/TokenPriceCalculator";
import {
  buildMessageWithAttachments,
  useAttachments,
} from "./hooks/useAttachments";
import { useChat } from "./hooks/useChat";
import { useLlmSettings } from "./hooks/useLlmSettings";
import { useWorkspace } from "./hooks/useWorkspace";
import { clearToken, loadToken } from "./auth/token";
import type { FileTreeNode } from "./types/attachment";
import type { UiMessage } from "./types/api";
import { IcpFooter } from "./components/IcpFooter";
import { NexoraLogo } from "./components/NexoraLogo";

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
  // 有本地 JWT 才进主界面；刷新窗口仍保持登录
  const [loggedIn, setLoggedIn] = useState(() => Boolean(loadToken()));
  // 桌面壳里已经是客户端，顶栏不再显示下载
  const inElectron = Boolean(window.electronAPI?.isElectron);
  const [downloadReady, setDownloadReady] = useState(false);
  const [downloadDetail, setDownloadDetail] = useState("正在检查安装包…");

  // home=门户；chat=对话；qa=测试；ops=运维；hash 刷新后仍停在对应页
  const [workspace, setWorkspace] = useState<"home" | "chat" | "qa" | "ops">(
    () => {
      const h = window.location.hash;
      if (h === "#/qa") return "qa";
      if (h === "#/ops") return "ops";
      if (h === "#/chat") return "chat";
      return "home";
    },
  );

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
    if (workspace === "qa") window.location.hash = "/qa";
    else if (workspace === "ops") window.location.hash = "/ops";
    else if (workspace === "chat") window.location.hash = "/chat";
    else window.location.hash = "/";
  }, [workspace]);

  useEffect(() => {
    if (!loggedIn || inElectron) return;
    let cancelled = false;
    fetchDesktopDownloadMeta()
      .then((meta) => {
        if (cancelled) return;
        setDownloadReady(meta.available);
        setDownloadDetail(meta.available ? "" : meta.detail || "安装包尚未发布");
      })
      .catch(() => {
        if (cancelled) return;
        setDownloadReady(false);
        setDownloadDetail("暂时无法获取安装包");
      });
    return () => {
      cancelled = true;
    };
  }, [loggedIn, inElectron]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // 闭环：等 /health/ready，避免进程活着但业务未初始化就开放 UI
        const h = await waitUntilReady(60_000, 500);
        if (cancelled) return;
        setHealthOk(true);
        setHealthLabel(
          `API Ready · ${getApiBase()} · modes: ${h.modes.join(", ")}`,
        );
      } catch (e) {
        if (cancelled) return;
        setHealthOk(false);
        const msg = e instanceof Error ? e.message : String(e);
        setHealthLabel(`API 未就绪 · ${getApiBase()} · ${msg}`);
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
      // 顺带装载意图台账（切会话时面板立即刷新）
      void loadTaskPlan(id);
    },
    [setMessages, switchSession, loadTaskPlan],
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
  useEffect(() => {
    const onLogout = () => setLoggedIn(false);
    window.addEventListener("auth:logout", onLogout);
    return () => window.removeEventListener("auth:logout", onLogout);
  }, []);
  const canEmptySend =
    (hasDesktopFs && openFiles.length > 0) || attachments.length > 0;

  // 未登录：只渲染登录页，不挂载会话/知识库
  if (!loggedIn) {
    return <LoginPage onLoggedIn={() => setLoggedIn(true)} />;
  }

  return (
    /**
     * app-shell：整页外壳
     * 上：顶栏（品牌 + 下载/退出；工作台内可回门户）
     * 下：门户 | 对话三栏 | 测试工作台
     */
    <div className="app-shell">
      <header className="app-header ant-app-header">
        <div className="app-header-brand">
          <NexoraLogo />
          <span className="app-header-title">Nexora</span>
          <Tag color="processing" className="app-header-badge">
            衡知
          </Tag>
        </div>

        {workspace === "chat" ? (
          <Tooltip title={sidebarOpen ? "隐藏聊天历史" : "显示聊天历史"}>
            <Button
              type={sidebarOpen ? "primary" : "text"}
              icon={<CommentOutlined />}
              onClick={toggleSidebar}
              aria-pressed={sidebarOpen}
              aria-label={sidebarOpen ? "隐藏聊天历史" : "显示聊天历史"}
            />
          </Tooltip>
        ) : null}

        <div className="app-header-spacer" />

        <Space size={8} wrap>
          {workspace !== "home" ? (
            <Button
              icon={<HomeOutlined />}
              onClick={() => setWorkspace("home")}
            >
              工作台首页
            </Button>
          ) : null}

          {workspace === "chat" || workspace === "qa" ? (
            <Button
              type={workspace === "qa" ? "primary" : "default"}
              icon={
                workspace === "qa" ? (
                  <MessageOutlined />
                ) : (
                  <ExperimentOutlined />
                )
              }
              onClick={() =>
                setWorkspace(workspace === "qa" ? "chat" : "qa")
              }
            >
              {workspace === "qa" ? "返回对话" : "测试工作台"}
            </Button>
          ) : null}

          {workspace === "chat" || workspace === "ops" ? (
            <Button
              type={workspace === "ops" ? "primary" : "default"}
              icon={
                workspace === "ops" ? (
                  <MessageOutlined />
                ) : (
                  <CloudServerOutlined />
                )
              }
              onClick={() =>
                setWorkspace(workspace === "ops" ? "chat" : "ops")
              }
            >
              {workspace === "ops" ? "返回对话" : "运维排障"}
            </Button>
          ) : null}

          {!inElectron &&
            (downloadReady ? (
              <Button
                icon={<DownloadOutlined />}
                href={desktopDownloadUrl()}
                target="_blank"
                rel="noreferrer"
              >
                下载客户端
              </Button>
            ) : (
              <Tooltip title={downloadDetail}>
                <Button icon={<DownloadOutlined />} disabled>
                  下载客户端
                </Button>
              </Tooltip>
            ))}

          {tenantUsage ? (
            <Tag className="token-bar" title="租户累计 Token（Redis）">
              入 {tenantUsage.tokens_in} · 出 {tenantUsage.tokens_out} · 请求{" "}
              {tenantUsage.requests}
            </Tag>
          ) : null}

          <TokenPriceCalculator tenantUsage={tenantUsage} />

          <Button
            icon={<LogoutOutlined />}
            onClick={() => {
              clearToken();
              setLoggedIn(false);
            }}
          >
            退出
          </Button>
        </Space>
      </header>

      {workspace === "home" ? (
        <HomePortal
          onEnter={(ws) => setWorkspace(ws)}
          onNewChat={() => {
            setWorkspace("chat");
            newSession();
          }}
          userLabel="Lee"
        />
      ) : workspace === "qa" ? (
        <QaWorkspace />
      ) : workspace === "ops" ? (
        <OpsWorkspace />
      ) : (
        /*
          三栏网格；sidebar-collapsed 时左列宽度为 0
        */
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
              e2eBaseUrl={e2eBaseUrl}
              setE2eBaseUrl={setE2eBaseUrl}
              qaTenantId={qaTenantId}
              setQaTenantId={setQaTenantId}
              useStream={useStream}
              setUseStream={setUseStream}
              healthLabel={healthLabel}
              healthOk={healthOk}
            />

            {error ? (
              <Alert
                type="error"
                showIcon
                closable={false}
                message={error}
                className="error-banner"
              />
            ) : null}

            <TaskPlanPanel taskPlan={taskPlan} lastCheck={lastCheck} />

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
      )}
      <IcpFooter />
    </div>
  );
}
