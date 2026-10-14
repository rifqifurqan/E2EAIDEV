"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type AIInventoryEntry, type EuAiActTier } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { useLoadMore } from "@/lib/use-load-more";
import { LoadMore } from "./load-more";
import { WhyItMattersPanel } from "./why-it-matters-panel";

function splitList(value: string, separators: RegExp): string[] {
  return value
    .split(separators)
    .map((part) => part.trim())
    .filter((part) => part !== "");
}

const INPUT = "mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm";
const LABEL = "text-sm font-medium text-gray-700";

function InventoryRow({ entry }: { entry: AIInventoryEntry }) {
  return (
    <li className="rounded border border-gray-200 p-2">
      <span className="mr-2 font-medium">{entry.name}</span>
      <span className="font-mono text-xs text-gray-500">
        {entry.kind} · {entry.risk_tier} · {entry.status} · {entry.approval_status}
      </span>
    </li>
  );
}

export function PlanScreen() {
  const { t } = useI18n();
  const [title, setTitle] = useState("");
  const [problem, setProblem] = useState("");
  const [users, setUsers] = useState("");
  const [taskSuccess, setTaskSuccess] = useState("");
  const [deflection, setDeflection] = useState("");
  const [timeSaved, setTimeSaved] = useState("");
  const [dataSources, setDataSources] = useState("");
  const [systems, setSystems] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [riskBotId, setRiskBotId] = useState("");
  const [riskTier, setRiskTier] = useState<EuAiActTier>("minimal");
  const [nistGovern, setNistGovern] = useState("");
  const [nistMeasure, setNistMeasure] = useState("");
  const [pdpImpact, setPdpImpact] = useState("");
  const [riskBusy, setRiskBusy] = useState(false);
  const [riskResult, setRiskResult] = useState<string | null>(null);
  const [riskFailed, setRiskFailed] = useState(false);
  const inventory = useAdminData(() => api.listInventory());
  const moreInventory = useLoadMore(
    inventory.kind === "ready" ? inventory.data.items : undefined,
    inventory.kind === "ready" ? inventory.data.next_cursor : null,
    async (cursor: string) => {
      const page = await api.listInventoryPage(cursor);
      return { items: page.items, next_cursor: page.next_cursor };
    },
  );

  const userList = splitList(users, /,/);
  const ready =
    title.trim() !== "" &&
    problem.trim() !== "" &&
    userList.length > 0 &&
    taskSuccess.trim() !== "" &&
    deflection.trim() !== "" &&
    timeSaved.trim() !== "";

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || busy) return;
    setBusy(true);
    setFailed(false);
    setResult(null);
    try {
      const created = await api.createUseCase({
        title: title.trim(),
        problem: problem.trim(),
        users: userList,
        success_metrics: {
          task_success: taskSuccess.trim(),
          deflection: deflection.trim(),
          time_saved: timeSaved.trim(),
        },
        data_sources: splitList(dataSources, /[,;]/),
        systems_to_integrate: splitList(systems, /[,;]/),
      });
      setResult(`${t.plan.submitted}: ${created.title} (${created.status})`);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  async function classifyRisk(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (riskBotId.trim() === "" || riskBusy) return;
    setRiskBusy(true);
    setRiskFailed(false);
    setRiskResult(null);
    try {
      const classification = await api.classifyBotRisk(riskBotId.trim(), {
        eu_ai_act_tier: riskTier,
        nist_ai_rmf_profile: {
          ...(nistGovern.trim() ? { govern: nistGovern.trim() } : {}),
          ...(nistMeasure.trim() ? { measure: nistMeasure.trim() } : {}),
        },
        uu_pdp_data_impact: pdpImpact.trim(),
      });
      setRiskResult(`${t.plan.riskClassified}: ${classification.eu_ai_act_tier}`);
    } catch {
      setRiskFailed(true);
    } finally {
      setRiskBusy(false);
    }
  }

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.nav.plan}</h1>
      <form onSubmit={submit} className="mb-6 rounded-lg border border-gray-200 bg-white p-4 text-left">
        <h2 className="mb-3 text-lg font-semibold text-gray-900">{t.plan.title}</h2>
        <div className="grid gap-3 md:grid-cols-2">
          <label className={LABEL} htmlFor="uc-title">
            {t.plan.useCaseTitle}
            <input id="uc-title" value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT} />
          </label>
          <label className={LABEL} htmlFor="uc-users">
            {t.plan.users}
            <input id="uc-users" value={users} onChange={(e) => setUsers(e.target.value)} className={INPUT} />
          </label>
          <label className={`${LABEL} md:col-span-2`} htmlFor="uc-problem">
            {t.plan.problem}
            <textarea id="uc-problem" value={problem} onChange={(e) => setProblem(e.target.value)} className={INPUT} />
          </label>
          <label className={LABEL} htmlFor="uc-task">
            {t.plan.taskSuccess}
            <input id="uc-task" value={taskSuccess} onChange={(e) => setTaskSuccess(e.target.value)} className={INPUT} />
          </label>
          <label className={LABEL} htmlFor="uc-deflection">
            {t.plan.deflection}
            <input id="uc-deflection" value={deflection} onChange={(e) => setDeflection(e.target.value)} className={INPUT} />
          </label>
          <label className={LABEL} htmlFor="uc-time">
            {t.plan.timeSaved}
            <input id="uc-time" value={timeSaved} onChange={(e) => setTimeSaved(e.target.value)} className={INPUT} />
          </label>
          <label className={LABEL} htmlFor="uc-sources">
            {t.plan.dataSources}
            <input id="uc-sources" value={dataSources} onChange={(e) => setDataSources(e.target.value)} className={INPUT} />
          </label>
          <label className={`${LABEL} md:col-span-2`} htmlFor="uc-systems">
            {t.plan.systems}
            <input id="uc-systems" value={systems} onChange={(e) => setSystems(e.target.value)} className={INPUT} />
          </label>
        </div>
        <button
          type="submit"
          disabled={busy || !ready}
          className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {t.plan.submit}
        </button>
        {result ? (
          <p role="status" className="mt-3 text-sm text-gray-700">
            {result}
          </p>
        ) : null}
        {failed ? (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {t.plan.submitFailed}
          </p>
        ) : null}
      </form>
      <form onSubmit={classifyRisk} className="mb-6 rounded-lg border border-gray-200 bg-white p-4 text-left">
        <h2 className="mb-3 text-lg font-semibold text-gray-900">{t.plan.riskTitle}</h2>
        <div className="grid gap-3 md:grid-cols-2">
          <label className={LABEL} htmlFor="risk-bot-id">
            {t.plan.riskBotId}
            <input
              id="risk-bot-id"
              value={riskBotId}
              onChange={(e) => setRiskBotId(e.target.value)}
              className={INPUT}
            />
          </label>
          <label className={LABEL} htmlFor="risk-tier">
            {t.plan.riskTier}
            <select
              id="risk-tier"
              value={riskTier}
              onChange={(e) => setRiskTier(e.target.value as EuAiActTier)}
              className={INPUT}
            >
              <option value="minimal">{t.plan.tierMinimal}</option>
              <option value="limited">{t.plan.tierLimited}</option>
              <option value="high">{t.plan.tierHigh}</option>
              <option value="unacceptable">{t.plan.tierUnacceptable}</option>
            </select>
          </label>
          <label className={LABEL} htmlFor="risk-nist-govern">
            {t.plan.nistGovern}
            <input
              id="risk-nist-govern"
              value={nistGovern}
              onChange={(e) => setNistGovern(e.target.value)}
              className={INPUT}
            />
          </label>
          <label className={LABEL} htmlFor="risk-nist-measure">
            {t.plan.nistMeasure}
            <input
              id="risk-nist-measure"
              value={nistMeasure}
              onChange={(e) => setNistMeasure(e.target.value)}
              className={INPUT}
            />
          </label>
          <label className={`${LABEL} md:col-span-2`} htmlFor="risk-pdp-impact">
            {t.plan.pdpImpact}
            <textarea
              id="risk-pdp-impact"
              value={pdpImpact}
              onChange={(e) => setPdpImpact(e.target.value)}
              className={INPUT}
            />
          </label>
        </div>
        <button
          type="submit"
          disabled={riskBusy || riskBotId.trim() === ""}
          className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {t.plan.classifyRisk}
        </button>
        {riskResult ? (
          <p role="status" className="mt-3 text-sm text-gray-700">
            {riskResult}
          </p>
        ) : null}
        {riskFailed ? (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {t.plan.classifyFailed}
          </p>
        ) : null}
      </form>
      <section className="mb-6 rounded-lg border border-gray-200 bg-white p-4 text-left">
        <h2 className="mb-3 text-lg font-semibold text-gray-900">{t.plan.inventoryTitle}</h2>
        {inventory.kind === "loading" ? <p className="text-sm text-gray-600">{t.plan.inventoryLoading}</p> : null}
        {inventory.kind === "forbidden" ? (
          <p role="alert" className="text-sm text-amber-700">
            {t.plan.inventoryAdminOnly}
          </p>
        ) : null}
        {inventory.kind === "error" ? (
          <p role="alert" className="text-sm text-red-700">
            {t.plan.inventoryLoadFailed}
          </p>
        ) : null}
        {inventory.kind === "ready" ? (
          moreInventory.items.length === 0 ? (
            <p className="text-sm text-gray-600">{t.plan.inventoryEmpty}</p>
          ) : (
            <>
              <ul className="space-y-2">
                {moreInventory.items.map((entry) => (
                  <InventoryRow key={entry.id} entry={entry} />
                ))}
              </ul>
              <LoadMore
                hasMore={moreInventory.hasMore}
                busy={moreInventory.busy}
                failed={moreInventory.failed}
                onLoadMore={moreInventory.loadMore}
              />
            </>
          )
        ) : null}
      </section>
      <WhyItMattersPanel stage="plan" />
    </section>
  );
}
