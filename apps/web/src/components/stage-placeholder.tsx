"use client";

import { useI18n } from "@/i18n/context";
import type { Dictionary } from "@/i18n";

type StageKey = "plan" | "data" | "build" | "test" | "release" | "operate" | "improve";

export function StagePlaceholder({ stage }: { stage: StageKey }) {
  const { t } = useI18n();
  const label = t.nav[stage];
  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{label}</h1>
      <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-gray-500">
        {label} stage — coming soon.
      </div>
    </section>
  );
}
