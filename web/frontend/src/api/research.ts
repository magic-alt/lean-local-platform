import { request } from "./client";

export interface MarketLocalizationCapability {
  key: string;
  name: string;
  currency: string;
  timezone: string;
  implementation_status: "upstream" | "implemented" | "partial" | string;
  execution_scope: string;
  lot_size_policy: string;
  tick_size_policy: string;
  symbol_properties_required: boolean;
  sessions: string[][];
  symbol_formats?: string[];
  notes?: string;
}

export interface ResearchPlatformCapabilities {
  schemaVersion: string;
  engine: {
    engine: string;
    upstreamRepository: string;
    authority: string;
    integrationMode: string;
    coreForkPolicy: string;
    capabilityPolicy: string;
    uiPolicy: string;
  };
  localization: {
    priority: string[];
    strategy: string;
    markets: MarketLocalizationCapability[];
    productionCertificationSource: string;
  };
  research: {
    owner: string;
    localExecutionEnabled: boolean;
    localNotebookWorkspaceEnabled: boolean;
    artifactContractVersion: string;
    importType: string;
    handoff: Record<string, string>;
    platformResponsibilities: string[];
    externalResponsibilities: string[];
  };
}

export interface ResearchImportPreview {
  id: string;
  researchRunId: string;
  externalRunId?: string;
  name?: string;
  status?: string;
  market?: string;
  schemaVersion?: string;
  runKind?: string;
  dataReleaseId?: string;
  modelReleaseId?: string;
  manifestSha256?: string;
  rootArtifactIds?: string[];
  summary?: Record<string, unknown>;
  artifactSummary?: Array<{
    artifactId?: string;
    artifactType?: string;
    promotionStatus?: string;
    payloadSha256?: string;
  }>;
  latestSignal?: {
    signalDate?: string;
    tradeDate?: string;
    targetArtifactId?: string;
    targetsSha256?: string;
    targetCount?: number;
    grossExposure?: number;
    previewTargets?: Array<Record<string, unknown>>;
  } | null;
  leanValidation?: {
    id?: string;
    status?: string;
    leanBacktestRunId?: string;
    validationArtifactId?: string;
    createdAt?: string;
  } | null;
  createdAt?: string;
}

export interface ResearchImportPage {
  items: ResearchImportPreview[];
  count: number;
  limit: number;
  offset: number;
}

export const researchCapabilities = () =>
  request<ResearchPlatformCapabilities>("/api/research/capabilities");

export const researchImports = (limit = 20, offset = 0) =>
  request<ResearchImportPage>(`/api/research/imports?limit=${limit}&offset=${offset}`);

export const researchImport = (id: string) =>
  request<ResearchImportPreview>(`/api/research/imports/${encodeURIComponent(id)}`);
