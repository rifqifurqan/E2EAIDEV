// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { buildEnv } from "../../scripts/next-no-telemetry.mjs";

const root = resolve(__dirname, "../..");

describe("NFR-12 no outbound telemetry by default", () => {
  it("forces Next.js telemetry off even when the caller enables it", () => {
    expect(buildEnv({ NEXT_TELEMETRY_DISABLED: "0", PATH: "/bin" })).toMatchObject({
      NEXT_TELEMETRY_DISABLED: "1",
      PATH: "/bin",
    });
  });

  it("routes every next script through the wrapper", () => {
    const pkg = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
    for (const name of ["dev", "build", "start"]) {
      expect(pkg.scripts[name], name).toContain("scripts/next-no-telemetry.mjs");
      expect(pkg.scripts[name], name).not.toMatch(/^next /);
    }
  });
});
