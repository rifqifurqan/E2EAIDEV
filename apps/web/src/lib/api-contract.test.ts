import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { ENDPOINTS } from "./api-client";

/**
 * Contract guard: every path the web client calls must exist in the generated OpenAPI file
 * (docs/openapi.json), so a renamed/misspelled route fails here instead of 404-ing in the UI.
 */
const spec = JSON.parse(readFileSync(resolve(__dirname, "../../../../docs/openapi.json"), "utf-8")) as {
  paths: Record<string, Record<string, unknown>>;
};

function toRegex(specPath: string): RegExp {
  return new RegExp(`^${specPath.replace(/\{[^}]+\}/g, "[^/]+")}$`);
}

function resolveEndpoint(value: unknown): string {
  if (typeof value === "function") {
    // Parameterised builders: feed a placeholder for every argument.
    const fn = value as (...args: string[]) => string;
    return fn("x", "x");
  }
  return String(value);
}

describe("web API client matches the OpenAPI contract", () => {
  const known = Object.keys(spec.paths).map(toRegex);

  // Paths the UI declares but the API does not (yet) serve; keep this list shrinking, never growing.
  const KNOWN_GAPS = new Set<string>(["bot"]);

  for (const [name, value] of Object.entries(ENDPOINTS)) {
    if (KNOWN_GAPS.has(name)) continue;
    it(`${name} is served by the API`, () => {
      const path = `/api/v1${resolveEndpoint(value).split("?")[0]}`;
      expect(known.some((rx) => rx.test(path)), path).toBe(true);
    });
  }
});
