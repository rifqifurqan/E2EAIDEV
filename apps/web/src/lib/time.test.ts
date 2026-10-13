// @vitest-environment node
import { describe, expect, it } from "vitest";

import { DEFAULT_TIME_ZONE, formatTimestamp } from "./time";

describe("NFR-20 timestamps: stored in UTC, shown in the user's time zone", () => {
  it("defaults to Asia/Jakarta (UTC+7)", () => {
    expect(DEFAULT_TIME_ZONE).toBe("Asia/Jakarta");
    expect(formatTimestamp("2026-10-13T00:30:00Z", undefined, "en")).toBe("13 Oct 2026, 07:30");
  });

  it("uses the user's own zone when given", () => {
    expect(formatTimestamp("2026-01-01T12:00:00Z", "Asia/Jayapura", "en")).toBe("1 Jan 2026, 21:00");
  });

  it("treats a timestamp without offset as UTC", () => {
    expect(formatTimestamp("2026-10-13T00:30:00", "Asia/Jakarta", "en")).toBe("13 Oct 2026, 07:30");
  });

  it("falls back to the default zone for an invalid zone, and to a dash for invalid input", () => {
    expect(formatTimestamp("2026-10-13T00:30:00Z", "Mars/Olympus", "en")).toBe("13 Oct 2026, 07:30");
    expect(formatTimestamp("not-a-date", "Asia/Jakarta", "en")).toBe("—");
    expect(formatTimestamp(null, "Asia/Jakarta", "en")).toBe("—");
  });

  it("formats in Indonesian", () => {
    expect(formatTimestamp("2026-10-13T00:30:00Z", "Asia/Jakarta", "id")).toMatch(/^13 Okt(ober)? 2026/);
  });
});
