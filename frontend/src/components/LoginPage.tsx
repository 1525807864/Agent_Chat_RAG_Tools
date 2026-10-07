// ============================================================================
// LoginPage.tsx：桌面端全屏登录页（未拿到 JWT 时挡住主界面）
// ============================================================================

// 状态：输入框、忙碌、错误
import { useEffect, useRef, useState } from "react";
// 调后端 POST /api/auth/login
import { postLogin, postRegister } from "../api/endpoints";
// 把 JWT 写入 localStorage，后续 apiJson / 上传 / SSE 会自动带 Bearer
import { saveToken } from "../auth/token";
import { IcpFooter } from "./IcpFooter";
import { NexoraLogo } from "./NexoraLogo";

/** 登录成功后由父组件切到主界面 */
type LoginPageProps = {
  onLoggedIn: () => void;
};

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  len: number;
  size: number;
  alpha: number;
  dark: boolean;
};

/** 蓝紫渐变上的轻粒子：小点与短划缓慢漂移，不挡点击。 */
function LoginParticles() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduce =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let particles: Particle[] = [];
    let frame = 0;
    let alive = true;

    const resize = () => {
      const parent = canvas.parentElement;
      const w = parent?.clientWidth || window.innerWidth;
      const h = parent?.clientHeight || window.innerHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.min(90, Math.max(36, Math.floor((w * h) / 18000)));
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.22,
        len: 6 + Math.random() * 14,
        size: Math.random() < 0.55 ? 1.2 : 0,
        alpha: 0.25 + Math.random() * 0.55,
        dark: Math.random() < 0.08,
      }));
    };

    const draw = () => {
      if (!alive) return;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx.clearRect(0, 0, w, h);
      for (const p of particles) {
        if (!reduce) {
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < -20) p.x = w + 20;
          if (p.x > w + 20) p.x = -20;
          if (p.y < -20) p.y = h + 20;
          if (p.y > h + 20) p.y = -20;
        }
        ctx.strokeStyle = p.dark
          ? `rgba(30, 24, 60, ${p.alpha})`
          : `rgba(255, 255, 255, ${p.alpha})`;
        ctx.lineWidth = p.size > 0 ? p.size : 1.4;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(p.x + p.len, p.y);
        ctx.stroke();
      }
      frame = window.requestAnimationFrame(draw);
    };

    resize();
    draw();
    window.addEventListener("resize", resize);
    return () => {
      alive = false;
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="login-particles" aria-hidden="true" />;
}

export function LoginPage({ onLoggedIn }: LoginPageProps) {
  // 默认用户名与 .env 里 ADMIN_USERNAME 对齐，方便本机调试
  const [username, setUsername] = useState("");
  // 密码不预填，避免窗口被别人看见
  const [password, setPassword] = useState("");

  //仅仅注册时使用
  const [password2,setPassword2] = useState("");
  // 请求进行中：禁用按钮，防重复提交
  const [busy, setBusy] = useState(false);
  // 登录失败文案（401「用户名或密码错误」等）
  const [err, setErr] = useState<string | null>(null);
  //true表单走注册接口
  const [isRegister,setIsRegister] = useState(false);

  /** 提交表单：校验 → 请求 → 存 token → 通知父组件 */
  const onSubmit = async () => {
    // 去掉首尾空格再判断空
    const u = username.trim();
    const p = password;
    if (!u || !p) {
      setErr("请输入用户名和密码");
      return;
    }
    
    if (isRegister && u.length<3) {
      setErr("用户名至少3位，并以字母开头");
      return;
    }
    if (isRegister && p.length<8) {
      setErr("密码至少8位");
      return;
    }
    if (isRegister && p!==password2) {
      setErr("两次密码不一致");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      // 与后端 LoginRequest 字段一致：username / password
      const res = isRegister ? await postRegister({ username: u, password: p }) : await postLogin({ username: u, password: p });
      // 只存 access_token；api 层用 authHeaders() 拼 Authorization
      saveToken(res.access_token);
      // 清空密码，避免停留在内存/输入框
      setPassword("");
      setPassword2("");
      // 让 App 把 loggedIn 设为 true，渲染主界面
      onLoggedIn();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    // 铺满窗口：中间登录卡，底部备案号
    <div className="login-page">
      <LoginParticles />
      <div className="login-page-main">
        <form
          className="login-card"
          onSubmit={(e) => {
            e.preventDefault();
            void onSubmit();
          }}
        >
          <div className="login-card-brand">
            <NexoraLogo size="lg" />
            <h1 className="login-card-title">Nexora</h1>
          </div>
          <p className="muted login-card-hint">衡知智能体 · 登录后使用对话、知识库与设置</p>

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
            autoComplete={isRegister ? "new-password" : "current-password"}
            disabled={busy}
          />
          {isRegister && (
            <>
            <label className="muted" htmlFor="login-pass2">
              确认密码
            </label>
            <input
              id="login-pass2"
              className="login-page-input"
              type="password"
              value={password2}
              onChange={(e) => setPassword2(e.target.value)}
              autoComplete="new-password"
              disabled={busy}
            />
            </>
          )}
          {err && <div className="error-banner login-page-err">{err}</div>}

          <div className="login-actions">
            <button type="submit" className="btn primary login-page-btn" disabled={busy}>
              {busy ? (isRegister ? "注册中…" : "登录中…") : isRegister ? "注册" : "登录"}
            </button>
          </div>
          <button
            type="button"
            className="login-switch"
            disabled={busy}
            onClick={() => {
              setIsRegister((v) => !v);
              setErr(null);
              setPassword2("");
            }}
          >
            {isRegister ? "已有账号，去登录" : "没有账号，去注册"}
          </button>
        </form>
      </div>
      <IcpFooter />
    </div>
  );
}