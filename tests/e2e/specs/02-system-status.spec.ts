import { expect, test } from "@playwright/test";

import { apiGet } from "../utils/api";
import { SystemStatusPage } from "../pages/system-status.page";

test.describe("02 system status @smoke", () => {
  test("frontend can verify the current PostgreSQL/RabbitMQ platform dependencies", async ({ page, request }) => {
    const health = await apiGet<{
      status: string;
      dependencies: Array<{ service: string; ok: boolean; detail: unknown }>;
    }>(request, "/api/health/dependencies");
    const services = health.dependencies.map((item) => item.service);
    expect(services).toEqual(expect.arrayContaining([
      "database",
      "broker",
      "lean_data_dir",
      "results_dir_writable"
    ]));
    expect(services).not.toContain("redis");

    const statusPage = new SystemStatusPage(page);
    await statusPage.open();
    await statusPage.check();
    for (const service of ["database", "broker", "lean_data_dir", "results_dir_writable"]) {
      await statusPage.expectDependency(service, true);
    }

    if (process.env.E2E_REQUIRE_LEAN_RUNTIME !== "0") {
      for (const service of ["docker", "lean_image", "lean_runner"]) {
        expect(services).toContain(service);
        await statusPage.expectDependency(service, true);
      }
    }
  });
});
