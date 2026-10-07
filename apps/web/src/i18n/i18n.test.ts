import { describe, it, expect } from "vitest";
import { getDictionary, dictionaries } from "./index";
import type { Dictionary } from "./en";

function collectKeys(obj: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "object" && v !== null && !Array.isArray(v)) {
      keys.push(...collectKeys(v as Record<string, unknown>, path));
    } else {
      keys.push(path);
    }
  }
  return keys;
}

describe("i18n dictionaries", () => {
  it("EN and ID have the same keys", () => {
    const enKeys = collectKeys(dictionaries.en as unknown as Record<string, unknown>).sort();
    const idKeys = collectKeys(dictionaries.id as unknown as Record<string, unknown>).sort();
    expect(enKeys).toEqual(idKeys);
  });

  it("getDictionary returns correct locale", () => {
    const en = getDictionary("en");
    const id = getDictionary("id");
    expect(en.lang.current).toBe("English");
    expect(id.lang.current).toBe("Bahasa Indonesia");
  });

  it("EN nav labels are correct lifecycle order", () => {
    const en = getDictionary("en");
    const navLabels = [
      en.nav.plan,
      en.nav.data,
      en.nav.build,
      en.nav.test,
      en.nav.release,
      en.nav.operate,
      en.nav.improve,
    ];
    expect(navLabels).toEqual([
      "Plan",
      "Data",
      "Build",
      "Test",
      "Release",
      "Operate",
      "Improve",
    ]);
  });

  it("ID nav labels are real Indonesian", () => {
    const id = getDictionary("id");
    expect(id.nav.plan).toBe("Perencanaan");
    expect(id.nav.build).toBe("Pembangunan");
    expect(id.nav.test).toBe("Pengujian");
    expect(id.nav.operate).toBe("Operasi");
    expect(id.nav.improve).toBe("Peningkatan");
  });

  it("language switch labels point to the other locale", () => {
    const en = getDictionary("en");
    const id = getDictionary("id");
    expect(en.lang.switch).toBe("Bahasa Indonesia");
    expect(id.lang.switch).toBe("English");
  });

  it("no EN string values are empty", () => {
    const en = getDictionary("en");
    const enKeys = collectKeys(en as unknown as Record<string, unknown>);
    for (const key of enKeys) {
      const parts = key.split(".");
      let val: unknown = en;
      for (const p of parts) val = (val as Record<string, unknown>)[p];
      expect(val, `${key} should not be empty`).not.toBe("");
    }
  });

  it("no ID string values are empty", () => {
    const id = getDictionary("id");
    const idKeys = collectKeys(id as unknown as Record<string, unknown>);
    for (const key of idKeys) {
      const parts = key.split(".");
      let val: unknown = id;
      for (const p of parts) val = (val as Record<string, unknown>)[p];
      expect(val, `${key} should not be empty`).not.toBe("");
    }
  });
});
