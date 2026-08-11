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

const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const path = require("path");
const fs = require("fs");
const fsp = fs.promises;
const { spawn } = require("child_process");

/** @type {BrowserWindow | null} */
let mainWindow = null;

/** @type {import("child_process").ChildProcess | null} */
let apiProcess = null;

/** 后端地址：可读环境变量，默认与 frontend/.env.example 的 VITE_API_BASE 一致 */
const API_HOST = process.env.LANGCHAIN_API_HOST || "127.0.0.1";
const API_PORT = Number(process.env.LANGCHAIN_API_PORT || 8020);
const API_BASE =
  process.env.LANGCHAIN_API_BASE || `http://${API_HOST}:${API_PORT}`;

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

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 640,
    title: "LangChain Demo Agent",
    webPreferences: {
      // 安全默认：渲染进程不能直接 require Node
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.cjs"),
    },
  });

  if (!app.isPackaged) {
    // 开发：连 Vite 热更新
    mainWindow.loadURL("http://127.0.0.1:5173");
    // 需要调试前端时可打开：
    // mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    // 生产：加载打包后的静态页（vite base 必须是 "./"）
    mainWindow.loadFile(getRendererIndexHtml());
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

async function boot() {
  // 0) 注册工作区 IPC（选目录 / 列目录 / 读 / 写）
  registerWorkspaceIpc();

  // 1) 先起后端（可被环境变量关掉）
  startBackend();

  // 2) 等健康检查；若用户手动起了后端，这里也会立刻通过
  try {
    await waitForHealth();
  } catch (e) {
    console.error(e);
    // 即使超时也开窗口，方便用户在 UI 里看到「API 不可达」并自行排查
  }

  // 3) 开窗口
  createWindow();
}

app.whenReady().then(boot);

app.on("activate", () => {
  // macOS：点 Dock 图标时若没有窗口则重建
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on("window-all-closed", () => {
  stopBackend();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  stopBackend();
});
