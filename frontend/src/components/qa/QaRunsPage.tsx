import { Button, Empty, List, Tag, Typography } from "antd";
import { PlayCircleOutlined } from "@ant-design/icons";
import type { QaRun } from "../../types/qa";

export function QaRunsPage({
  runs,
  onSmoke,
  busy,
}: {
  runs: QaRun[];
  onSmoke: () => void;
  busy: boolean;
}) {
  return (
    <section className="qa-pane qa-center-page">
      <div className="qa-pane-head">
        <span>执行记录</span>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          loading={busy}
          onClick={onSmoke}
        >
          执行冒烟
        </Button>
      </div>
      {runs.length ? (
        <List
          dataSource={runs}
          renderItem={(r) => (
            <List.Item>
              <List.Item.Meta
                avatar={
                  <Tag color={r.verdict === "pass" ? "success" : "error"}>
                    {r.verdict}
                  </Tag>
                }
                title={<Typography.Text>{r.summary}</Typography.Text>}
                description={
                  <Typography.Text type="secondary">{r.id}</Typography.Text>
                }
              />
            </List.Item>
          )}
        />
      ) : (
        <Empty description="还没有执行。冒烟结果会出现在这里。" />
      )}
    </section>
  );
}
