export function marketCostParameters(market: string, feeModel?: string, slippageModel?: string) {
  const zeroFees = feeModel === "zero";
  const slippageBps = slippageModel === "zero" ? 0 : 5.0;
  if (market === "china") {
    return {
      commissionRate: zeroFees ? 0 : 0.0001,
      minCommission: zeroFees ? 0 : 5,
      stampTaxSell: zeroFees ? 0 : 0.0005,
      transferFeeRate: zeroFees ? 0 : 0.00001,
      slippageBps
    };
  }
  if (market === "hongkong") {
    return {
      commissionRate: zeroFees ? 0 : 0.0003,
      minCommission: zeroFees ? 0 : 3,
      stampTaxBuy: zeroFees ? 0 : 0.001,
      stampTaxSell: zeroFees ? 0 : 0.001,
      sfcLevyRate: zeroFees ? 0 : 0.000027,
      afrcLevyRate: zeroFees ? 0 : 0.0000015,
      exchangeTradingFeeRate: zeroFees ? 0 : 0.0000565,
      settlementFeeRate: zeroFees ? 0 : 0.000042,
      slippageBps
    };
  }
  return { slippageBps };
}

export interface BacktestRequestPayload {
  symbol: string;
  name?: string;
  assetClass?: string;
  market?: string;
  venue?: string;
  resolution?: string;
  dataType?: string;
  start: string;
  end: string;
  cash: number;
  dockerImage: string;
  projectId: string;
  benchmarkSymbol?: string;
  source?: string;
  allowResearchSource?: boolean;
  parameters: Record<string, unknown>;
  [key: string]: unknown;
}

export function buildBacktestRequest(
  values: Record<string, any>,
  context: {
    assetClass?: string;
    market?: string;
    venue?: string;
    resolution?: string;
    dataType?: string;
    projectId?: string;
  } = {}
): BacktestRequestPayload {
  const market = context.market ?? values.market;
  const feeModel = values.feeModel ?? "default";
  const slippageModel = values.slippageModel ?? "default";
  const benchmarkSymbol = values.benchmarkSymbol;
  const source = values.source;
  const allowResearchSource = values.allowResearchSource === true;
  const projectId = context.projectId ?? values.projectId;
  if (!projectId) {
    throw new Error("Project strategy is required");
  }
  return {
    ...values,
    symbol: String(values.symbol ?? "").trim().toUpperCase(),
    assetClass: context.assetClass ?? values.assetClass,
    market,
    venue: context.venue ?? values.venue ?? market,
    resolution: context.resolution ?? values.resolution,
    dataType: context.dataType ?? values.dataType,
    projectId,
    allowResearchSource,
    parameters: {
      ...(values.parameters ?? {}),
      benchmarkSymbol,
      feeModel,
      slippageModel,
      source,
      allowResearchSource,
      ...marketCostParameters(market, feeModel, slippageModel)
    }
  } as BacktestRequestPayload;
}
