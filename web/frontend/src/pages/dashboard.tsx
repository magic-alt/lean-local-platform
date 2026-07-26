import {
  Alert,
  Button,
  Card,
  Modal,
  Space,
  Statistic
} from "antd";
import {
  DatabaseOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SettingOutlined
} from "@ant-design/icons";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import { useAsyncData } from "../hooks";

export function Dashboard() {
  const navigate = useNavigate();
  const [historyOpen, setHistoryOpen] = useState(false);
  const runs = useAsyncData(api.backtests, []);
  const tasks = useAsyncData(api.tasks, []);
  const dependencyHealth = useAsyncData(api.dependencyHealth, {
    status: "ok",
    executionStatus: "ok",
    dependencies: [],
    urls: { prometheus: "", grafana: "" }
  });
  const latest = runs.data[0];
  const activeTasks = tasks.data.filter((task) => ["created", "queued", "running"].includes(task.status)).length;
  const finishedRuns = runs.data.filter((run) => ["success", "succeeded", "failed", "cancelled"].includes(run.status));
  const successfulRuns = runs.data.filter((run) => run.status === "success" || run.status === "succeeded").length;
  const successRate = finishedRuns.length ? Math.round((successfulRuns / finishedRuns.length) * 100) : 0;
  const durations = runs.data.map((run) => run.duration_seconds).filter((value): value is number => typeof value === "number");
  const averageDuration = durations.length ? Math.round(durations.reduce((sum, value) => sum + value, 0) / durations.length) : 0;
  const runsLoading = runs.loading && runs.data.length === 0;
  const tasksLoading = tasks.loading && tasks.data.length === 0;
  const dependencyChecksCompleted = dependencyHealth.data.dependencies.length > 0;
  const failedDependencies = dependencyHealth.data.dependencies.filter((item) => !item.ok);
  const failedDependencyNames = failedDependencies.map((item) => item.service).join(", ");
  const executionBlocked = dependencyChecksCompleted && dependencyHealth.data.executionStatus !== "ok";
  const operationallyDegraded = dependencyChecksCompleted
    && dependencyHealth.data.status !== "ok"
    && !executionBlocked;
  const alertChannelMissing = failedDependencies.some((item) => item.service === "external_alert_channel");

  return (
    <>
      <div className="toolbar">
        <h1 className="page-title">Dashboard</h1>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => { void runs.reload(); void tasks.reload(); }}>Refresh</Button>
          <Button icon={<DeleteOutlined />} onClick={() => setHistoryOpen(true)}>Manage Local History</Button>
        </Space>
      </div>
      {executionBlocked && (
        <Alert
          type="error"
          showIcon
          message="Platform execution is blocked or degraded"
          description={failedDependencyNames}
          action={<Button size="small" onClick={() => void dependencyHealth.reload()}>Recheck</Button>}
          style={{ marginBottom: 16 }}
        />
      )}
      {operationallyDegraded && (
        <Alert
          type="warning"
          showIcon
          message="Scheduled automation needs attention"
          description={
            alertChannelMissing
              ? "External alert delivery is not configured. Interactive backtests remain available, but unattended schedules are not operationally ready."
              : failedDependencyNames
          }
          action={<Button size="small" onClick={() => void dependencyHealth.reload()}>Recheck</Button>}
          style={{ marginBottom: 16 }}
        />
      )}
      <Card className="workflow-card" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Button type="primary" icon={<FolderOpenOutlined />} onClick={() => navigate("/projects")}>New Project</Button>
          <Button icon={<DatabaseOutlined />} onClick={() => navigate("/data")}>Fetch Data</Button>
          <Button icon={<PlayCircleOutlined />} onClick={() => navigate("/backtests?view=run")}>Run Backtest</Button>
          <Button onClick={() => navigate("/backtests?view=history")}>Backtest History</Button>
          <Button icon={<ExperimentOutlined />} onClick={() => navigate("/paper")}>Paper Replay</Button>
          <Button icon={<SettingOutlined />} onClick={() => navigate("/settings")}>Settings</Button>
        </Space>
      </Card>
      <div className="grid">
        <Card loading={runsLoading}><Statistic title="Backtests" value={runs.data.length} /></Card>
        <Card loading={tasksLoading}><Statistic title="Active Tasks" value={activeTasks} /></Card>
        <Card loading={runsLoading}><Statistic title="Success Rate" value={successRate} suffix="%" /></Card>
        <Card loading={runsLoading}><Statistic title="Average Duration" value={averageDuration} suffix="s" /></Card>
      </div>
      <div className="grid">
        <Card loading={runsLoading}><Statistic title="Latest Net Profit" value={latest?.statistics?.["Net Profit"] ?? "N/A"} /></Card>
        <Card loading={runsLoading}><Statistic title="Latest Sharpe" value={latest?.statistics?.["Sharpe Ratio"] ?? "N/A"} /></Card>
        <Card loading={runsLoading}><Statistic title="Latest Status" value={latest?.status ?? "N/A"} /></Card>
        <Card loading={runsLoading}><Statistic title="Latest Symbol" value={latest?.symbol ?? "N/A"} /></Card>
      </div>
      <Modal
        title="Manage local history"
        open={historyOpen}
        onCancel={() => setHistoryOpen(false)}
        footer={<Button onClick={() => setHistoryOpen(false)}>Close</Button>}
      >
        <Alert
          type="warning"
          showIcon
          message="There is no global one-click delete."
          description="Review a resource page, then delete one item or an explicit selection. Running work must be cancelled or stopped first. Market data is never included."
          style={{ marginBottom: 16 }}
        />
        <div className="history-resource-list">
          {[
            { label: "Backtests", count: runs.data.length, route: "/backtests?view=history" },
            { label: "Tasks", count: tasks.data.length, route: "/tasks" },
            { label: "Optimizations", route: "/optimization" },
            { label: "Research sessions", route: "/research" },
            { label: "Reports", route: "/reports" },
            { label: "Paper sessions", route: "/paper" },
            { label: "Projects", route: "/projects" },
          ].map((item) => (
            <div className="history-resource-row" key={item.route}>
              <div><strong>{item.label}</strong>{item.count != null && <span className="muted"> · {item.count} local records</span>}</div>
              <Button size="small" onClick={() => { setHistoryOpen(false); navigate(item.route); }}>Review</Button>
            </div>
          ))}
        </div>
      </Modal>
    </>
  );
}
