/**
 * 报告：对 runs/cases 做聚合（业界常见：报告层不二次跑测试）
 */
import { Button, Card, Col, Empty, List, Progress, Row, Statistic, Tag } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import type { QaCase, QaRun } from "../../types/qa";
import { KIND_LABEL } from "../../qa/kindLabels";

export function QaReportPage({
  runs,
  cases,
  projectName,
}: {
  runs: QaRun[];
  cases: QaCase[];
  projectName: string;
}) {
  const passed = runs.filter((r) => r.verdict === "pass").length;
  const failed = runs.length - passed;
  const rate = runs.length ? Math.round((passed / runs.length) * 100) : 0;
  const fails = runs.filter((r) => r.verdict !== "pass");

  // 按用例类型统计数量（内容覆盖度）
  const byKind: Record<string, number> = {};
  for (const c of cases) {
    byKind[c.kind] = (byKind[c.kind] || 0) + 1;
  }
  const kindEntries = Object.entries(byKind);

  const exportMd = () => {
    const lines = [
      `# 测试报告 · ${projectName}`,
      ``,
      `- 通过率：${rate}%`,
      `- 通过 / 失败 / 总运行：${passed} / ${failed} / ${runs.length}`,
      `- 用例数：${cases.length}`,
      ``,
      `## 失败记录`,
      ...(fails.length
        ? fails.map((r) => `- [${r.verdict}] ${r.summary}`)
        : ["- （无）"]),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `qa-report-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <section className="qa-pane qa-center-page">
      <div className="qa-pane-head">
        <span>报告</span>
        <Button icon={<DownloadOutlined />} onClick={exportMd}>
          导出 Markdown
        </Button>
      </div>
      {/* Statistic 四卡 + 失败 List：保持你现有结构 */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="通过率" value={rate} suffix="%" />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="通过" value={passed} valueStyle={{ color: "#c5a572" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="失败" value={failed} valueStyle={{ color: "#b91c1c" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="用例" value={cases.length} />
          </Card>
        </Col>
      </Row>

      <Card size="small" title="用例类型覆盖" style={{ marginBottom: 16 }}>
        {kindEntries.length ? (
          kindEntries.map(([k, n]) => (
            <div key={k} style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{KIND_LABEL[k as keyof typeof KIND_LABEL] || k}</span>
                <span>{n}</span>
              </div>
              <Progress
                percent={cases.length ? Math.round((n / cases.length) * 100) : 0}
                showInfo={false}
                strokeColor="#c5a572"
                size="small"
              />
            </div>
          ))
        ) : (
          <Empty description="暂无用例" />
        )}
      </Card>

      {fails.length ? (
        <List
          header="失败记录"
          dataSource={fails}
          renderItem={(r) => (
            <List.Item>
              <Tag color="error">{r.verdict}</Tag>
              {r.summary}
            </List.Item>
          )}
        />
      ) : (
        <Empty description="暂无失败记录" />
      )}
    </section>
  );
}