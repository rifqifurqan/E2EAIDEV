"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";

export function BotReleaseScreen() {
  const { t } = useI18n();
  const [reloadKey, setReloadKey] = useState(0);
  const approvals = useAdminData(() => api.listBotApprovals(), reloadKey);
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [decisionFailed, setDecisionFailed] = useState(false);

  async function decide(id: string, decision: "approved" | "rejected") {
    setDecisionFailed(false);
    setDecidingId(id);
    try {
      await api.decideBotApproval(id, decision);
    } catch {
      setDecisionFailed(true);
    } finally {
      setDecidingId(null);
      setReloadKey((key) => key + 1);
    }
  }

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.bots.title}</h1>

      <div className="mb-4 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {t.bots.newBot}
        </button>
        <button
          type="button"
          className="rounded border border-blue-300 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50"
        >
          {t.bots.release}
        </button>
        <button
          type="button"
          className="rounded border border-orange-300 px-4 py-2 text-sm font-medium text-orange-700 hover:bg-orange-50"
        >
          {t.bots.rollback}
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Bundles */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.bots.bundles}</h2>
          <p className="text-sm text-gray-500">{t.bots.noBots}</p>
        </div>

        {/* Grants */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.bots.grants}</h2>
          <p className="text-sm text-gray-500">{t.bots.noBots}</p>
        </div>

        {/* Scope */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.bots.scope}</h2>
          <p className="text-sm text-gray-500">{t.bots.noBots}</p>
        </div>
      </div>

      <div className="mt-6 rounded-lg border border-gray-200 p-4">
        <h2 className="mb-3 text-lg font-semibold">{t.bots.approvalsTitle}</h2>
        {approvals.kind === "loading" ? <p>{t.bots.approvalsLoading}</p> : null}
        {approvals.kind === "forbidden" ? (
          <p role="alert" className="rounded border border-yellow-300 bg-yellow-50 p-3 text-sm">
            {t.bots.approvalsSignIn}
          </p>
        ) : null}
        {approvals.kind === "error" ? (
          <p role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm">
            {t.bots.approvalsLoadFailed}
          </p>
        ) : null}
        {decisionFailed ? (
          <p role="alert" className="mb-2 rounded border border-red-300 bg-red-50 p-3 text-sm">
            {t.bots.decisionFailed}
          </p>
        ) : null}
        {approvals.kind === "ready" ? (
          approvals.data.items.length === 0 ? (
            <p className="text-sm text-gray-500">{t.bots.approvalsEmpty}</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {approvals.data.items.map((approval) => (
                <li key={approval.id} className="rounded border border-gray-200 p-2">
                  <span className="mr-2">{approval.approval_type}</span>
                  <span className="mr-2 text-xs text-gray-500">{`${t.bots.risk}: ${approval.risk_tier}`}</span>
                  <span className="font-mono text-xs">{approval.status}</span>
                  {approval.status === "pending" ? (
                    <span className="ml-3 inline-flex gap-2">
                      <button
                        type="button"
                        disabled={decidingId === approval.id}
                        onClick={() => decide(approval.id, "approved")}
                        className="rounded border border-green-400 px-2 py-0.5 text-xs text-green-700 disabled:opacity-50"
                      >
                        {t.bots.approve}
                      </button>
                      <button
                        type="button"
                        disabled={decidingId === approval.id}
                        onClick={() => decide(approval.id, "rejected")}
                        className="rounded border border-red-400 px-2 py-0.5 text-xs text-red-700 disabled:opacity-50"
                      >
                        {t.bots.reject}
                      </button>
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )
        ) : null}
      </div>
    </section>
  );
}
