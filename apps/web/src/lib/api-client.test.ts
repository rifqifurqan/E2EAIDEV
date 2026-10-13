import { describe, it, expect, vi } from "vitest";
import { ENDPOINTS } from "./api-client";
import nextConfig from "../../next.config";
import { middleware } from "../middleware";
import { NextRequest } from "next/server";

describe("API client endpoint paths", () => {
  it("health endpoints target /api/v1", () => {
    expect(ENDPOINTS.health).toBe("/health");
    expect(ENDPOINTS.ready).toBe("/ready");
  });

  it("auth endpoints match backend routes", () => {
    expect(ENDPOINTS.login).toBe("/auth/login");
    expect(ENDPOINTS.logout).toBe("/auth/logout");
    expect(ENDPOINTS.me).toBe("/me");
  });

  it("chat endpoints match backend routes", () => {
    expect(ENDPOINTS.conversations).toBe("/chat/conversations");
    expect(ENDPOINTS.conversation("abc")).toBe("/chat/conversations/abc");
    expect(ENDPOINTS.messages("abc")).toBe("/chat/conversations/abc/messages");
    expect(ENDPOINTS.feedback("msg1")).toBe("/messages/msg1/feedback");
    expect(ENDPOINTS.stop("msg1")).toBe("/messages/msg1/stop");
    expect(ENDPOINTS.ask).toBe("/chat/ask");
  });

  it("document endpoints match backend routes", () => {
    expect(ENDPOINTS.documents).toBe("/documents");
    expect(ENDPOINTS.document("d1")).toBe("/documents/d1");
    expect(ENDPOINTS.documentShares("d1")).toBe("/documents/d1/shares");
    expect(ENDPOINTS.documentSensitivity("d1")).toBe(
      "/documents/d1/sensitivity",
    );
    expect(ENDPOINTS.documentRestore("d1")).toBe("/documents/d1/restore");
    expect(ENDPOINTS.visibleChunks).toBe("/documents/visible-chunks");
  });

  it("eval endpoints match backend routes", () => {
    expect(ENDPOINTS.evalDatasets).toBe("/evals/datasets");
    expect(ENDPOINTS.evalRuns).toBe("/evals/runs");
  });

  it("bot endpoints match backend routes", () => {
    expect(ENDPOINTS.bots).toBe("/bots");
    expect(ENDPOINTS.bot("b1")).toBe("/bots/b1");
    expect(ENDPOINTS.botBundles("b1")).toBe("/bots/b1/bundles");
    expect(ENDPOINTS.botRollback("b1", "bun1")).toBe(
      "/bots/b1/bundles/bun1/rollback",
    );
    expect(ENDPOINTS.botGrants("b1")).toBe("/bots/b1/grants");
    expect(ENDPOINTS.botScope("b1")).toBe("/bots/b1/scope");
    expect(ENDPOINTS.botAsk("b1")).toBe("/bots/b1/ask");
  });

  it("admin endpoints match backend routes", () => {
    expect(ENDPOINTS.deactivateUser("u1")).toBe("/users/u1/deactivate");
  });

  it("use-case intake and config export endpoints match backend routes", () => {
    expect(ENDPOINTS.useCases).toBe("/plan/use-cases");
    expect(ENDPOINTS.configExport("yaml")).toBe("/admin/config/export?format=yaml");
  });
});

describe("Next runtime wiring", () => {
  it("proxies /api/v1 requests to the local backend", async () => {
    const rewritesFn = nextConfig.rewrites;
    expect(rewritesFn).toBeTypeOf("function");
    if (typeof rewritesFn !== "function") throw new Error("rewrites must be a function");
    const rewrites = await rewritesFn();
    expect(rewrites).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          source: "/api/v1/:path*",
          destination: "http://127.0.0.1:8000/api/v1/:path*",
        }),
      ]),
    );
  });

  it("allows Next hydration scripts in CSP while keeping external scripts blocked", () => {
    const req = new NextRequest("http://localhost:13000/");
    const csp = middleware(req).headers.get("Content-Security-Policy") ?? "";
    expect(csp).toContain("script-src");
    expect(csp).toContain("'unsafe-inline'");
    expect(csp).not.toContain("https:");
    expect(csp).not.toContain("*");
  });

  it("allows unsafe-eval only in development (Next dev bundles need it), never in production", () => {
    const req = new NextRequest("http://localhost:13000/");
    const original = process.env.NODE_ENV;
    try {
      vi.stubEnv("NODE_ENV", "development");
      expect(middleware(req).headers.get("Content-Security-Policy")).toContain("'unsafe-eval'");
      vi.stubEnv("NODE_ENV", "production");
      expect(middleware(req).headers.get("Content-Security-Policy")).not.toContain("'unsafe-eval'");
    } finally {
      vi.unstubAllEnvs();
      expect(process.env.NODE_ENV).toBe(original);
    }
  });
});

describe("no assistant-cloud dependency", () => {
  it("api-client does not import assistant-cloud", async () => {
    const source = await import("./api-client");
    // If assistant-cloud were imported, it would appear in the module
    const moduleKeys = Object.keys(source);
    expect(moduleKeys).not.toContain("assistantCloud");
    expect(moduleKeys).not.toContain("AssistantCloud");
  });
});

describe("Operate and Improve endpoints", () => {
  it("match backend routes", () => {
    expect(ENDPOINTS.incidents).toBe("/incidents");
    expect(ENDPOINTS.flywheel).toBe("/improve/flywheel");
  });
});

describe("Data and Build endpoints", () => {
  it("match backend routes", () => {
    expect(ENDPOINTS.dueReviews).toBe("/documents/reviews/due");
    expect(ENDPOINTS.modelRegistry).toBe("/model-registry");
  });
});
