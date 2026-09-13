/**
 * selection.cjs — 读取系统当前选中文本（Windows 优先）
 * ------------------------------------------------
 * 策略（第一期求稳）：
 * 1) 记下旧剪贴板
 * 2) 向系统发送 Ctrl+C
 * 3) 短暂等待后读剪贴板
 * 4) 尽量恢复旧剪贴板
 *
 * 注意：会短暂占用剪贴板；这是划词工具常见折中，后期可再强化 UIA。
 */
const { clipboard } = require("electron");
const { execFile } = require("child_process");
const { promisify } = require("util");

const execFileAsync = promisify(execFile);

const MIN_LEN = 2; // 太短不分析

/** 等一会儿，给目标软件时间把选区拷进剪贴板 */
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Windows：用 PowerShell 向「当前前台」发送 Ctrl+C
 * 不依赖额外 npm 原生模块，方便你手写跑通。
 */
async function sendCtrlCWindows() {
  // SendKeys 需要 STA；-STA 很重要
  const script = `
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("^c")
`;
  await execFileAsync(
    "powershell.exe",
    ["-NoProfile", "-STA", "-Command", script],
    { windowsHide: true, timeout: 5000 },
  );
}

/**
 * 尝试读取选中文本。
 * @returns {Promise<{ text: string, method: string }>}
 */
async function getSelectedText() {
  if (process.platform !== "win32") {
    // 非 Windows：第一期先只提示；你后期可补 macOS 的 osascript
    return { text: "", method: "unsupported" };
  }

  const prev = clipboard.readText();

  // 写入一个不太可能和选区相同的标记，便于判断「是否真的拷到了新内容」
  const marker = `__lc_sel_${Date.now()}__`;
  clipboard.writeText(marker);

  try {
    await sendCtrlCWindows();
    // 不同软件拷贝速度不同，可按需调大
    await sleep(180);

    let text = (clipboard.readText() || "").trim();

    // 若仍是 marker，说明 Ctrl+C 没生效 / 没有选区
    if (!text || text === marker) {
      text = "";
    }

    return { text, method: "clipboard-ctrlc" };
  } finally {
    // 尽量恢复用户原来的剪贴板（失败也无所谓）
    try {
      clipboard.writeText(prev ?? "");
    } catch {
      /* ignore */
    }
  }
}

function isWorthAnalyzing(text) {
  return typeof text === "string" && text.trim().length >= MIN_LEN;
}

module.exports = {
  getSelectedText,
  isWorthAnalyzing,
  MIN_LEN,
};