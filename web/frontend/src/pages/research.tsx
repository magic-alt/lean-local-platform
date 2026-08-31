import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Row,
  Space,
  Steps,
  Tag,
  Typography
} from "antd";
import {
  CheckCircleOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  PlayCircleOutlined
} from "@ant-design/icons";
import { Link } from "react-router-dom";

const { Paragraph, Text, Title } = Typography;

export function ResearchPage() {
  return (
    <Space direction="vertical" size={20} style={{ width: "100%" }}>
      <div>
        <Space align="center" wrap>
          <Title level={2} style={{ margin: 0 }}>研究交付</Title>
          <Tag color="blue">Artifact Contract v2</Tag>
          <Tag>qlib-platform owned</Tag>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, maxWidth: 920 }}>
          LEAN Local Platform 不再执行模型研究或 Notebook 工作区。特征、因子、训练、滚动验证和选股研究由外部
          qlib-platform 负责；本平台只接收不可变研究产物、验证 lineage/hash，并用 LEAN 做权威执行验证。
        </Paragraph>
      </div>

      <Alert
        type="info"
        showIcon
        message="研究执行边界已收口"
        description="旧的研究模板、研究运行、重试/取消、导出和 Notebook Workspace API 已退役。前端不会再调用这些已删除的接口。"
      />

      <Card title="标准交付链路">
        <Steps
          responsive
          items={[
            {
              title: "发布数据",
              description: "platform 发布不可变 DataRelease",
              icon: <DatabaseOutlined />
            },
            {
              title: "外部研究",
              description: "qlib-platform 完成特征、训练和选择",
              icon: <ExperimentOutlined />
            },
            {
              title: "导入产物",
              description: "Artifact Contract v2 + content hash",
              icon: <CheckCircleOutlined />
            },
            {
              title: "LEAN 验证",
              description: "回测与执行侧权威验证",
              icon: <PlayCircleOutlined />
            }
          ]}
        />
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="平台继续负责">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="数据权威">Parquet DataRelease、PIT、QA、lineage</Descriptions.Item>
              <Descriptions.Item label="研究导入">POST /api/research/imports/qlib</Descriptions.Item>
              <Descriptions.Item label="验证回写">POST /api/research/runs/:runId/lean-validation</Descriptions.Item>
              <Descriptions.Item label="执行">LEAN backtest / optimization / paper control</Descriptions.Item>
              <Descriptions.Item label="证据">运行产物、manifest、hash、validation evidence</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="外部 qlib-platform 负责">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="研究">特征、因子、模型训练、滚动验证</Descriptions.Item>
              <Descriptions.Item label="选择">模型评分、目标组合与研究诊断</Descriptions.Item>
              <Descriptions.Item label="交付">Artifact Contract v2 研究 bundle</Descriptions.Item>
              <Descriptions.Item label="约束">保持 DataReleaseId、artifactId 与 SHA-256 lineage</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      <Card title="下一步">
        <Space wrap>
          <Button type="primary"><Link to="/data">检查 DataRelease / 数据</Link></Button>
          <Button><Link to="/backtests">进入 LEAN 回测</Link></Button>
          <Button><Link to="/docs/research">阅读研究边界文档</Link></Button>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>
          <Text strong>注意：</Text>当前版本仍为 NOT CERTIFIED，Live/P9 写入保持禁用；研究产物导入成功也不等于生产准入。
        </Paragraph>
      </Card>
    </Space>
  );
}
