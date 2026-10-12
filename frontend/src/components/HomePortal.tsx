// ============================================================================
// HomePortal.tsx
// - 左侧：领域目录（收藏/最近先静态）
// - 主区：筛选 pills + 双列卡片
// - ready → onEnter(workspace)；soon → Toast「即将开放」
// ============================================================================

import { useMemo, useState } from "react";
import { Button, Input, message } from "antd";
import {
  AppstoreOutlined,
  BarChartOutlined,
  BookOutlined,
  ClockCircleOutlined,
  CloudServerOutlined,
  CodeOutlined,
  EditOutlined,
  ExperimentOutlined,
  MessageOutlined,
  RiseOutlined,
  SafetyOutlined,
  SearchOutlined,
  StarOutlined,
} from "@ant-design/icons";
import { NexoraLogo } from "./NexoraLogo";
import {
  DOMAINS,
  DOMAIN_FILTERS,
  DOMAIN_GROUPS,
  filterDomains,
  type DomainFilterId,
  type DomainGroupId,
  type DomainItem,
} from "../portal/domains";
import "../styles/portal.css";

type Props = {
  /** 进入已上线工作台 */
  onEnter: (workspace: "chat" | "qa") => void;
  /** 顶栏「新建对话」：进 chat 并开新会话 */
  onNewChat?: () => void;
  /** 侧栏底部用户名 */
  userLabel?: string;
};

type SideNav = "all" | "fav" | "recent" | DomainGroupId;

/** 按领域 id 选图标 */
function domainIcon(id: string) {
  switch (id) {
    case "chat":
      return <MessageOutlined />;
    case "qa":
      return <ExperimentOutlined />;
    case "code-review":
      return <CodeOutlined />;
    case "ops":
      return <CloudServerOutlined />;
    case "data":
      return <BarChartOutlined />;
    case "security":
      return <SafetyOutlined />;
    case "kb":
      return <BookOutlined />;
    case "content":
      return <EditOutlined />;
    case "growth":
      return <RiseOutlined />;
    default:
      return <AppstoreOutlined />;
  }
}

export function HomePortal({
  onEnter,
  onNewChat,
  userLabel = "User",
}: Props) {
  const [filter, setFilter] = useState<DomainFilterId>("all");
  const [nav, setNav] = useState<SideNav>("all");
  const [q, setQ] = useState("");

  const visible = useMemo(() => {
    // 收藏 / 最近：第一版无数据，展示空列表
    if (nav === "fav" || nav === "recent") return [] as DomainItem[];

    let list = filterDomains(filter);
    if (nav === "rd" || nav === "ops" || nav === "biz") {
      list = list.filter((d) => d.group === nav);
    }
    const key = q.trim().toLowerCase();
    if (!key) return list;
    return list.filter(
      (d) =>
        d.name.toLowerCase().includes(key) ||
        d.subtitle.toLowerCase().includes(key) ||
        d.tags.some((t) => t.toLowerCase().includes(key)),
    );
  }, [filter, nav, q]);

  const onCardClick = (d: DomainItem) => {
    if (d.status === "ready" && d.workspace) {
      onEnter(d.workspace);
      return;
    }
    message.info(`「${d.name}」即将开放，敬请期待`);
  };

  return (
    <div className="portal">
      <header className="portal-top">
        <Input
          className="portal-search"
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索领域或工具…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />

        <div className="portal-top-actions">
          {onNewChat ? (
            <Button
              className="portal-btn-primary"
              type="primary"
              onClick={onNewChat}
            >
              + 新建对话
            </Button>
          ) : null}
        </div>
      </header>

      <div className="portal-body">
        <aside className="portal-side">
          <button
            type="button"
            className={`portal-nav-item${nav === "all" ? " active" : ""}`}
            onClick={() => {
              setNav("all");
              setFilter("all");
            }}
          >
            <AppstoreOutlined />
            <span>全部领域</span>
            <em>{DOMAINS.length}</em>
          </button>

          <button
            type="button"
            className={`portal-nav-item${nav === "fav" ? " active" : ""}`}
            onClick={() => setNav("fav")}
          >
            <StarOutlined />
            <span>我的收藏</span>
            <em>0</em>
          </button>

          <button
            type="button"
            className={`portal-nav-item${nav === "recent" ? " active" : ""}`}
            onClick={() => setNav("recent")}
          >
            <ClockCircleOutlined />
            <span>最近使用</span>
          </button>

          {DOMAIN_GROUPS.map((g) => (
            <div key={g.id} className="portal-side-group">
              <div className="portal-side-label">{g.label}</div>
              {DOMAINS.filter((d) => d.group === g.id).map((d) => (
                <button
                  key={d.id}
                  type="button"
                  className="portal-nav-item sub"
                  onClick={() => onCardClick(d)}
                  title={
                    d.status === "soon" ? "即将开放" : `进入${d.name}`
                  }
                >
                  {domainIcon(d.id)}
                  <span>{d.name}</span>
                  {typeof d.badge === "number" ? <em>{d.badge}</em> : null}
                </button>
              ))}
            </div>
          ))}

          <div className="portal-user">
            <div className="portal-avatar">
              {userLabel.slice(0, 1).toUpperCase()}
            </div>
            <div className="portal-user-meta">
              <strong>{userLabel}</strong>
              <span>Nexora · Admin</span>
            </div>
          </div>
        </aside>

        <main className="portal-main">
          <h1 className="portal-h1">选择一个领域，进入对应工作台</h1>
          <p className="portal-lead">
            每个领域由专属 Agent 驱动；已上线可直接进入，其余敬请期待。
          </p>

          <div className="portal-pills">
            {DOMAIN_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                className={`portal-pill${filter === f.id ? " active" : ""}`}
                onClick={() => {
                  setFilter(f.id);
                  // 点筛选时回到「全部领域」侧栏态，避免和分组 nav 打架
                  if (nav === "rd" || nav === "ops" || nav === "biz") {
                    setNav("all");
                  }
                }}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="portal-grid">
            {visible.map((d) => (
              <article
                key={d.id}
                className={`portal-card${d.status === "soon" ? " soon" : ""}`}
                onClick={() => onCardClick(d)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onCardClick(d);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <div className="portal-card-head">
                  <div className="portal-card-icon">{domainIcon(d.id)}</div>
                  <div className="portal-card-titles">
                    <h2>{d.name}</h2>
                    <p>{d.subtitle}</p>
                  </div>
                </div>
                <p className="portal-card-desc">{d.description}</p>
                <div className="portal-card-foot">
                  <div className="portal-tags">
                    {d.tags.map((t) => (
                      <span key={t} className="portal-tag">
                        {t}
                      </span>
                    ))}
                  </div>
                  {d.status === "ready" ? (
                    <span className="portal-enter">进入 →</span>
                  ) : (
                    <span className="portal-soon">即将开放</span>
                  )}
                </div>
              </article>
            ))}
          </div>

          {visible.length === 0 ? (
            <p className="portal-empty">
              {nav === "fav"
                ? "暂无收藏领域。"
                : nav === "recent"
                  ? "暂无最近使用记录。"
                  : "没有匹配的领域，试试其它筛选或关键字。"}
            </p>
          ) : null}

        </main>
      </div>
    </div>
  );
}
