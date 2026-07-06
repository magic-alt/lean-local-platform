import { Form, Input, InputNumber } from "antd";

import type { AssetClassInfo, Project, StrategyTemplate } from "../api";

export function templateDefaults(template?: StrategyTemplate) {
  return Object.fromEntries((template?.parameters ?? []).map((parameter) => [parameter.key, parameter.default ?? ""]));
}

export function strategyFields(template?: StrategyTemplate) {
  return (template?.parameters ?? []).map((parameter) => (
    <Form.Item key={parameter.key} name={["parameters", parameter.key]} label={parameter.label}>
      {parameter.type === "number" ? <InputNumber min={parameter.min} style={{ width: "100%" }} /> : <Input />}
    </Form.Item>
  ));
}

export function projectTemplate(project?: Project, templates: StrategyTemplate[] = []) {
  const key = String(project?.config?.templateKey ?? "");
  return templates.find((template) => template.key === key);
}

export function projectMarket(project?: Project) {
  return String(project?.config?.market ?? "usa");
}

export function projectAssetClass(project?: Project) {
  return String(project?.config?.assetClass ?? "equity");
}

export function projectVenue(project?: Project) {
  return String(project?.config?.venue ?? projectMarket(project));
}

export function projectResolution(project?: Project) {
  return String(project?.config?.resolution ?? "daily");
}

export function projectDataType(project?: Project) {
  return String(project?.config?.dataType ?? "trade");
}

export function defaultVenueFor(assetClass: string, assets: AssetClassInfo[], market = "usa") {
  if (assetClass === "equity") return market;
  const found = assets.find((item) => item.key === assetClass);
  return found?.defaultVenue ?? found?.venues?.[0] ?? market;
}

export function defaultTemplateFor(assetClass: string) {
  if (assetClass === "crypto") return "crypto_buy_hold";
  if (assetClass === "future") return "futures_trend";
  return "ema_cross";
}
