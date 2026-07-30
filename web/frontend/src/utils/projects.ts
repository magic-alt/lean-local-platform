import type { Project } from "../api";

export interface ProjectSelectOption {
  value: string;
  label: string;
}

function projectLabel(project: Project): string {
  return String(project.display_name || project.name || project.id).trim() || project.id;
}

/**
 * Project copies can have different IDs while exposing the same display name.
 * Keep the first project returned by the API (currently the most recently
 * updated one) so selection dropdowns do not render indistinguishable entries.
 */
export function projectSelectOptions(projects: Project[]): ProjectSelectOption[] {
  const seenLabels = new Set<string>();
  const options: ProjectSelectOption[] = [];

  for (const project of projects) {
    const label = projectLabel(project);
    const normalizedLabel = label.normalize("NFKC").toLowerCase();
    if (seenLabels.has(normalizedLabel)) continue;
    seenLabels.add(normalizedLabel);
    options.push({ value: project.id, label });
  }

  return options;
}
