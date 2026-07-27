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
import { HashRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { lazy, Suspense, useMemo, useState } from "react";

const loadDashboardPage = () => import("./pages/dashboard");
const loadCorePages = () => import("./pages/core");
const loadDocsPages = () => import("./pages/docs");
const loadInsightsPages = () => import("./pages/insights");
const loadOperationsPages = () => import("./pages/operations");
const loadPaperAccountPages = () => import("./pages/paper-accounts");
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
const PaperAccountsPage = lazy(() => loadPaperAccountPages().then((module) => ({ default: module.PaperAccountsPage })));
const PaperAccountDetailPage = lazy(() => loadPaperAccountPages().then((module) => ({ default: module.PaperAccountDetailPage })));
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
  const location = useLocation();
  const selectedMenuKey = useMemo(() => {
    const pathname = location.pathname;
    if (pathname.startsWith("/paper")) return "/paper";
    if (pathname.startsWith("/runs/") || pathname.startsWith("/backtests")) return "/backtests";
    if (pathname.startsWith("/docs")) return "/docs";
    if (pathname.startsWith("/optimization") || pathname.startsWith("/compare")) return "/optimization";
    if (pathname.startsWith("/research") || pathname.startsWith("/ashare-research")) return "/research";
    const directMatch = [
      "/projects",
      "/data",
      "/reports",
      "/insights",
      "/tasks",
      "/monitoring",
      "/settings"
    ].find((key) => pathname === key || pathname.startsWith(`${key}/`));
    return pathname === "/" ? "/" : directMatch;
  }, [location.pathname]);
  const menuItems = useMemo(() => [
    {
      type: "group" as const,
      label: "研究",
      children: [
        { key: "/", icon: <AppstoreOutlined />, label: navigationLink("/", "概览", loadDashboardPage) },
        { key: "/projects", icon: <FolderOpenOutlined />, label: navigationLink("/projects", "项目", loadCorePages) },
        { key: "/data", icon: <DatabaseOutlined />, label: navigationLink("/data", "数据", loadCorePages) },
        { key: "/research", icon: <ExperimentOutlined />, label: navigationLink("/research", "研究", loadResearchPages) }
      ]
    },
    {
      type: "group" as const,
      label: "回测",
      children: [
        { key: "/backtests", icon: <PlayCircleOutlined />, label: navigationLink("/backtests", "回测", loadCorePages) },
        { key: "/optimization", icon: <SlidersOutlined />, label: navigationLink("/optimization", "优化", loadCorePages) },
        { key: "/reports", icon: <FileTextOutlined />, label: navigationLink("/reports", "报告", loadOperationsPages) }
      ]
    },
    {
      type: "group" as const,
      label: "交易",
      children: [
        { key: "/paper", icon: <ExperimentOutlined />, label: navigationLink("/paper", "模拟交易", loadPaperAccountPages) },
        { key: "/insights", icon: <BulbOutlined />, label: navigationLink("/insights", "洞察", loadInsightsPages) }
      ]
    },
    {
      type: "group" as const,
      label: "系统",
      children: [
        { key: "/tasks", icon: <UnorderedListOutlined />, label: navigationLink("/tasks", "任务", loadOperationsPages) },
        { key: "/monitoring", icon: <DashboardOutlined />, label: navigationLink("/monitoring", "监控", loadOperationsPages) },
        { key: "/docs", icon: <ReadOutlined />, label: navigationLink("/docs", "文档", loadDocsPages) },
        { key: "/settings", icon: <SettingOutlined />, label: navigationLink("/settings", "设置", loadOperationsPages) }
      ]
    }
  ], []);
  return (
    <Layout className="app-layout">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <Sider className="app-sidebar" breakpoint="lg" collapsedWidth="0">
        <div className="app-logo">LEAN Local</div>
        <nav aria-label="主导航">
          <Menu theme="dark" mode="inline" items={menuItems} selectedKeys={selectedMenuKey ? [selectedMenuKey] : []} />
        </nav>
      </Sider>
      <Layout>
        <Header className="app-header">
          <Space className="app-header__content">
            <Button
              className="app-mobile-menu-button"
              aria-label="打开导航"
              icon={<MenuOutlined />}
              onClick={() => setMobileNavigationOpen(true)}
            />
            <strong>LEAN Local Workbench</strong>
            <span className="app-header__badges"><Tag color="blue">docker</Tag><Tag color="green">multi-asset</Tag><Tag color="purple">paper</Tag></span>
          </Space>
        </Header>
        <Content id="main-content" className="app-content" role="main" tabIndex={-1}>
          <Suspense fallback={<div className="route-loading"><Spin size="large" /></div>}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/projects" element={<ProjectsPage />} />
              <Route path="/data" element={<DataPage />} />
              <Route path="/backtests" element={<BacktestsPage />} />
              <Route path="/compare" element={<Navigate to="/optimization" replace />} />
              <Route path="/runs/:id" element={<RunDetailPage />} />
              <Route path="/optimization" element={<OptimizationPage />} />
              <Route path="/paper" element={<PaperAccountsPage />} />
              <Route path="/paper/accounts/:id" element={<PaperAccountDetailPage />} />
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
        <nav aria-label="移动端导航">
          <Menu
            mode="inline"
            items={menuItems}
            selectedKeys={selectedMenuKey ? [selectedMenuKey] : []}
            onClick={() => setMobileNavigationOpen(false)}
          />
        </nav>
      </Drawer>
    </Layout>
  );
}

export default function App() {
  return <HashRouter><AppShell /></HashRouter>;
}
