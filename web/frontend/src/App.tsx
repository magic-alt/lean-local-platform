import { Button, Layout, Menu, Result, Space, Tag } from "antd";
import {
  AppstoreOutlined,
  CodeOutlined,
  BarChartOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  SlidersOutlined,
  UnorderedListOutlined
} from "@ant-design/icons";
import { HashRouter, Link, Route, Routes } from "react-router-dom";
import { useMemo } from "react";

import {
  BacktestsPage,
  ComparePage,
  Dashboard,
  DataPage,
  MonitoringPage,
  ObjectStorePage,
  OptimizationPage,
  P2ResearchPage,
  PaperPage,
  ProjectsPage,
  ProjectWorkspacePage,
  ReportsPage,
  ResearchPage,
  RunDetailPage,
  SettingsPage,
  TasksPage
} from "./pages";

const { Content, Header, Sider } = Layout;

function AppShell() {
  const menuItems = useMemo(() => [
    { key: "/", icon: <AppstoreOutlined />, label: <Link to="/">Dashboard</Link> },
    { key: "/workspace", icon: <CodeOutlined />, label: <Link to="/workspace">Workspace</Link> },
    { key: "/projects", icon: <FolderOpenOutlined />, label: <Link to="/projects">Projects</Link> },
    { key: "/data", icon: <DatabaseOutlined />, label: <Link to="/data">Data</Link> },
    { key: "/backtests", icon: <PlayCircleOutlined />, label: <Link to="/backtests">Backtests</Link> },
    { key: "/compare", icon: <BarChartOutlined />, label: <Link to="/compare">Compare</Link> },
    { key: "/optimization", icon: <SlidersOutlined />, label: <Link to="/optimization">Optimization</Link> },
    { key: "/paper", icon: <ExperimentOutlined />, label: <Link to="/paper">Paper</Link> },
    { key: "/research", icon: <ExperimentOutlined />, label: <Link to="/research">Research</Link> },
    { key: "/ashare-research", icon: <DatabaseOutlined />, label: <Link to="/ashare-research">A-Share Research</Link> },
    { key: "/reports", icon: <FileTextOutlined />, label: <Link to="/reports">Reports</Link> },
    { key: "/object-store", icon: <DatabaseOutlined />, label: <Link to="/object-store">Object Store</Link> },
    { key: "/tasks", icon: <UnorderedListOutlined />, label: <Link to="/tasks">Tasks</Link> },
    { key: "/monitoring", icon: <DashboardOutlined />, label: <Link to="/monitoring">Monitoring</Link> },
    { key: "/settings", icon: <SettingOutlined />, label: <Link to="/settings">Settings</Link> }
  ], []);
  return (
    <Layout className="app-layout">
      <Sider breakpoint="lg" collapsedWidth="0"><div className="app-logo">LEAN Local</div><Menu theme="dark" mode="inline" items={menuItems} /></Sider>
      <Layout>
        <Header className="app-header"><Space><strong>LEAN Local Workbench</strong><Tag color="blue">docker</Tag><Tag color="green">multi-asset</Tag><Tag color="purple">paper</Tag></Space></Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/workspace" element={<ProjectWorkspacePage />} />
            <Route path="/workspace/:projectId" element={<ProjectWorkspacePage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/data" element={<DataPage />} />
            <Route path="/backtests" element={<BacktestsPage />} />
            <Route path="/compare" element={<ComparePage />} />
            <Route path="/runs/:id" element={<RunDetailPage />} />
            <Route path="/optimization" element={<OptimizationPage />} />
            <Route path="/paper" element={<PaperPage />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/ashare-research" element={<P2ResearchPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/object-store" element={<ObjectStorePage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/monitoring" element={<MonitoringPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route
              path="*"
              element={(
                <Result
                  status="404"
                  title="Page Not Found"
                  subTitle="The requested LEAN Local page does not exist."
                  extra={<Button type="primary"><Link to="/">Back to Dashboard</Link></Button>}
                />
              )}
            />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  return <HashRouter><AppShell /></HashRouter>;
}
