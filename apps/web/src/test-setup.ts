import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  // The locale is persisted in localStorage; without this a language-switch test leaves Indonesian on for
  // every later test in the same file (order-dependent failures).
  try {
    globalThis.localStorage?.clear();
  } catch {
    // storage unavailable in this environment: nothing to reset
  }
});
