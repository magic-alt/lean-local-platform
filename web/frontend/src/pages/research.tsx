import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Row,
  Space,
  Steps,
  Table,
  Tag,
  Typography
} from "antd";
import {
  CheckCircleOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  PlayCircleOutlined,
  ReloadOutlined
} from "@ant-design/icons";
import { Link } from "react-router-dom";

import {
  researchCapabilities,
  researchImports,
  type MarketLocalizationCapability,
  type ResearchImportPreview,
  type ResearchPlatformCapabilities
} from "../api/research";
import { useAsyncData } from "../hooks";

const { Paragraph, Text, Title } = Typography;

const fallbackCapabilities: ResearchPlatformCapabilities = {
  schemaVersion: "1.0",
  engine: {
    engine: "QuantConnect LEAN",
    upstreamRepository: "QuantConnect/Lean",
    authority: "upstream",
    integrationMode: "delegate",
    coreForkPolicy: "no_local_core_fork",
    capabilityPolicy: "preserve_upstream_engine_capabilities",
    uiPolicy: "curated_control_plane_not_feature_reimplementation"
  },
  localization: {
    priority: ["china", "hongkong"],
    strategy: "adapter_layer_over_upstream_lean",
    markets: [],
    productionCertificationSource: "docs/release-status.md"
  },
  research: {
    owner: "qlib-platform",
    localExecutionEnabled: false,
    localNotebookWorkspaceEnabled: false,
    artifactContractVersion: "2.0",
    importType: "QLIB_RESEARCH_BUNDLE",
    handoff: {},
    platformResponsibilities: [],
    externalResponsibilities: []
  }
};

const emptyImports = { items: [] as ResearchImportPreview[], count: 0, limit: 20, offset: 0 };
const loadImports = () => researchImports(20, 0);

function localizationStatus(item: MarketLocalizationCapability) {
  if (item.implementation_status === "implemented") return <Tag color="green">implemented</Tag>;
  if (item.implementation_status === "partial") return <Tag color="orange">partial</Tag>;
  return <Tag color="blue">{item.implementation_status}</Tag>;
}

export function ResearchPage() {
  const capabilities = useAsyncData(researchCapabilities, fallbackCapabilities, false, "research-capabilities");
  const imports = useAsyncData(loadImports, emptyImports, false, "research-imports");
  const refresh = () => Promise.all([capabilities.reload(), imports.reload()]);

  return (
    <Space orientation="vertical" size={20} style={{ width: "100%" }}>
      <div>
        <Space align="center" wrap>
          <Title level={2} style={{ margin: 0 }}>研究交付与结果预览</Title>
          <Tag color="blue">Artifact Contract v2</Tag>
          <Tag>qlib-platform owned</Tag>
          <Tag color="green">LEAN upstream execution</Tag>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, maxWidth: 980 }}>
          本页不执行特征、因子、模型训练或 Notebook。研究由 qlib-platform 完成；本平台保留不可变产物导入、
          lineage/hash 校验、结果预览，以及由官方 QuantConnect LEAN 执行的权威回测验证。
        </Paragraph>
      </div>

      {(capabilities.error || imports.error) && <Alert
        type="warning"
        showIcon
        message="研究互操作状态暂时不可完整读取"
        description={[capabilities.error?.message, imports.error?.message].filter(Boolean).join("；")}
      />}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="官方 LEAN 继承边界">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="执行引擎">{capabilities.data.engine.engine}</Descriptions.Item>
              <Descriptions.Item label="上游仓库">{capabilities.data.engine.upstreamRepository}</Descriptions.Item>
              <Descriptions.Item label="集成方式">{capabilities.data.engine.integrationMode}</Descriptions.Item>
              <Descriptions.Item label="核心策略">{capabilities.data.engine.coreForkPolicy}</Descriptions.Item>
              <Descriptions.Item label="能力策略">{capabilities.data.engine.capabilityPolicy}</Descriptions.Item>
            </Descriptions>
            <Alert
              style={{ marginTop: 12 }}
              type="info"
              showIcon
              message="Web 是控制面，不是 LEAN 功能替代实现"
              description="本地化代码只负责市场数据、交易所语义、broker adapter、编排和验证；算法、订单、组合与执行引擎继续由官方 LEAN 提供。"
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="Research Plane 边界">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Owner">{capabilities.data.research.owner}</Descriptions.Item>
              <Descriptions.Item label="本地研究执行">{capabilities.data.research.localExecutionEnabled ? "启用" : "关闭"}</Descriptions.Item>
              <Descriptions.Item label="Notebook Workspace">{capabilities.data.research.localNotebookWorkspaceEnabled ? "启用" : "关闭"}</Descriptions.Item>
              <Descriptions.Item label="交付协议">Artifact Contract v{capabilities.data.research.artifactContractVersion}</Descriptions.Item>
              <Descriptions.Item label="导入类型">{capabilities.data.research.importType}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      <Card title="A股 / 港股本地化状态">
        <Table<MarketLocalizationCapability>
          rowKey="key"
          size="small"
          pagination={false}
          dataSource={capabilities.data.localization.markets.filter((item) => ["china", "hongkong"].includes(item.key))}
          columns={[
            { title: "市场", render: (_, item) => <><strong>{item.name}</strong><div className="muted">{item.key}</div></> },
            { title: "状态", render: (_, item) => localizationStatus(item), width: 120 },
            { title: "执行范围", dataIndex: "execution_scope", width: 150 },
            { title: "币种 / 时区", render: (_, item) => `${item.currency} / ${item.timezone}`, width: 210 },
            { title: "交易时段", render: (_, item) => item.sessions.map((session) => session.join("–")).join("；") },
            { title: "手数规则", dataIndex: "lot_size_policy" },
            { title: "最小价位规则", dataIndex: "tick_size_policy" },
            { title: "逐证券属性", render: (_, item) => item.symbol_properties_required ? <Tag color="orange">required</Tag> : <Tag>optional</Tag>, width: 120 }
          ]}
        />
        <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          港股当前明确为 partial / preview-only：只有符号与数据布局适配并不等于可执行认证；逐证券 board lot、价格档位、费用、交易日历及执行证据完成前不会宣称为生产可用。
        </Paragraph>
      </Card>

      <Card
        title={`最近导入的 qlib-platform 研究结果（${imports.data.count}）`}
        extra={<Button icon={<ReloadOutlined />} loading={capabilities.loading || imports.loading} onClick={() => void refresh()}>刷新</Button>}
      >
        <Table<ResearchImportPreview>
          rowKey="id"
          size="small"
          loading={imports.loading}
          dataSource={imports.data.items}
          pagination={false}
          locale={{ emptyText: "尚未导入 Artifact Contract v2 研究结果" }}
          columns={[
            { title: "研究", render: (_, item) => <><strong>{item.name || item.externalRunId || item.id}</strong><div className="muted">{item.externalRunId || item.researchRunId}</div></> },
            { title: "市场", render: (_, item) => <Tag>{item.market || "china"}</Tag>, width: 90 },
            { title: "DataRelease", render: (_, item) => <Text code>{item.dataReleaseId ? item.dataReleaseId.slice(0, 18) : "-"}</Text> },
            { title: "TargetPortfolio", render: (_, item) => item.latestSignal
              ? <><div>{item.latestSignal.targetCount ?? 0} targets</div><div className="muted">trade {item.latestSignal.tradeDate || "-"}</div></>
              : "-" },
            { title: "LEAN 验证", render: (_, item) => item.leanValidation
              ? <Tag color="green">{item.leanValidation.status || "validated"}</Tag>
              : <Tag color="orange">pending</Tag>, width: 130 },
            { title: "导入时间", dataIndex: "createdAt", width: 190 }
          ]}
        />
      </Card>

      <Card title="标准交付链路">
        <Steps
          responsive
          items={[
            {
              title: "发布数据",
              content: "platform 发布不可变 DataRelease",
              icon: <DatabaseOutlined />
            },
            {
              title: "外部研究",
              content: "qlib-platform 完成特征、训练、walk-forward 与选择",
              icon: <ExperimentOutlined />
            },
            {
              title: "导入与预览",
              content: "Artifact Contract v2 + content hash + lineage",
              icon: <CheckCircleOutlined />
            },
            {
              title: "LEAN 验证",
              content: "官方 LEAN 做执行侧权威验证",
              icon: <PlayCircleOutlined />
            }
          ]}
        />
      </Card>

      <Card title="下一步">
        <Space wrap>
          <Button type="primary"><Link to="/data">检查 DataRelease / 数据</Link></Button>
          <Button><Link to="/backtests">进入 LEAN 回测</Link></Button>
          <Button><Link to="/docs/research">阅读 Research Interop 文档</Link></Button>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>
          <Text strong>注意：</Text>当前 release status 仍由认证证据决定。导入研究产物、A股适配实现或港股 preview 都不自动等于生产准入。
        </Paragraph>
      </Card>
    </Space>
  );
}
