import { Button, Drawer, Layout, Menu, Result, Space, Spin, Tag } from "antd";
import {
  AppstoreOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  BulbOutlined,
  ReadOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  SlidersOutlined,
  UnorderedListOutlined,
  MenuOutlined
} from "@ant-design/icons";
import { HashRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import { lazy, Suspense, useMemo, useState } from "react";

const loadDashboardPage = () => import("./pages/dashboard");
const loadCorePages = () => import("./pages/core");
const loadDocsPages = () => import("./pages/docs");
const loadInsightsPages = () => import("./pages/insights");
const loadOperationsPages = () => import("./pages/operations");
const loadResearchPages = () => import("./pages/research");

const Dashboard = lazy(() => loadDashboardPage().then((module) => ({ default: module.Dashboard })));
const BacktestsPage = lazy(() => loadCorePages().then((module) => ({ default: module.BacktestsPage })));
const DataPage = lazy(() => loadCorePages().then((module) => ({ default: module.DataPage })));
const OptimizationPage = lazy(() => loadCorePages().then((module) => ({ default: module.OptimizationPage })));
const ProjectsPage = lazy(() => loadCorePages().then((module) => ({ default: module.ProjectsPage })));
const RunDetailPage = lazy(() => loadCorePages().then((module) => ({ default: module.RunDetailPage })));
const DocsPage = lazy(() => loadDocsPages().then((module) => ({ default: module.DocsPage })));
const InsightsPage = lazy(() => loadInsightsPages().then((module) => ({ default: module.InsightsPage })));
const MonitoringPage = lazy(() => loadOperationsPages().then((module) => ({ default: module.MonitoringPage })));
const PaperPage = lazy(() => loadOperationsPages().then((module) => ({ default: module.PaperPage })));
const ReportsPage = lazy(() => loadOperationsPages().then((module) => ({ default: module.ReportsPage })));
const SettingsPage = lazy(() => loadOperationsPages().then((module) => ({ default: module.SettingsPage })));
const TasksPage = lazy(() => loadOperationsPages().then((module) => ({ default: module.TasksPage })));
const ResearchPage = lazy(() => loadResearchPages().then((module) => ({ default: module.ResearchPage })));

const { Content, Header, Sider } = Layout;

function navigationLink(to: string, label: string, preload: () => Promise<unknown>) {
  return (
    <Link
      to={to}
      onFocus={() => { void preload(); }}
      onMouseEnter={() => { void preload(); }}
    >
      {label}
    </Link>
  );
}

function AppShell() {
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const menuItems = useMemo(() => [
    { key: "/", icon: <AppstoreOutlined />, label: navigationLink("/", "Dashboard", loadDashboardPage) },
    { key: "/projects", icon: <FolderOpenOutlined />, label: navigationLink("/projects", "Projects", loadCorePages) },
    { key: "/data", icon: <DatabaseOutlined />, label: navigationLink("/data", "Data", loadCorePages) },
    { key: "/backtests", icon: <PlayCircleOutlined />, label: navigationLink("/backtests", "Backtests", loadCorePages) },
    { key: "/optimization", icon: <SlidersOutlined />, label: navigationLink("/optimization", "Optimization", loadCorePages) },
    { key: "/paper", icon: <ExperimentOutlined />, label: navigationLink("/paper", "Paper", loadOperationsPages) },
    { key: "/research", icon: <ExperimentOutlined />, label: navigationLink("/research", "Research", loadResearchPages) },
    { key: "/docs", icon: <ReadOutlined />, label: navigationLink("/docs", "文档", loadDocsPages) },
    { key: "/reports", icon: <FileTextOutlined />, label: navigationLink("/reports", "Reports", loadOperationsPages) },
    { key: "/insights", icon: <BulbOutlined />, label: navigationLink("/insights", "Insights", loadInsightsPages) },
    { key: "/tasks", icon: <UnorderedListOutlined />, label: navigationLink("/tasks", "Tasks", loadOperationsPages) },
    { key: "/monitoring", icon: <DashboardOutlined />, label: navigationLink("/monitoring", "Monitoring", loadOperationsPages) },
    { key: "/settings", icon: <SettingOutlined />, label: navigationLink("/settings", "Settings", loadOperationsPages) }
  ], []);
  return (
    <Layout className="app-layout">
      <Sider className="app-sidebar" breakpoint="lg" collapsedWidth="0"><div className="app-logo">LEAN Local</div><Menu theme="dark" mode="inline" items={menuItems} /></Sider>
      <Layout>
        <Header className="app-header">
          <Space className="app-header__content">
            <Button
              className="app-mobile-menu-button"
              aria-label="Open navigation"
              icon={<MenuOutlined />}
              onClick={() => setMobileNavigationOpen(true)}
            />
            <strong>LEAN Local Workbench</strong>
            <span className="app-header__badges"><Tag color="blue">docker</Tag><Tag color="green">multi-asset</Tag><Tag color="purple">paper</Tag></span>
          </Space>
        </Header>
        <Content className="app-content">
          <Suspense fallback={<div className="route-loading"><Spin size="large" /></div>}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/projects" element={<ProjectsPage />} />
              <Route path="/data" element={<DataPage />} />
              <Route path="/backtests" element={<BacktestsPage />} />
              <Route path="/compare" element={<Navigate to="/optimization" replace />} />
              <Route path="/runs/:id" element={<RunDetailPage />} />
              <Route path="/optimization" element={<OptimizationPage />} />
              <Route path="/paper" element={<PaperPage />} />
              <Route path="/research" element={<ResearchPage />} />
              <Route path="/docs" element={<Navigate to="/docs/index" replace />} />
              <Route path="/docs/:slug" element={<DocsPage />} />
              <Route path="/ashare-research" element={<Navigate to="/research" replace />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/insights" element={<InsightsPage />} />
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
          </Suspense>
        </Content>
      </Layout>
      <Drawer
        className="app-mobile-navigation"
        title="LEAN Local"
        placement="left"
        open={mobileNavigationOpen}
        onClose={() => setMobileNavigationOpen(false)}
      >
        <Menu mode="inline" items={menuItems} onClick={() => setMobileNavigationOpen(false)} />
      </Drawer>
    </Layout>
  );
}

export default function App() {
  return <HashRouter><AppShell /></HashRouter>;
}
