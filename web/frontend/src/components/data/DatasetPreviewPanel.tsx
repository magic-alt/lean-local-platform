import { Alert, Button, Card, Empty, Input, Select, Space, Spin, Tag, message } from "antd";
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { Component, type ErrorInfo, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../api";
import type { DataQueryRow, DatasetPreviewResult } from "../../api";
import { candlestickOption } from "../../charts/candlestick";
import { LeanChart } from "../../charts/LeanChart";

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

function textValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

interface PreviewColumn {
  title: string;
  dataIndex: string;
  width?: number;
  ellipsis?: boolean;
  render?: (value: unknown) => ReactNode;
}

const COLUMNS: Record<string, PreviewColumn[]> = {
  trade_cal: [
    { title: "市场", dataIndex: "market", width: 90 },
    { title: "日期", dataIndex: "trade_date", width: 120 },
    { title: "交易日", dataIndex: "is_open", width: 90, render: (value: unknown) => Number(value) ? <Tag color="success">开市</Tag> : <Tag>休市</Tag> },
    { title: "上一交易日", dataIndex: "prev_trade_date", width: 120, render: dateValue },
    { title: "下一交易日", dataIndex: "next_trade_date", width: 120, render: dateValue },
    { title: "来源", dataIndex: "source", ellipsis: true },
  ],
  index_basic: [
    { title: "指数代码", dataIndex: "ts_code", width: 120, render: textValue },
    { title: "指数名称", dataIndex: "name", width: 180, ellipsis: true, render: textValue },
    { title: "市场", dataIndex: "market", width: 90, render: textValue },
    { title: "类别", dataIndex: "category", width: 130, render: textValue },
    { title: "发布机构", dataIndex: "publisher", width: 240, ellipsis: true, render: textValue },
    { title: "基日", dataIndex: "base_date", width: 110, render: dateValue },
    { title: "基点", dataIndex: "base_point", width: 100, render: numberValue },
    { title: "发布日期", dataIndex: "list_date", width: 110, render: dateValue },
  ],
  index_daily: [
    { title: "指数代码", dataIndex: "ts_code", width: 120, render: textValue },
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
    { title: "合约代码", dataIndex: "ts_code", width: 130, render: textValue },
    { title: "名称", dataIndex: "name", width: 200, ellipsis: true, render: textValue },
    { title: "品种", dataIndex: "fut_code", width: 90, render: textValue },
    { title: "交易所", dataIndex: "exchange", width: 100, render: textValue },
    { title: "合约乘数", dataIndex: "multiplier", width: 110, render: numberValue },
    { title: "交易单位", dataIndex: "trade_unit", width: 110, render: numberValue },
    { title: "报价单位", dataIndex: "quote_unit", width: 130, render: textValue },
    { title: "上市日期", dataIndex: "list_date", width: 110, render: dateValue },
    { title: "最后交易日", dataIndex: "last_ddate", width: 120, render: dateValue },
  ],
  opt_basic: [
    { title: "期权代码", dataIndex: "ts_code", width: 130, render: textValue },
    { title: "合约名称", dataIndex: "name", width: 260, ellipsis: true, render: textValue },
    { title: "标的", dataIndex: "opt_code", width: 130, render: textValue },
    { title: "方向", dataIndex: "call_put", width: 80, render: (value: unknown) => <Tag color={value === "C" ? "red" : "green"}>{value === "C" ? "认购" : value === "P" ? "认沽" : String(value || "-")}</Tag> },
    { title: "行权价", dataIndex: "exercise_price", width: 100, render: numberValue },
    { title: "合约月份", dataIndex: "s_month", width: 100, render: textValue },
    { title: "乘数", dataIndex: "opt_multiplier", width: 100, render: numberValue },
    { title: "上市日期", dataIndex: "list_date", width: 110, render: dateValue },
    { title: "到期日期", dataIndex: "maturity_date", width: 110, render: dateValue },
    { title: "交易所", dataIndex: "exchange", width: 90, render: textValue },
  ],
};

const TABLE_WIDTH: Record<string, number> = {
  trade_cal: 700,
  index_basic: 1080,
  index_daily: 1100,
  fut_basic: 1120,
  opt_basic: 1250,
};

class DatasetPreviewErrorBoundary extends Component<
  { children: ReactNode; resetKey: string },
  { error?: Error }
> {
  state: { error?: Error } = {};

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Dataset preview render failed", error, info);
  }

  componentDidUpdate(previous: { resetKey: string }) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) {
      this.setState({ error: undefined });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <Alert
          type="error"
          showIcon
          message="预览渲染失败"
          description={`前端错误：${this.state.error.message || this.state.error.name || "未知渲染错误"}`}
          action={<Button size="small" onClick={() => this.setState({ error: undefined })}>重新渲染</Button>}
        />
      );
    }
    return this.props.children;
  }
}

function DatasetPreviewContent({ datasets }: { datasets: PreviewDatasetOption[] }) {
  const [dataset, setDataset] = useState(datasets[0].key);
  const [keyword, setKeyword] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [result, setResult] = useState<DatasetPreviewResult>();
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const requestSequence = useRef(0);
  const pageSize = 100;

  async function load(
    page = 1,
    selectedDataset = dataset,
    filters = { keyword, startDate, endDate },
  ) {
    const sequence = ++requestSequence.current;
    setLoading(true);
    setLoadError("");
    try {
      const response = await api.datasetPreview(selectedDataset, {
        keyword: filters.keyword,
        startDate: filters.startDate || undefined,
        endDate: filters.endDate || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      });
      if (sequence !== requestSequence.current) return;
      setResult({
        ...response,
        items: Array.isArray(response.items)
          ? response.items.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
          : [],
        count: Number.isFinite(Number(response.count)) ? Number(response.count) : 0,
        offset: Number.isFinite(Number(response.offset)) ? Number(response.offset) : 0,
      });
    } catch (error) {
      if (sequence !== requestSequence.current) return;
      const detail = (error as Error).message || "数据集预览加载失败";
      setLoadError(detail);
      message.error(detail);
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }

  useEffect(() => () => {
    requestSequence.current += 1;
  }, []);

  useEffect(() => {
    setKeyword("");
    setStartDate("");
    setEndDate("");
    void load(1, dataset, { keyword: "", startDate: "", endDate: "" });
    // The dataset switch intentionally resets filters before the next manual search.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset]);

  const selected = datasets.find((item) => item.key === dataset) ?? datasets[0];
  const currentPage = Math.floor((result?.offset ?? 0) / pageSize) + 1;
  const totalPages = Math.max(1, Math.ceil((result?.count ?? 0) / pageSize));
  const columns = COLUMNS[dataset] ?? [];
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
      {loadError && <Alert type="error" showIcon closable message="查询失败" description={loadError} style={{ marginBottom: 12 }} />}
      {chartRows.length > 0 && <LeanChart option={candlestickOption(chartRows, String(result?.items[0]?.ts_code || "指数"))} style={{ height: 520, marginBottom: 12 }} />}
      <Spin spinning={loading}>
        <div className="dataset-preview-table-scroll">
          <table className="dataset-preview-table" style={{ minWidth: TABLE_WIDTH[dataset] ?? 900 }}>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column.dataIndex} style={{ width: column.width }}>{column.title}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(result?.items ?? []).map((row, rowIndex) => {
                const key = `${dataset}:${String(row.ts_code || row.symbol || row.market || "row")}:${String(row.trade_date || row.list_date || row.name || rowIndex)}`;
                return (
                  <tr key={key}>
                    {columns.map((column) => {
                      const rawValue = row[column.dataIndex];
                      return (
                        <td
                          key={column.dataIndex}
                          className={column.ellipsis ? "dataset-preview-cell-ellipsis" : undefined}
                          title={column.ellipsis ? textValue(rawValue) : undefined}
                        >
                          {column.render ? column.render(rawValue) : textValue(rawValue)}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!loading && (result?.items.length ?? 0) === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配记录" />}
        </div>
      </Spin>
      <div className="dataset-preview-pagination">
        <span>共 {(result?.count ?? 0).toLocaleString()} 条 · 第 {currentPage.toLocaleString()} / {totalPages.toLocaleString()} 页</span>
        <Space>
          <Button size="small" disabled={loading || currentPage <= 1} onClick={() => void load(currentPage - 1)}>上一页</Button>
          <Button size="small" disabled={loading || currentPage >= totalPages} onClick={() => void load(currentPage + 1)}>下一页</Button>
        </Space>
      </div>
    </Card>
  );
}

export function DatasetPreviewPanel({ datasets }: { datasets: PreviewDatasetOption[] }) {
  const resetKey = datasets.map((item) => item.key).join(":");
  return (
    <DatasetPreviewErrorBoundary resetKey={resetKey}>
      <DatasetPreviewContent datasets={datasets} />
    </DatasetPreviewErrorBoundary>
  );
}
