import { Card, Col, Empty, List, Row, Statistic, Tag } from "antd";
import type { QaCase, QaRun } from "../../types/qa";

export function QaReportPage({
  runs,
  cases,
}: {
  runs: QaRun[];
  cases: QaCase[];
}) {
  const passed = runs.filter((r) => r.verdict === "pass").length;
  const failed = runs.length - passed;
  const rate = runs.length ? Math.round((passed / runs.length) * 100) : 0;
  const fails = runs.filter((r) => r.verdict !== "pass");

  return (
    <section className="qa-pane qa-center-page">
      <div className="qa-pane-head">报告</div>
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="通过率" value={rate} suffix="%" />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="通过" value={passed} valueStyle={{ color: "#0f766e" }} />
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
