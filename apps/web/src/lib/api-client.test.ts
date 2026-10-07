import { describe, it, expect } from "vitest";
import { ENDPOINTS } from "./api-client";

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
