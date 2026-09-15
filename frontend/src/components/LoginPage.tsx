// ============================================================================
// LoginPage.tsx：桌面端全屏登录页（未拿到 JWT 时挡住主界面）
// ============================================================================

// 状态：输入框、忙碌、错误
import { useState } from "react";
// 调后端 POST /api/auth/login
import { postLogin } from "../api/endpoints";
// 把 JWT 写入 localStorage，后续 apiJson / 上传 / SSE 会自动带 Bearer
import { saveToken } from "../auth/token";

/** 登录成功后由父组件切到主界面 */
type LoginPageProps = {
  onLoggedIn: () => void;
};

export function LoginPage({ onLoggedIn }: LoginPageProps) {
  // 默认用户名与 .env 里 ADMIN_USERNAME 对齐，方便本机调试
  const [username, setUsername] = useState("admin");
  // 密码不预填，避免窗口被别人看见
  const [password, setPassword] = useState("");
  // 请求进行中：禁用按钮，防重复提交
  const [busy, setBusy] = useState(false);
  // 登录失败文案（401「用户名或密码错误」等）
  const [err, setErr] = useState<string | null>(null);

  /** 提交表单：校验 → 请求 → 存 token → 通知父组件 */
  const onSubmit = async () => {
    // 去掉首尾空格再判断空
    const u = username.trim();
    const p = password;
    if (!u || !p) {
      setErr("请输入用户名和密码");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      // 与后端 LoginRequest 字段一致：username / password
      const res = await postLogin({ username: u, password: p });
      // 只存 access_token；api 层用 authHeaders() 拼 Authorization
      saveToken(res.access_token);
      // 清空密码，避免停留在内存/输入框
      setPassword("");
      // 让 App 把 loggedIn 设为 true，渲染主界面
      onLoggedIn();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    // 铺满窗口的浅底，卡片垂直水平居中
    <div className="login-page">
      <form
        className="login-card"
        // 回车也能提交；阻止浏览器默认刷新
        onSubmit={(e) => {
          e.preventDefault();
          void onSubmit();
        }}
      >
        <div className="login-card-brand">
          <span className="app-header-dot" aria-hidden="true" />
          <h1 className="login-card-title">LangChain Demo Agent</h1>
        </div>
        <p className="muted login-card-hint">登录后使用对话、知识库与设置</p>

        <label className="muted" htmlFor="login-user">
          用户名
        </label>
        <input
          id="login-user"
          className="login-page-input"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          disabled={busy}
        />

        <label className="muted" htmlFor="login-pass">
          密码
        </label>
        <input
          id="login-pass"
          className="login-page-input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          disabled={busy}
        />

        {err && <div className="error-banner login-page-err">{err}</div>}

        <button type="submit" className="btn primary login-page-btn" disabled={busy}>
          {busy ? "登录中…" : "登录"}
        </button>
      </form>
    </div>
  );
}