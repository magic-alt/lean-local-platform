import { Alert, Button, Card, Input, Select, Space, Table, Tag, message } from "antd";
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";

import { api } from "../../api";
import type { DataQueryRow, DatasetPreviewResult } from "../../api";
import { candlestickOption } from "../../charts/candlestick";

export interface PreviewDatasetOption {
  key: "trade_cal" | "index_basic" | "index_daily" | "fut_basic" | "opt_basic";
  label: string;
  keywordPlaceholder: string;
}

function numberValue(value: unknown, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: digits }) : "-";
}

function dateValue(value: unknown) {
  return value ? String(value).slice(0, 10) : "-";
}

const COLUMNS: Record<string, any[]> = {
  trade_cal: [
    { title: "市场", dataIndex: "market", width: 90 },
    { title: "日期", dataIndex: "trade_date", width: 120 },
    { title: "交易日", dataIndex: "is_open", width: 90, render: (value: unknown) => Number(value) ? <Tag color="success">开市</Tag> : <Tag>休市</Tag> },
    { title: "上一交易日", dataIndex: "prev_trade_date", width: 120, render: dateValue },
    { title: "下一交易日", dataIndex: "next_trade_date", width: 120, render: dateValue },
    { title: "来源", dataIndex: "source", ellipsis: true },
  ],
  index_basic: [
    { title: "指数代码", dataIndex: "ts_code", width: 120, fixed: "left" },
    { title: "指数名称", dataIndex: "name", width: 180, ellipsis: true },
    { title: "市场", dataIndex: "market", width: 90 },
    { title: "类别", dataIndex: "category", width: 130 },
    { title: "发布机构", dataIndex: "publisher", width: 240, ellipsis: true },
    { title: "基日", dataIndex: "base_date", width: 110, render: dateValue },
    { title: "基点", dataIndex: "base_point", width: 100, render: numberValue },
    { title: "发布日期", dataIndex: "list_date", width: 110, render: dateValue },
  ],
  index_daily: [
    { title: "指数代码", dataIndex: "ts_code", width: 120, fixed: "left" },
    { title: "日期", dataIndex: "trade_date", width: 110 },
    { title: "开", dataIndex: "open", width: 100, render: numberValue },
    { title: "高", dataIndex: "high", width: 100, render: numberValue },
    { title: "低", dataIndex: "low", width: 100, render: numberValue },
    { title: "收", dataIndex: "close", width: 100, render: numberValue },
    { title: "涨跌幅", dataIndex: "pct_chg", width: 100, render: (value: unknown) => `${numberValue(value)}%` },
    { title: "成交量", dataIndex: "vol", width: 130, render: (value: unknown) => numberValue(value, 0) },
    { title: "成交额", dataIndex: "amount", width: 140, render: numberValue },
  ],
  fut_basic: [
    { title: "合约代码", dataIndex: "ts_code", width: 130, fixed: "left" },
    { title: "名称", dataIndex: "name", width: 200, ellipsis: true },
    { title: "品种", dataIndex: "fut_code", width: 90 },
    { title: "交易所", dataIndex: "exchange", width: 100 },
    { title: "合约乘数", dataIndex: "multiplier", width: 110, render: numberValue },
    { title: "交易单位", dataIndex: "trade_unit", width: 110, render: numberValue },
    { title: "报价单位", dataIndex: "quote_unit", width: 130 },
    { title: "上市日期", dataIndex: "list_date", width: 110, render: dateValue },
    { title: "最后交易日", dataIndex: "last_ddate", width: 120, render: dateValue },
  ],
  opt_basic: [
    { title: "期权代码", dataIndex: "ts_code", width: 130, fixed: "left" },
    { title: "合约名称", dataIndex: "name", width: 260, ellipsis: true },
    { title: "标的", dataIndex: "opt_code", width: 130 },
    { title: "方向", dataIndex: "call_put", width: 80, render: (value: unknown) => <Tag color={value === "C" ? "red" : "green"}>{value === "C" ? "认购" : value === "P" ? "认沽" : String(value || "-")}</Tag> },
    { title: "行权价", dataIndex: "exercise_price", width: 100, render: numberValue },
    { title: "合约月份", dataIndex: "s_month", width: 100 },
    { title: "乘数", dataIndex: "opt_multiplier", width: 100, render: numberValue },
    { title: "上市日期", dataIndex: "list_date", width: 110, render: dateValue },
    { title: "到期日期", dataIndex: "maturity_date", width: 110, render: dateValue },
    { title: "交易所", dataIndex: "exchange", width: 90 },
  ],
};

export function DatasetPreviewPanel({ datasets }: { datasets: PreviewDatasetOption[] }) {
  const [dataset, setDataset] = useState(datasets[0].key);
  const [keyword, setKeyword] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [result, setResult] = useState<DatasetPreviewResult>();
  const [loading, setLoading] = useState(false);
  const pageSize = 100;

  async function load(
    page = 1,
    selectedDataset = dataset,
    filters = { keyword, startDate, endDate },
  ) {
    setLoading(true);
    try {
      setResult(await api.datasetPreview(selectedDataset, {
        keyword: filters.keyword,
        startDate: filters.startDate || undefined,
        endDate: filters.endDate || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      }));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setKeyword("");
    setStartDate("");
    setEndDate("");
    void load(1, dataset, { keyword: "", startDate: "", endDate: "" });
    // The dataset switch intentionally resets filters before the next manual search.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset]);

  const selected = datasets.find((item) => item.key === dataset) ?? datasets[0];
  const chartRows = useMemo<DataQueryRow[]>(() => {
    if (dataset !== "index_daily") return [];
    return (result?.items ?? []).map((item) => ({
      timestamp: String(item.trade_date || ""),
      open: Number(item.open || 0),
      high: Number(item.high || 0),
      low: Number(item.low || 0),
      close: Number(item.close || 0),
      volume: Number(item.vol || 0),
      source: "tushare:index_daily",
    })).sort((left, right) => left.timestamp.localeCompare(right.timestamp));
  }, [dataset, result?.items]);

  return (
    <Card size="small" className="dataset-preview-card">
      <div className="dataset-preview-toolbar">
        <Select
          value={dataset}
          style={{ width: 190 }}
          options={datasets.map((item) => ({ value: item.key, label: item.label }))}
          onChange={setDataset}
        />
        <Input
          allowClear
          value={keyword}
          prefix={<SearchOutlined />}
          placeholder={selected.keywordPlaceholder}
          onChange={(event) => setKeyword(event.target.value)}
          onPressEnter={() => void load(1)}
          style={{ minWidth: 220, flex: 1 }}
        />
        <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} style={{ width: 150 }} />
        <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} style={{ width: 150 }} />
        <Button type="primary" icon={<ReloadOutlined />} loading={loading} onClick={() => void load(1)}>查询数据库</Button>
      </div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message={result?.storage === "compressed_archive" ? "读取压缩批次归档，不恢复逐行 JSON" : "读取规范化 MySQL 表"}
        description={`共匹配 ${(result?.count ?? 0).toLocaleString()} 条记录${result?.updatedAt ? ` · 归档时间 ${result.updatedAt}` : ""}`}
      />
      {chartRows.length > 0 && <ReactECharts option={candlestickOption(chartRows, String(result?.items[0]?.ts_code || "指数"))} style={{ height: 520, marginBottom: 12 }} />}
      <Table
        size="small"
        loading={loading}
        rowKey={(row) => `${dataset}:${String(row.ts_code || row.symbol || row.market || "row")}:${String(row.trade_date || row.list_date || row.name || "")}`}
        dataSource={result?.items ?? []}
        columns={COLUMNS[dataset]}
        scroll={{ x: "max-content" }}
        pagination={{
          pageSize,
          total: result?.count ?? 0,
          current: Math.floor((result?.offset ?? 0) / pageSize) + 1,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total.toLocaleString()} 条`,
          onChange: (page) => void load(page),
        }}
      />
    </Card>
  );
}
