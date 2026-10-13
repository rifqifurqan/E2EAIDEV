"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api } from "@/lib/api-client";
import { WhyItMattersPanel } from "./why-it-matters-panel";

function splitList(value: string, separators: RegExp): string[] {
  return value
    .split(separators)
    .map((part) => part.trim())
    .filter((part) => part !== "");
}

const INPUT = "mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm";
const LABEL = "text-sm font-medium text-gray-700";

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
      <WhyItMattersPanel stage="plan" />
    </section>
  );
}
