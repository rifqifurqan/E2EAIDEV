import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "fs";
import { resolve, join } from "path";

function walkSync(dir: string, exts: string[]): string[] {
  const results: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory() && entry !== "node_modules") {
      results.push(...walkSync(full, exts));
    } else if (exts.some((e) => full.endsWith(e)) && !full.includes(".test.")) {
      results.push(full);
    }
  }
  return results;
}

// The pattern to check for — kept as a variable so this test file itself
// does not contain a bare import-style reference that would false-positive.
const CLOUD_PATTERN = /assistant[-.]cloud/;

describe("no cloud dependency guard", () => {
  it("package.json has no cloud SDK dependency", () => {
    const pkg = JSON.parse(
      readFileSync(resolve(__dirname, "../../package.json"), "utf-8"),
    );
    const allDeps = {
      ...pkg.dependencies,
      ...pkg.devDependencies,
    };
    const banned = ["@assistant-ui/react-ai-sdk", "assistant-cloud", "@assistant-cloud/core"];
    for (const name of banned) {
      expect(allDeps).not.toHaveProperty(name);
    }
  });

  it("no source file imports a cloud SDK", () => {
    const srcDir = resolve(__dirname, "..");
    const files = walkSync(srcDir, [".ts", ".tsx"]);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const content = readFileSync(file, "utf-8");
      expect(content, `${file} must not reference cloud SDK`).not.toMatch(
        CLOUD_PATTERN,
      );
    }
  });
});
