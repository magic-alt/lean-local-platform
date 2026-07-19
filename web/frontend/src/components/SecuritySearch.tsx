import { AutoComplete, Space, Tag, Typography } from "antd";
import type { AutoCompleteProps } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";

type SecurityItem = Awaited<ReturnType<typeof api.searchSecurities>>["items"][number];

type SecuritySearchProps = Omit<AutoCompleteProps, "options" | "onChange" | "onSearch" | "filterOption"> & {
  assetClass?: string;
  localSymbols?: string[];
  market?: string;
  onChange?: (value: string) => void;
  onSelectSecurity?: (security: SecurityItem) => void;
  value?: string;
};

const MARKET_COLORS: Record<string, string> = {
  china: "red",
  hongkong: "green",
  usa: "blue"
};

const MATCH_FIELD_LABELS: Record<string, string> = { code: "代码", name: "公司", pinyin: "拼音", alias: "别名" };
const MATCH_TYPE_LABELS: Record<string, string> = { exact: "精确", prefix: "前缀", contains: "包含" };

function optionLabel(item: SecurityItem) {
  const matchLabel = item.matchField === "none" ? "" : `${MATCH_FIELD_LABELS[item.matchField] ?? item.matchField}/${MATCH_TYPE_LABELS[item.matchType] ?? item.matchType}`;
  const companyName = String(item.name || "").trim();
  const hasDistinctCompanyName = Boolean(companyName && companyName.toUpperCase() !== item.symbol.toUpperCase());
  return (
    <div className="security-option">
      <Space size={8} className="security-option-main">
        <Tag color={MARKET_COLORS[item.market] ?? "default"}>{item.marketLabel}</Tag>
        <span className="security-option-company">{hasDistinctCompanyName ? companyName : item.symbol}</span>
        {hasDistinctCompanyName && <Typography.Text type="secondary">{item.symbol}</Typography.Text>}
      </Space>
      <Space size={6}>
        {item.exchange && <Typography.Text type="secondary" className="security-option-meta">{item.exchange}</Typography.Text>}
        {item.hasLocalData && <Tag color="cyan">本地数据</Tag>}
        {matchLabel && <Typography.Text type="secondary" className="security-option-meta">{matchLabel}</Typography.Text>}
      </Space>
    </div>
  );
}

export function SecuritySearch({
  assetClass = "equity",
  localSymbols = [],
  market = "all",
  onChange,
  onFocus,
  onSelect,
  onSelectSecurity,
  placeholder,
  value,
  ...props
}: SecuritySearchProps) {
  const [items, setItems] = useState<SecurityItem[]>([]);
  const [query, setQuery] = useState(String(value ?? ""));
  const requestSequence = useRef(0);

  useEffect(() => setQuery(String(value ?? "")), [value]);
  useEffect(() => setItems([]), [assetClass, market]);

  useEffect(() => {
    if (assetClass !== "equity") return;
    const sequence = ++requestSequence.current;
    const timer = window.setTimeout(() => {
      void api.searchSecurities(market || "all", query.trim(), 50)
        .then((result) => {
          if (sequence === requestSequence.current) setItems(result.items);
        })
        .catch(() => {
          if (sequence === requestSequence.current) setItems([]);
        });
    }, 180);
    return () => window.clearTimeout(timer);
  }, [assetClass, market, query]);

  const options = useMemo(() => {
    if (assetClass === "equity") {
      return items.map((item) => ({ key: `${item.market}:${item.symbol}`, value: item.symbol, label: optionLabel(item), security: item }));
    }
    const normalizedQuery = query.trim().toLowerCase();
    return localSymbols
      .filter((symbol) => !normalizedQuery || symbol.toLowerCase().includes(normalizedQuery))
      .slice(0, 50)
      .map((symbol) => ({ value: symbol, label: symbol }));
  }, [assetClass, items, localSymbols, query]);

  return (
    <AutoComplete
      {...props}
      value={value}
      options={options}
      filterOption={false}
      placeholder={placeholder ?? (assetClass === "equity" ? "代码 / 公司名 / 拼音 / 别名" : "输入或选择 Symbol")}
      onChange={(nextValue) => {
        setQuery(nextValue);
        onChange?.(nextValue);
      }}
      onFocus={(event) => {
        setQuery(String(value ?? ""));
        onFocus?.(event);
      }}
      onSelect={(nextValue, option) => {
        const security = (option as { security?: SecurityItem }).security;
        if (security) onSelectSecurity?.(security);
        onSelect?.(nextValue, option);
      }}
    />
  );
}
