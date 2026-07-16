import { Alert, Card, Space, Statistic, Table, Tag, Tooltip } from "antd";

import type { BacktestAdmissionResponse, BacktestExperiment, BacktestValidation } from "../../api";
import { asRecord, shortHash, shortValue } from "../../utils/display";

export function ValidationStatusTag({ validation }: { validation?: BacktestValidation | null }) {
  if (!validation) return <Tag>unknown</Tag>;
  const severity = String(validation.severity || (validation.passed === false ? "critical" : "ok"));
  const color = validation.passed === false || severity === "critical" ? "red" : severity === "warning" ? "gold" : "green";
  return <Tag color={color}>{validation.passed === false ? "failed" : severity}</Tag>;
}

function gateDetailSummary(details?: Record<string, unknown>) {
  const item = asRecord(details);
  const coverage = [
    item.bar_count != null ? `bars ${item.bar_count}` : null,
    item.market_bar_count != null ? `market bars ${item.market_bar_count}` : null,
    item.status_count != null ? `status ${item.status_count}` : null
  ].filter(Boolean);
  if (coverage.length) return coverage.join(" / ");
  if (item.symbol) {
    const range = item.startDate && item.endDate ? ` ${item.startDate} -> ${item.endDate}` : "";
    return `${item.symbol}${range}`;
  }
  if (item.rows != null) return `rows ${item.rows}`;
  if (item.batchId || item.status) return [item.batchId ? `batch ${item.batchId}` : null, item.status ? `status ${item.status}` : null].filter(Boolean).join(" / ");
  return shortValue(item, 120);
}

function ValueCell({ value }: { value: unknown }) {
  const text = shortValue(value);
  return text.endsWith("...") ? <Tooltip title={typeof value === "string" ? value : JSON.stringify(value)}>{text}</Tooltip> : <>{text}</>;
}

function KeyValueTable({ rows }: { rows: Array<{ key: string; value: unknown }> }) {
  return (
    <Table
      size="small"
      pagination={false}
      rowKey="key"
      dataSource={rows}
      columns={[
        { title: "Field", dataIndex: "key", width: 190 },
        { title: "Value", dataIndex: "value", render: (value) => <ValueCell value={value} /> }
      ]}
    />
  );
}

export function BacktestTrustPanel({
  validation,
  experiment,
  fingerprint
}: {
  validation?: BacktestValidation | null;
  experiment?: BacktestExperiment | null;
  fingerprint?: Record<string, unknown> | null;
}) {
  const scope = asRecord(validation?.scope);
  const marketRules = asRecord(validation?.marketRules);
  const feeModel = asRecord(marketRules.feeModel);
  const slippageModel = asRecord(marketRules.slippageModel);
  const validationData = asRecord(validation?.data);
  const coverage = asRecord(validationData.coverage);
  const benchmark = asRecord(validationData.benchmark);
  const latestBatch = asRecord(validationData.latestImportBatch);
  const gates = validation?.gates ?? [];
  const strategy = asRecord(experiment?.strategy);
  const parameters = asRecord(experiment?.parameters);
  const experimentData = asRecord(experiment?.data);
  const environment = asRecord(experiment?.environment);
  const marketDailyBars = asRecord(experimentData.marketDailyBars);
  const tradeStatus = asRecord(experimentData.tradeStatus);
  const fp = asRecord(fingerprint);
  if (!validation && !experiment && !fingerprint) {
    return <Alert type="info" message="Validation metadata is not available for this run." />;
  }
  return (
    <>
      <div className="grid">
        <Card><div className="metric-label">Validation</div><ValidationStatusTag validation={validation} /></Card>
        <Card><Statistic title="Benchmark Rows" value={shortValue(benchmark.rows ?? fp.benchmark_rows)} /></Card>
        <Card><Statistic title="Daily Bars" value={shortValue(marketDailyBars.row_count ?? fp.market_daily_bars_count ?? coverage.bar_count)} /></Card>
        <Card><Statistic title="Trade Status" value={shortValue(tradeStatus.row_count ?? fp.trade_status_count ?? coverage.status_count)} /></Card>
      </div>
      <div className="two-column">
        <Card title="A-Share Rules">
          <Space wrap style={{ marginBottom: 12 }}>
            <Tag color={marketRules.enabled ? "blue" : "default"}>{marketRules.enabled ? "enabled" : "not required"}</Tag>
            {Boolean(marketRules.tPlusOne) && <Tag>T+1</Tag>}
            {Boolean(marketRules.suspendedBlocked) && <Tag>suspension blocked</Tag>}
            {Boolean(marketRules.limitUpBuyBlocked) && <Tag>limit-up buy blocked</Tag>}
            {Boolean(marketRules.limitDownSellBlocked) && <Tag>limit-down sell blocked</Tag>}
            {Boolean(marketRules.benchmarkRequired) && <Tag>benchmark required</Tag>}
          </Space>
          <KeyValueTable
            rows={[
              { key: "lotSize", value: marketRules.lotSize },
              { key: "executionPolicy", value: marketRules.executionPolicy },
              { key: "commissionRate", value: feeModel.commissionRate },
              { key: "minCommission", value: feeModel.minCommission },
              { key: "stampTaxSell", value: feeModel.stampTaxSell },
              { key: "transferFeeRate", value: feeModel.transferFeeRate },
              { key: "slippageBps", value: slippageModel.slippageBps },
              { key: "cashBuffer", value: marketRules.cashBuffer }
            ]}
          />
        </Card>
        <Card title="Data Gates">
          <Table
            size="small"
            pagination={false}
            rowKey={(row) => `${row.name}-${gateDetailSummary(row.details)}`}
            dataSource={gates}
            columns={[
              { title: "Gate", dataIndex: "name", ellipsis: true },
              { title: "Status", render: (_, gate) => <Tag color={gate.passed ? "green" : "red"}>{gate.passed ? "passed" : "failed"}</Tag> },
              { title: "Severity", dataIndex: "severity" },
              { title: "Details", render: (_, gate) => <span className="muted">{gateDetailSummary(gate.details)}</span> }
            ]}
          />
        </Card>
      </div>
      <div className="two-column">
        <Card title="Data Evidence">
          <KeyValueTable
            rows={[
              { key: "symbol", value: scope.symbol },
              { key: "period", value: `${shortValue(scope.start)} -> ${shortValue(scope.end)}` },
              { key: "adjust", value: scope.adjust },
              { key: "barCount", value: coverage.bar_count ?? marketDailyBars.row_count },
              { key: "statusCount", value: coverage.status_count ?? tradeStatus.row_count },
              { key: "benchmark", value: benchmark.symbol },
              { key: "benchmarkRows", value: benchmark.rows },
              { key: "importBatch", value: latestBatch.id },
              { key: "importStatus", value: latestBatch.status }
            ]}
          />
        </Card>
        <Card title="Experiment Fingerprint">
          <KeyValueTable
            rows={[
              { key: "parametersSha256", value: shortHash(parameters.sha256 ?? fp.parameters_sha256) },
              { key: "strategySha256", value: shortHash(strategy.sha256 ?? fp.strategy_file_sha256) },
              { key: "gitCommit", value: shortHash(strategy.gitCommit ?? fp.git_commit) },
              { key: "gitDirty", value: strategy.gitDirty ?? fp.git_dirty },
              { key: "dockerImage", value: environment.dockerImage ?? fp.docker_image },
              { key: "dockerDigest", value: shortHash(environment.dockerImageDigest ?? fp.docker_image_digest) },
              { key: "leanZipSha256", value: shortHash(experimentData.leanZipSha256 ?? fp.lean_zip_sha256) },
              { key: "factorFileSha256", value: shortHash(experimentData.factorFileSha256 ?? fp.factor_file_sha256) },
              { key: "dataBatchId", value: experimentData.batchId ?? fp.data_batch_id }
            ]}
          />
        </Card>
      </div>
    </>
  );
}

export function StrategyAdmissionPanel({ value }: { value?: BacktestAdmissionResponse | null }) {
  const admission = value?.admission;
  if (!value) return <Alert type="info" message="Strategy admission metadata is not available for this run." />;
  if (!admission) {
    return (
      <Alert
        type="info"
        showIcon
        message={value.registrationStatus === "not_applicable"
          ? "Strategy admission does not apply to this standalone run."
          : "This parameter set has not been registered for strategy admission."}
        description={value.registrationStatus === "not_applicable"
          ? `Parameter fingerprint: ${shortHash(value.parametersSha256)}`
          : `Parameter fingerprint: ${shortHash(value.parametersSha256)}. Register a baseline and evaluate the required market-regime runs before treating this as admitted.`}
      />
    );
  }
  const evaluation = admission.evaluation ?? {};
  const status = evaluation.status ?? (admission.current_stage === "admission_passed" || admission.current_stage === "paper_validated" ? "pass" : "pending");
  const statusColor = status === "pass" ? "green" : status === "watch" ? "gold" : status === "fail" ? "red" : "blue";
  const gates = evaluation.gates ?? [];
  return (
    <>
      <div className="grid">
        <Card><div className="metric-label">Stage</div><Tag color={admission.current_stage === "admission_passed" || admission.current_stage === "paper_validated" ? "green" : "blue"}>{admission.current_stage}</Tag></Card>
        <Card><div className="metric-label">Evaluation</div><Tag color={statusColor}>{status}</Tag></Card>
        <Card><Statistic title="Profile" value={`${admission.profile_name} / ${admission.profile_version}`} /></Card>
        <Card><Statistic title="Sample Set" value={admission.sample_set} /></Card>
      </div>
      <Card title="Admission Gates" style={{ marginTop: 16 }}>
        {gates.length ? (
          <Table
            size="small"
            pagination={false}
            rowKey="name"
            dataSource={gates}
            columns={[
              { title: "Gate", dataIndex: "name" },
              { title: "Status", render: (_, gate) => <Tag color={gate.passed ? "green" : gate.severity === "warning" ? "gold" : "red"}>{gate.passed ? "passed" : "failed"}</Tag> },
              { title: "Severity", dataIndex: "severity" },
              { title: "Actual", dataIndex: "actual", render: (item) => shortValue(item) },
              { title: "Expected / Baseline", render: (_, gate) => shortValue(gate.expected ?? gate.baseline ?? gate.reason) }
            ]}
          />
        ) : <Alert type="info" message="A baseline is registered; admission gates have not been evaluated yet." />}
      </Card>
    </>
  );
}
