/**
 * Electron 主进程（main process）
 * =================================
 * 职责：
 * 1. 创建桌面窗口，加载前端页面（开发连 Vite，打包后读 dist）
 * 2. 可选：自动拉起本机 FastAPI（uvicorn :8020），退出时关掉
 * 3. 通过 preload 向渲染进程暴露少量安全信息
 *
 * 为什么用 .cjs？
 * frontend/package.json 声明了 "type": "module"，
 * Electron 入口若写成 .js 可能被当成 ESM；.cjs 强制 CommonJS，最稳。
 *
 * 启动方式（在 frontend 目录）：
 *   npm run dev:desktop
 * 打包：
 *   npm run dist
 */

const {
  app,
  BrowserWindow,
  ipcMain,
  dialog,
  globalShortcut,
  screen,
} = require("electron");
const path = require("path");
const fs = require("fs");
const fsp = fs.promises;
const { spawn, execSync } = require("child_process");
const { API_BASE, isLocalApi } = require("./api-base.cjs");
const API_HOST = process.env.LANGCHAIN_API_HOST || "127.0.0.1";
const API_PORT = Number(process.env.LANGCHAIN_API_PORT || 8020);
const {
  getSelectedText,
  isWorthAnalyzing,
  MIN_LEN,
} = require("./selection.cjs");

/** 桌面应用图标 / 划词圆形按钮（electron/assets） */
const APP_ICON_PATH = path.join(__dirname, "assets", "app-icon.png");
const SELECTION_FAB_PATH = path.join(__dirname, "assets", "selection-fab.png");

/** @type {BrowserWindow | null} */
let mainWindow = null;
/** @type {BrowserWindow | null} */
let explainWindow = null;
/** @type {BrowserWindow | null} */
let iconWindow = null;
/** 防止连按快捷键 / 点图标并发多次分析 */
let explainInFlight = false;
/** 松手读到的选区；点图标时用它，不要再 Ctrl+C */
let pendingExplainText = "";
/** 划词读选区中，避免重入 */
let selectionCaptureBusy = false;
/** 左键按下位置，用来判断拖选还是单击 */
let mouseDownPos = null;
/** @type {import("child_process").ChildProcess | null} */
let apiProcess = null;
/** 划词图标自动隐藏定时器 */
let iconHideTimer = null;
/**
 * 用户是否正在「自定义拖动」圆形图标。
 * true 时：全局 uIOhook 的 mouseup 应忽略（见 isPointInOurWindows），
 * 否则拖图标松手会被当成新划词，图标又弹回鼠标旁。
 */
let iconDragging = false;
const ICON_HIDE_MS = 5000; //5秒后自动隐藏图标
/**
 * 仓库根目录（LangChain_Demo/）
 * - 开发：electron/ 的上一级
 * - 打包后：若把后端放进 extraResources/backend，则用 resourcesPath
 */
function getProjectRoot() {
  if (app.isPackaged) {
    // 优先：用户指定仓库根；否则期望安装时把后端放到 resources/backend
    return (
      process.env.LANGCHAIN_DEMO_ROOT ||
      path.join(process.resourcesPath, "backend")
    );
  }
  return path.join(__dirname, "..");
}

/**
 * 打包后前端静态文件位置
 * electron-builder 会把 frontend/dist 打进应用目录，并映射为 electron/ 旁的 dist
 * （见 frontend/package.json 的 build.files）
 */
function getRendererIndexHtml() {
  if (app.isPackaged) {
    // 打包后：与 electron/main.cjs 同级的上一级 dist（由 builder 配置决定）
    return path.join(app.getAppPath(), "dist", "index.html");
  }
  // 开发一般不走 loadFile；这里兜底指向 frontend/dist
  return path.join(__dirname, "..", "frontend", "dist", "index.html");
}

/**
 * 轮询 /health，等后端真正就绪再开窗口，避免前端一上来就「API 不可达」
 */
async function waitForHealth(timeoutMs = 45000) {
  const url = `${API_BASE}/health`;
  if (!isLocalApi(API_BASE)) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 400) return;
    } catch {
      /* 远端暂时不通也开窗口，避免卡 45 秒 */
    }
    return;
  }
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // 后端还没起来，继续等
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error(`等待后端超时：${url} （请确认 Python 依赖与端口 ${API_PORT}）`);
}

/**
 * Windows：释放被旧 uvicorn 占用的端口，避免 Electron 二次启动时报 10048。
 */
function freeApiPortIfNeeded() {
  if (process.platform !== "win32") return;
  try {
    const out = execSync(`netstat -ano | findstr :${API_PORT}`, {
      encoding: "utf8",
      windowsHide: true,
    });
    const pids = new Set();
    for (const line of out.split(/\r?\n/)) {
      if (!line.includes("LISTENING")) continue;
      const parts = line.trim().split(/\s+/);
      const pid = parts[parts.length - 1];
      if (pid && /^\d+$/.test(pid) && pid !== "0") pids.add(pid);
    }
    for (const pid of pids) {
      console.log(`[electron] 端口 ${API_PORT} 被 PID ${pid} 占用，尝试结束旧进程`);
      try {
        spawn("taskkill", ["/pid", pid, "/f", "/t"], {
          shell: true,
          stdio: "ignore",
          windowsHide: true,
        });
      } catch (e) {
        console.warn(`[electron] taskkill ${pid} 失败:`, e);
      }
    }
  } catch {
    // findstr 无匹配时 exit code 非 0，忽略即可
  }
}

/**
 * 启动 FastAPI。
 * 用 `python -m uvicorn`，比直接找 uvicorn.exe 在 Windows/conda 下更稳。
 *
 * 环境变量：
 * - ELECTRON_START_BACKEND=0  → 不自动起后端（你已在终端手动起了）
 * - PYTHON / PYTHON_PATH      → 指定解释器，默认 "python"
 */
function startBackend() {
  if (process.env.ELECTRON_START_BACKEND === "0") {
    console.log("[electron] 跳过自动启动后端（ELECTRON_START_BACKEND=0）");
    return;
  }
  if (!isLocalApi(API_BASE)) {
    console.log(`[electron] 使用云 API：${API_BASE}，跳过本地 uvicorn`);
    return;
  }
  if (app.isPackaged) {
    console.log("[electron] 安装版不启动本地后端");
    return;
  }
  if (apiProcess) return;

  const root = getProjectRoot();
  // 打包后若没带上 api/ 目录，就不要瞎 spawn，让用户手动起后端
  if (!fs.existsSync(path.join(root, "api", "server.py"))) {
    console.warn(
      `[electron] 未找到后端代码：${path.join(root, "api", "server.py")}\n` +
        "  开发期请在仓库根目录运行；打包版可设置环境变量 LANGCHAIN_DEMO_ROOT，\n" +
        "  或先手动：uvicorn api.server:app --port 8020",
    );
    return;
  }

  // 先清掉残留在端口上的旧后端，再 spawn（否则新进程立刻 10048 退出，UI 仍打到旧代码）
  freeApiPortIfNeeded();

  const python = process.env.PYTHON_PATH || process.env.PYTHON || "python";

  console.log(`[electron] 启动后端：${python} -m uvicorn @ ${root}`);

  apiProcess = spawn(
    python,
    [
      "-m",
      "uvicorn",
      "api.server:app",
      "--host",
      API_HOST,
      "--port",
      String(API_PORT),
    ],
    {
      cwd: root,
      shell: true,
      env: { ...process.env },
      // 把子进程输出打到主进程终端，方便排错
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  apiProcess.stdout?.on("data", (buf) => {
    console.log(`[api] ${buf.toString().trimEnd()}`);
  });
  apiProcess.stderr?.on("data", (buf) => {
    console.error(`[api] ${buf.toString().trimEnd()}`);
  });
  apiProcess.on("exit", (code, signal) => {
    console.log(`[electron] 后端退出 code=${code} signal=${signal}`);
    apiProcess = null;
  });
}

function stopBackend() {
  if (!apiProcess) return;
  try {
    // Windows 上 kill 整棵进程树更干净
    if (process.platform === "win32" && apiProcess.pid) {
      spawn("taskkill", ["/pid", String(apiProcess.pid), "/f", "/t"], {
        shell: true,
      });
    } else {
      apiProcess.kill("SIGTERM");
    }
  } catch (e) {
    console.error("[electron] 停止后端失败:", e);
  }
  apiProcess = null;
}

/**
 * 安全：把 relPath 解析到 absRoot 下，禁止 .. 穿越到根外
 * @returns {string} 绝对规范化路径
 */
function resolveInsideRoot(absRoot, relPath = "") {
  const root = path.resolve(absRoot);
  const target = path.resolve(root, relPath || ".");
  // 确保 target 以 root + sep 开头（或等于 root）
  const rel = path.relative(root, target);
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    throw new Error("路径越界：不允许访问工作区以外的文件");
  }
  return target;
}

/** 仅允许常见文本，避免把 bin/图片当 UTF-8 读 */
const TEXT_EXT =
  /\.(txt|md|py|ts|tsx|js|jsx|json|css|html|yml|yaml|toml|ini|csv|log|sql|rs|go|java|c|cpp|h)$/i;

function assertTextFile(filePath) {
  if (!TEXT_EXT.test(filePath)) {
    throw new Error("仅支持文本源码/配置文件");
  }
}

/** 注册工作区 IPC（完整版核心） */
function registerWorkspaceIpc() {
  // 选工作区根目录
  ipcMain.handle("ws:select-directory", async () => {
    const win = BrowserWindow.getFocusedWindow();
    const r = await dialog.showOpenDialog(win ?? undefined, {
      properties: ["openDirectory"],
    });
    if (r.canceled || !r.filePaths[0]) return null;
    return r.filePaths[0];
  });

  // 列一层目录
  ipcMain.handle("ws:list-dir", async (_evt, { absRoot, relPath }) => {
    const dir = resolveInsideRoot(absRoot, relPath || "");
    const names = await fsp.readdir(dir, { withFileTypes: true });
    // 过滤隐藏文件（可按需调整）
    return names
      .filter((d) => !d.name.startsWith("."))
      .map((d) => {
        const childRel = relPath ? `${relPath}/${d.name}` : d.name;
        // Windows 下统一用 /
        const norm = childRel.replace(/\\/g, "/");
        return {
          name: d.name,
          path: norm,
          isDir: d.isDirectory(),
        };
      })
      .sort((a, b) => Number(b.isDir) - Number(a.isDir) || a.name.localeCompare(b.name));
  });

  // 读文件
  ipcMain.handle("ws:read-file", async (_evt, { absRoot, relPath }) => {
    const fp = resolveInsideRoot(absRoot, relPath);
    assertTextFile(fp);
    const st = await fsp.stat(fp);
    if (st.size > 512 * 1024) throw new Error("文件超过 512KB，拒绝读入");
    return fsp.readFile(fp, "utf-8");
  });

  // 写文件（Agent 改代码后的落盘；也可前端「应用修改」调用）
  ipcMain.handle("ws:write-file", async (_evt, { absRoot, relPath, content }) => {
    const fp = resolveInsideRoot(absRoot, relPath);
    assertTextFile(fp);
    if (typeof content !== "string") throw new Error("content 必须是字符串");
    if (Buffer.byteLength(content, "utf-8") > 1024 * 1024*10) {
      throw new Error("写入内容超过 10MB");
    }
    await fsp.mkdir(path.dirname(fp), { recursive: true });
    await fsp.writeFile(fp, content, "utf-8");
    return { ok: true };
  });
}
/**
 * 创建或复用置顶分析小窗（先不抢焦点，避免 Ctrl+C 拷到本窗）
 */
function ensureExplainWindow() {
  if (explainWindow && !explainWindow.isDestroyed()) {
    return explainWindow;
  }
  explainWindow = new BrowserWindow({
    width: 420,
    height: 520,
    minWidth: 320,
    minHeight: 360,
    show: false,
    alwaysOnTop: true,
    autoHideMenuBar: true,
    title: "划词分析",
    icon: APP_ICON_PATH,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "explain-preload.cjs"),
    },
  });
  explainWindow.loadFile(path.join(__dirname, "explain.html"));
  explainWindow.on("closed", () => {
    explainWindow = null;
  });
  return explainWindow;
}

/** 等小窗页面加载完再发 IPC，避免首帧 push 丢失 */
async function ensureExplainWindowReady() {
  const win = ensureExplainWindow();
  if (!win.webContents.isLoading()) return win;
  await new Promise((resolve) => {
    win.webContents.once("did-finish-load", resolve);
  });
  return win;
}

/** 向小窗推状态（小窗未就绪时忽略） */
function pushExplainUpdate(payload) {
  if (!explainWindow || explainWindow.isDestroyed()) return;
  explainWindow.webContents.send("explain:update", payload);
}

async function getAuthHeaders() {
  const TOKEN_KEY = "auth.access_token.v1";
  if (!mainWindow || mainWindow.isDestroyed()) {
    throw new Error("请先打开主窗口并登录，再使用划词分析");
  }
  const token = await mainWindow.webContents.executeJavaScript(
    `localStorage.getItem(${JSON.stringify(TOKEN_KEY)}) || ""`,
    true,
  );
  const t = String(token || "").trim();
  if (!t) {
    throw new Error("未登录：请在主窗口登录后再划词");
  }
  return  { Authorization: `Bearer ${t}` };
}


/**
 * 调现有 FastAPI：POST /api/chat
 */
async function analyzeTextWithBackend(selected) {
  const auth = await getAuthHeaders();
  const clipped =
    selected.length > 9000 ? `${selected.slice(0, 9000)}\n…(已截断)` : selected;
  const message =
    "请分析下面用户选中的内容。若是代码：说明作用、关键逻辑、注意点；" +
    "若是普通文字：概括含义并解释难懂处。用简洁中文回答。\n\n" +
    "---- 选中内容开始 ----\n" +
    clipped +
    "\n---- 选中内容结束 ----";
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...auth,
    },
    body: JSON.stringify({
      message,
      session_id: `explain-${Date.now()}`,
      mode: "chat",
    }),
  });
  if (!res.ok) {
    const t = await res.text().catch(() => res.statusText);
    throw new Error(t || `HTTP ${res.status}`);
  }
  const data = await res.json();
  return data.answer || "";
}

/** ---------- 划词圆形图标窗 ---------- */

function ensureIconWindow() {
  if (iconWindow && !iconWindow.isDestroyed()) return iconWindow;

  iconWindow = new BrowserWindow({
    width: 52,
    height: 52,
    show: false,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    movable: true, // 保留系统可移动；实际拖动靠 icon.html JS + icon:move（透明窗 CSS drag 不可靠）
    skipTaskbar: true,
    focusable: true,
    hasShadow: false,
    icon: APP_ICON_PATH,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "icon-preload.cjs"),
    },
  });

  iconWindow.setAlwaysOnTop(true, "screen-saver");
  iconWindow.loadFile(path.join(__dirname, "icon.html"));

  // 拖动中重置 5 秒倒计时，避免拖着拖着图标消失
  iconWindow.on("will-move", () => {
    if (iconWindow && !iconWindow.isDestroyed() && iconWindow.isVisible()) {
      scheduleIconHide();
    }
  });

  iconWindow.on("closed", () => {
    clearIconHideTimer();
    iconWindow = null;
  });
  return iconWindow;
}

function clearIconHideTimer() {
  if (iconHideTimer) {
    clearTimeout(iconHideTimer);
    iconHideTimer = null;
  }
}

/** 从现在起再等 5 秒，无人点击/悬停则藏图标 */
function scheduleIconHide() {
  clearIconHideTimer();
  iconHideTimer = setTimeout(() => {
    hideIconWindow();
    pendingExplainText = ""; // 过期选区作废
    iconHideTimer = null;
  }, ICON_HIDE_MS);
}

function hideIconWindow() {
  clearIconHideTimer();
  // 隐藏时若还在拖，也要清标志，否则全局钩子会一直被 iconDragging 挡住
  iconDragging = false;
  if (iconWindow && !iconWindow.isDestroyed() && iconWindow.isVisible()) {
    iconWindow.hide();
  }
}

function showIconWindowAt(screenX, screenY, text) {
  pendingExplainText = text;
  const win = ensureIconWindow();

  let x = Math.round(screenX + 16);
  let y = Math.round(screenY + 16);
  const display = screen.getDisplayNearestPoint({ x, y });
  const b = display.workArea;
  // 窗口 52×52，留边距
  x = Math.min(x, b.x + b.width - 56);
  y = Math.min(y, b.y + b.height - 56);
  x = Math.max(x, b.x);
  y = Math.max(y, b.y);

  win.setPosition(x, y);
  if (!win.isVisible()) win.showInactive();
  scheduleIconHide();
}

/**
 * 判断屏幕坐标是否落在「我们自己的窗口」上（含容差）。
 * 用途：全局划词钩子 mouseup 时，若点在自己窗上就不要再弹图标 / 读选区。
 */
function isPointInOurWindows(screenX, screenY) {
  // 正在拖圆形图标：整次手势都算「在我们窗上」，直接挡掉全局钩子
  if (iconDragging) return true;

  // Windows 下 uIOhook 坐标与 BrowserWindow.getPosition() 可能因 DPI 差几像素，
  // 加一圈 pad，避免拖完松手刚好落在窗边外被误判成「桌面划词」
  const pad = 24;

  const wins = [iconWindow, explainWindow, mainWindow];
  for (const w of wins) {
    // 窗口不存在 / 已销毁 / 没显示：跳过
    if (!w || w.isDestroyed() || !w.isVisible()) continue;
    // 窗口左上角与宽高（Electron 逻辑像素）
    const [wx, wy] = w.getPosition();
    const [ww, wh] = w.getSize();
    if (
      screenX >= wx - pad &&
      screenX <= wx + ww + pad &&
      screenY >= wy - pad &&
      screenY <= wy + wh + pad
    ) {
      return true;
    }
  }
  return false;
}

async function onGlobalMouseUpMaybeShowIcon(screenX, screenY) {
  if (selectionCaptureBusy || explainInFlight) return;
  if (isPointInOurWindows(screenX, screenY)) return;

  selectionCaptureBusy = true;
  try {
    const { text, method } = await getSelectedText();
    console.log(`[icon] capture method=${method}, len=${text.length}`);
    if (!isWorthAnalyzing(text)) {
      hideIconWindow();
      pendingExplainText = "";
      return;
    }
    showIconWindowAt(screenX, screenY, text);
  } catch (e) {
    console.error("[icon] capture failed", e);
    hideIconWindow();
  } finally {
    selectionCaptureBusy = false;
  }
}

/**
 * 用已知文本打开分析窗并请求后端（快捷键 / 点图标共用）
 */
async function runExplainWithText(text) {
  if (explainInFlight) {
    console.log("[explain] 已有任务进行中，忽略");
    return;
  }
  explainInFlight = true;
  hideIconWindow();

  try {
    const win = await ensureExplainWindowReady();
    if (!win.isVisible()) win.show();
    win.focus();

    if (!isWorthAnalyzing(text)) {
      pushExplainUpdate({
        phase: "error",
        selected: text || "",
        detail: `未读到有效选区（至少 ${MIN_LEN} 个字符）。`,
      });
      return;
    }

    pushExplainUpdate({
      phase: "loading",
      selected: text,
      answer: "",
    });

    const answer = await analyzeTextWithBackend(text);
    pushExplainUpdate({
      phase: "done",
      selected: text,
      answer,
    });
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    console.error("[explain]", detail);
    try {
      await ensureExplainWindowReady();
      if (explainWindow && !explainWindow.isDestroyed()) {
        if (!explainWindow.isVisible()) explainWindow.show();
        explainWindow.focus();
      }
      pushExplainUpdate({
        phase: "error",
        detail: detail || "分析失败",
      });
    } catch {
      /* ignore */
    }
  } finally {
    explainInFlight = false;
  }
}

/** 快捷键：现场读选区 → 分析（不经过图标） */
async function runExplainFromHotkey() {
  const { text, method } = await getSelectedText();
  console.log(`[explain] hotkey method=${method}, len=${text.length}`);
  await runExplainWithText(text);
}

function registerExplainHotkey() {
  globalShortcut.unregisterAll();
  const accel = "CommandOrControl+Shift+A";
  const ok = globalShortcut.register(accel, () => {
    void runExplainFromHotkey();
  });
  if (!ok) {
    console.error(`[explain] 快捷键注册失败：${accel}（可能被其它软件占用）`);
  } else {
    console.log(`[explain] 已注册全局快捷键：${accel}`);
  }
}

function registerExplainIpc() {
  ipcMain.on("explain:close", () => {
    if (explainWindow && !explainWindow.isDestroyed()) {
      explainWindow.close();
    }
  });

  ipcMain.on("icon:analyze", () => {
    clearIconHideTimer(); // 已点击，不要再自动藏
    const text = pendingExplainText;
    if (!isWorthAnalyzing(text)) {
      hideIconWindow();
      return;
    }
    void runExplainWithText(text);
  });

  // 鼠标停在图标上 / 拖动中：重置 5 秒倒计时
  ipcMain.on("icon:ping", () => {
    if (iconWindow && !iconWindow.isDestroyed() && iconWindow.isVisible()) {
      scheduleIconHide();
    }
  });

  /**
   * icon:move — 渲染进程自定义拖动发来的「相对位移」
   * payload: { dx, dy }，单位：屏幕像素，相对上一帧，不是绝对坐标
   */
  ipcMain.on("icon:move", (_evt, payload) => {
    // 窗没了或不显示：忽略（避免 hide 之后还在收 move）
    if (!iconWindow || iconWindow.isDestroyed() || !iconWindow.isVisible()) {
      return;
    }

    // 转成数字；非法 / 缺失当 0
    const dx = Number(payload?.dx) || 0;
    const dy = Number(payload?.dy) || 0;
    // 两轴都是 0：没必要 setPosition
    if (!dx && !dy) return;

    // 标记正在拖：挡住全局划词钩子，直到 icon:drag-end
    iconDragging = true;

    // 当前窗口左上角
    const [x, y] = iconWindow.getPosition();
    // 加上相对位移，得到候选新位置
    let nx = Math.round(x + dx);
    let ny = Math.round(y + dy);

    // 钳到最近显示器的工作区（避开任务栏），留 56≈52 窗宽 + 一点边距
    const display = screen.getDisplayNearestPoint({ x: nx, y: ny });
    const b = display.workArea;
    nx = Math.min(Math.max(nx, b.x), b.x + b.width - 56);
    ny = Math.min(Math.max(ny, b.y), b.y + b.height - 56);

    // 真正挪窗（透明无框窗用 JS 拖，比 -webkit-app-region:drag 可靠）
    iconWindow.setPosition(nx, ny);
    // 拖一下也续命，避免拖着拖着 5 秒到了被藏掉
    scheduleIconHide();
  });

  /**
   * icon:drag-end — 渲染进程 pointerup / pointercancel
   * 清掉拖动标志，之后全局钩子恢复正常判断
   */
  ipcMain.on("icon:drag-end", () => {
    iconDragging = false;
  });
}

/** 全局鼠标钩子：拖选松手后弹出圆形分析图标 */
function startGlobalSelectionHook() {
  let uIOhook;
  try {
    uIOhook = require(path.join(
      __dirname,
      "..",
      "frontend",
      "node_modules",
      "uiohook-napi",
    )).uIOhook;
  } catch (e1) {
    try {
      uIOhook = require("uiohook-napi").uIOhook;
    } catch (e2) {
      console.warn(
        "[icon] 未加载 uiohook-napi，划词图标不可用（快捷键仍可用）。",
        e2?.message || e1?.message,
      );
      return;
    }
  }

  uIOhook.on("mousedown", (e) => {
    if (e.button === 1) {
      mouseDownPos = { x: e.x, y: e.y };
    }
  });

  uIOhook.on("mouseup", (e) => {
    if (e.button !== 1) return;
    const down = mouseDownPos;
    mouseDownPos = null;
    if (!down) return;

    const dist = Math.hypot(e.x - down.x, e.y - down.y);
    if (dist < 6) return;

    setTimeout(() => {
      void onGlobalMouseUpMaybeShowIcon(e.x, e.y);
    }, 80);
  });

  uIOhook.start();
  console.log("[icon] 全局鼠标钩子已启动");
  console.log("[icon] fab asset:", SELECTION_FAB_PATH);

  app.on("will-quit", () => {
    try {
      uIOhook.stop();
    } catch {
      /* ignore */
    }
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 640,
    title: "LangChain Demo Agent",
    icon: APP_ICON_PATH,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.cjs"),
    },
  });

  if (!app.isPackaged) {
    mainWindow.loadURL("http://127.0.0.1:5173");
  } else {
    // 安装版直接打开云站点，与网页同源，避免 file:// CORS
    mainWindow.loadURL(API_BASE);
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

async function boot() {
  registerWorkspaceIpc();
  registerExplainIpc();

  startBackend();

  try {
    await waitForHealth();
  } catch (e) {
    console.error(e);
  }

  createWindow();
  registerExplainHotkey();
  startGlobalSelectionHook();
}

app.whenReady().then(boot);

app.on("activate", () => {
  // macOS：点 Dock 图标时若没有窗口则重建
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on("window-all-closed", () => {
  globalShortcut.unregisterAll();
  stopBackend();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  globalShortcut.unregisterAll();
  stopBackend();
});
