/**
 * QaCaseTree.tsx
 * 左栏：搜索 + 树（编号 / 类型徽标 / 状态点 / 删除 / 展开收起）
 */
import { useEffect, useMemo, useState } from "react";
import { Button, Input, Tag, Typography } from "antd";
import {
  CaretDownOutlined,
  CaretRightOutlined,
  DeleteOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import type { QaCase } from "../../types/qa";
import { KIND_LABEL } from "../../qa/kindLabels";

type Props = {
  cases: QaCase[];
  selectedId: string | null;
  query: string;
  onQuery: (q: string) => void;
  onSelect: (id: string) => void;
  onGenerate: () => void;
  onDelete: (id: string) => void;
  busy: boolean;
};

export function QaCaseTree({
  cases,
  selectedId,
  query,
  onQuery,
  onSelect,
  onGenerate,
  onDelete,
  busy,
}: Props) {
  const q = query.trim().toLowerCase();
  const roots = useMemo(() => cases.filter((c) => !c.parentId), [cases]);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const childrenOf = (id: string) => cases.filter((c) => c.parentId === id);

  const hit = (c: QaCase) =>
    c.title.toLowerCase().includes(q) ||
    c.code.toLowerCase().includes(q) ||
    KIND_LABEL[c.kind].includes(query.trim());

  const rootIds = useMemo(() => roots.map((r) => r.id).join(","), [roots]);

  const visibleRoot = (root: QaCase) => {
    if (!q) return true;
    return hit(root) || childrenOf(root.id).some(hit);
  };

  useEffect(() => {
    setExpanded((prev) => {
      const next = new Set(prev);
      for (const id of rootIds.split(",")) {
        if (id) next.add(id);
      }
      return next;
    });
  }, [rootIds]);

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <aside className="qa-pane qa-pane-tree">
      <div className="qa-pane-head">
        <span>测试内容</span>
        <Button
          type="link"
          size="small"
          icon={<PlusOutlined />}
          disabled={busy}
          onClick={onGenerate}
        >
          生成
        </Button>
      </div>

      <Input.Search
        allowClear
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        placeholder="搜索编号 / 标题 / 类型"
        style={{ marginBottom: 8 }}
      />

      <ul className="qa-tree">
        {roots.filter(visibleRoot).map((root) => {
          const open = expanded.has(root.id) || Boolean(q);
          const kids = childrenOf(root.id);
          return (
            <li key={root.id} className="qa-tree-block">
              <div
                className={
                  root.id === selectedId
                    ? "qa-tree-line is-active"
                    : "qa-tree-line"
                }
              >
                {kids.length > 0 ? (
                  <Button
                    type="text"
                    size="small"
                    className="qa-tree-toggle"
                    aria-expanded={open}
                    icon={open ? <CaretDownOutlined /> : <CaretRightOutlined />}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleExpand(root.id);
                    }}
                  />
                ) : (
                  <span className="qa-tree-toggle-spacer" />
                )}
                <button
                  type="button"
                  className="qa-tree-row"
                  onClick={() => onSelect(root.id)}
                >
                  <span className="qa-dot qa-dot-root" />
                  <span className="qa-tree-code">{root.code}</span>
                  <span className="qa-tree-title">{root.title}</span>
                  <span
                    className={`qa-status-dot is-${root.status}`}
                    title={root.status}
                  />
                </button>
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  disabled={busy}
                  title="删除需求包及其子项"
                  onClick={() => onDelete(root.id)}
                />
              </div>

              {open && (
                <ul className="qa-tree-children">
                  {kids
                    .filter((ch) => !q || hit(ch))
                    .map((ch) => (
                      <li key={ch.id}>
                        <div
                          className={
                            ch.id === selectedId
                              ? "qa-tree-line is-active"
                              : "qa-tree-line"
                          }
                        >
                          <button
                            type="button"
                            className="qa-tree-row"
                            onClick={() => onSelect(ch.id)}
                          >
                            <Tag color="processing" className="qa-kind-tag">
                              {KIND_LABEL[ch.kind]}
                            </Tag>
                            <span className="qa-tree-code">{ch.code}</span>
                            <span className="qa-tree-title">{ch.title}</span>
                            <span
                              className={`qa-status-dot is-${ch.status}`}
                              title={ch.status}
                            />
                          </button>
                          <Button
                            type="text"
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            disabled={busy}
                            title="删除此测试项"
                            onClick={() => onDelete(ch.id)}
                          />
                        </div>
                      </li>
                    ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>

      {!cases.length ? (
        <Typography.Paragraph type="secondary" className="qa-empty">
          暂无测试项，点击「生成」创建一批演示用例
        </Typography.Paragraph>
      ) : null}
    </aside>
  );
}
