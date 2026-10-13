"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api } from "@/lib/api-client";
import { WhyItMattersPanel } from "./why-it-matters-panel";

type StageKey = "plan" | "data" | "build" | "test" | "release" | "operate" | "improve";

function UseCaseIntakeForm() {
  const [title, setTitle] = useState("");
  const [businessOwner, setBusinessOwner] = useState("");
  const [purpose, setPurpose] = useState("");
  const [riskTier, setRiskTier] = useState("limited");
  const [status, setStatus] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("Submitting...");
    try {
      const result = await api.createUseCase({
        title,
        business_owner: businessOwner,
        purpose,
        risk_tier: riskTier,
      });
      setStatus(`Use case ${result.title} ${result.status}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Use-case submission failed");
    }
  }

  return (
    <form onSubmit={submit} className="mb-6 rounded-lg border border-gray-200 bg-white p-4 text-left">
      <h2 className="mb-3 text-lg font-semibold text-gray-900">Use-case intake</h2>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm font-medium text-gray-700" htmlFor="use-case-title">
          Use-case title
          <input
            id="use-case-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            required
            className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-gray-700" htmlFor="business-owner">
          Business owner
          <input
            id="business-owner"
            value={businessOwner}
            onChange={(event) => setBusinessOwner(event.target.value)}
            required
            className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-gray-700 md:col-span-2" htmlFor="use-case-purpose">
          Purpose
          <textarea
            id="use-case-purpose"
            value={purpose}
            onChange={(event) => setPurpose(event.target.value)}
            required
            className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-gray-700" htmlFor="risk-tier">
          Risk tier
          <select
            id="risk-tier"
            value={riskTier}
            onChange={(event) => setRiskTier(event.target.value)}
            className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="minimal">Minimal</option>
            <option value="limited">Limited</option>
            <option value="high">High</option>
          </select>
        </label>
      </div>
      <button
        type="submit"
        className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        Submit use case
      </button>
      {status ? <p role="status" className="mt-3 text-sm text-gray-700">{status}</p> : null}
    </form>
  );
}

export function StagePlaceholder({ stage }: { stage: StageKey }) {
  const { t } = useI18n();
  const label = t.nav[stage];
  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{label}</h1>
      {stage === "plan" ? (
        <UseCaseIntakeForm />
      ) : (
        <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-gray-500">
          {label} stage — coming soon.
        </div>
      )}
      <WhyItMattersPanel stage={stage} />
    </section>
  );
}
