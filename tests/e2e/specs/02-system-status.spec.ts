import { expect, test } from "@playwright/test";

import { apiGet } from "../utils/api";
import { SystemStatusPage } from "../pages/system-status.page";

test.describe("02 system status @smoke", () => {
  test("frontend can verify API, Docker, LEAN runner, data dir, and results dir", async ({ page, request }) => {
    const health = await apiGet<{
      status: string;
      dependencies: Array<{ service: string; ok: boolean; detail: unknown }>;
    }>(request, "/api/health/dependencies");
    expect(health.dependencies.map((item) => item.service)).toEqual(expect.arrayContaining([
      "database",
      "redis",
      "docker",
      "lean_image",
      "lean_data_dir",
      "results_dir_writable",
      "lean_runner"
    ]));

    const statusPage = new SystemStatusPage(page);
    await statusPage.open();
    await statusPage.check();
    for (const service of ["database", "redis", "docker", "lean_data_dir", "results_dir_writable", "lean_runner"]) {
      await statusPage.expectDependency(service, true);
    }
  });
});
