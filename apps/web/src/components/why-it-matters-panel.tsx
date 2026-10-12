"use client";

import { useI18n } from "@/i18n/context";

type StageKey =
  | "plan"
  | "data"
  | "build"
  | "test"
  | "release"
  | "operate"
  | "improve";

const FRAMEWORK_LINKS = [
  { key: "owasp", href: "https://owasp.org/www-project-top-10-for-large-language-model-applications/" },
  { key: "nist", href: "https://www.nist.gov/artificial-intelligence" },
  { key: "euAiAct", href: "https://artificialintelligenceact.eu/" },
  { key: "iso42001", href: "https://www.iso.org/standard/81230.html" },
  { key: "uuPdp", href: "https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022" },
] as const;

export function WhyItMattersPanel({ stage }: { stage: StageKey }) {
  const { t } = useI18n();
  const wim = t.whyItMatters;
  const title = wim.title;

  return (
    <section aria-label={title} className="mt-6 rounded-lg border border-blue-200 bg-blue-50 p-4">
      <h2 className="mb-2 text-lg font-semibold text-blue-900">{title}</h2>
      <p className="mb-4 text-sm text-blue-800">{wim.stages[stage]}</p>
      <h3 className="mb-2 text-sm font-medium text-blue-900">{wim.frameworks}</h3>
      <ul className="space-y-1">
        {FRAMEWORK_LINKS.map(({ key, href }) => (
          <li key={key}>
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-blue-700 underline hover:text-blue-900"
            >
              {wim[key]}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
