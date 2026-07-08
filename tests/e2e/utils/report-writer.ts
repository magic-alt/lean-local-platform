import fs from "node:fs";

import { reportPath } from "./env";

export interface CaseRecord {
  id: string;
  name: string;
  status: "Pass" | "Fail" | "Blocked" | "Skipped";
  details?: Record<string, unknown>;
}

export function appendCaseResult(record: CaseRecord) {
  const file = reportPath("e2e-case-results.json");
  const current = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf-8")) as CaseRecord[] : [];
  const next = current.filter((item) => item.id !== record.id);
  next.push(record);
  fs.writeFileSync(file, JSON.stringify(next, null, 2), "utf-8");
}

export function writeAuditMarkdown(content: string) {
  fs.writeFileSync(reportPath("e2e-audit-report.md"), content, "utf-8");
}
