import { createOperationId, request } from "./client";

export interface WorkflowBlockedReason {
  code: string;
  detail: string;
  owner: string;
}

export interface IntegratedWorkflowIdentity {
  researchRunId?: string | null;
  dataReleaseId?: string | null;
  artifactId?: string | null;
  validationRunId?: string | null;
  leanBacktestRunId?: string | null;
  deploymentId?: string | null;
  cycleId?: string | null;
  inputHash: string;
  manifestSha256?: string | null;
  targetsSha256?: string | null;
}

export interface IntegratedWorkflowStatus {
  schemaVersion: string;
  workflowId: string;
  correlationId: string;
  stage: string;
  nextAction: string;
  blockedReasons: WorkflowBlockedReason[];
  identity: IntegratedWorkflowIdentity;
  readiness: Record<string, boolean>;
  certification: Record<string, unknown>;
  authorization: Record<string, unknown>;
  steps: Array<{ stage: string; owner: string; state: string }>;
  operations: Record<string, unknown>;
}

export interface IntegratedWorkflowPlan {
  schemaVersion: string;
  workflowId: string;
  correlationId: string;
  inputHash: string;
  stage: string;
  nextAction: string;
  blockedReasons: WorkflowBlockedReason[];
  steps: Array<{ stage: string; owner: string; state: string }>;
  writeOwnerPolicy: Record<string, unknown>;
}

export interface IntegratedWorkflowResume {
  schemaVersion: string;
  workflowId: string;
  correlationId: string;
  idempotencyKey: string;
  inputHash: string;
  stage: string;
  decision: string;
  owner: string;
  dispatched: boolean;
  requiresExplicitApproval: boolean;
  requiresReview: boolean;
  reason: string;
}

export const integratedWorkflowStatus = (importId: string) =>
  request<IntegratedWorkflowStatus>(
    `/api/integrated-workflows/${encodeURIComponent(importId)}/status`,
  );

export const integratedWorkflowPlan = (importId: string) =>
  request<IntegratedWorkflowPlan>(
    `/api/integrated-workflows/${encodeURIComponent(importId)}/plan`,
  );

export const integratedWorkflowExplain = (importId: string) =>
  request<Record<string, unknown>>(
    `/api/integrated-workflows/${encodeURIComponent(importId)}/explain`,
  );

export const integratedWorkflowCompare = (leftImportId: string, rightImportId: string) => {
  const params = new URLSearchParams({ left: leftImportId, right: rightImportId });
  return request<Record<string, unknown>>(`/api/integrated-workflows/compare?${params.toString()}`);
};

export const resumeIntegratedWorkflow = (
  importId: string,
  operationId = createOperationId(),
) =>
  request<IntegratedWorkflowResume>(
    `/api/integrated-workflows/${encodeURIComponent(importId)}/resume`,
    { method: "POST", operationId },
  );
