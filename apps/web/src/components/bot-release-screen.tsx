"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";
import { useLoadMore } from "@/lib/use-load-more";
import { LoadMore } from "./load-more";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PRINCIPAL_RE = /^(user|team|division|role|org):\S+$/;

export function BotReleaseScreen() {
  const { t } = useI18n();
  const [reloadKey, setReloadKey] = useState(0);
  const approvals = useAdminData(() => api.listBotApprovals(), reloadKey);
  const more = useLoadMore(
    approvals.kind === "ready" ? approvals.data.items : undefined,
    approvals.kind === "ready" ? approvals.data.next_cursor : null,
    api.listBotApprovalsPage,
  );
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [decisionFailed, setDecisionFailed] = useState(false);

  const [botId, setBotId] = useState("");
  const [rationale, setRationale] = useState("");
  const [requesting, setRequesting] = useState(false);
  const [requestFailed, setRequestFailed] = useState(false);

  const [showNewBot, setShowNewBot] = useState(false);
  const [botName, setBotName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createdName, setCreatedName] = useState<string | null>(null);
  const [createFailed, setCreateFailed] = useState(false);

  const [grantBotId, setGrantBotId] = useState("");
  const [principal, setPrincipal] = useState("");
  const [granting, setGranting] = useState(false);
  const [grantedPrincipal, setGrantedPrincipal] = useState<string | null>(null);
  const [grantFailed, setGrantFailed] = useState(false);

  async function grantAccess(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const target = principal.trim();
    if (!UUID_RE.test(grantBotId.trim()) || !PRINCIPAL_RE.test(target) || granting) return;
    setGrantFailed(false);
    setGrantedPrincipal(null);
    setGranting(true);
    try {
      const grant = await api.grantBotAccess(grantBotId.trim(), { principal: target, level: "user" });
      setPrincipal("");
      setGrantedPrincipal(grant.principal);
    } catch {
      setGrantFailed(true);
    } finally {
      setGranting(false);
    }
  }

  async function createBot(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = botName.trim();
    if (name === "" || creating) return;
    setCreateFailed(false);
    setCreatedName(null);
    setCreating(true);
    try {
      const bot = await api.createBot(name);
      setBotName("");
      setBotId(bot.id);
      setGrantBotId(bot.id);
      setCreatedName(bot.name);
    } catch {
      setCreateFailed(true);
    } finally {
      setCreating(false);
    }
  }

  async function requestApproval(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRequestFailed(false);
    setRequesting(true);
    try {
      await api.requestBotApproval(botId.trim(), rationale.trim() === "" ? undefined : rationale.trim());
      setBotId("");
      setRationale("");
    } catch {
      setRequestFailed(true);
    } finally {
      setRequesting(false);
      setReloadKey((key) => key + 1);
    }
  }

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
          onClick={() => setShowNewBot((open) => !open)}
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

      {showNewBot ? (
        <form onSubmit={createBot} className="mb-4 flex flex-wrap items-end gap-3 text-sm">
          <label htmlFor="new-bot-name">
            <span className="mr-1">{t.bots.botName}</span>
            <input
              id="new-bot-name"
              value={botName}
              onChange={(event) => setBotName(event.target.value)}
              className="rounded border border-gray-300 px-2 py-1 text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={creating || botName.trim() === ""}
            className="rounded border border-blue-400 px-3 py-1 text-sm text-blue-700 disabled:opacity-50"
          >
            {t.bots.createBot}
          </button>
          {createdName !== null ? (
            <p role="status" className="w-full text-sm text-green-700">
              {`${t.bots.botCreated}: ${createdName}`}
            </p>
          ) : null}
          {createFailed ? (
            <p role="alert" className="w-full text-sm text-red-700">
              {t.bots.createFailed}
            </p>
          ) : null}
        </form>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Bundles */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.bots.bundles}</h2>
          <p className="text-sm text-gray-500">{t.bots.noBots}</p>
        </div>

        {/* Grants */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.bots.grants}</h2>
          <form onSubmit={grantAccess} className="flex flex-col gap-2 text-sm">
            <label htmlFor="grant-bot-id">
              <span className="mr-1">{t.bots.grantBot}</span>
              <input
                id="grant-bot-id"
                value={grantBotId}
                onChange={(event) => setGrantBotId(event.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs"
              />
            </label>
            <label htmlFor="grant-principal">
              <span className="mr-1">{t.bots.grantPrincipal}</span>
              <input
                id="grant-principal"
                value={principal}
                onChange={(event) => setPrincipal(event.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs"
              />
            </label>
            <button
              type="submit"
              disabled={granting || !UUID_RE.test(grantBotId.trim()) || !PRINCIPAL_RE.test(principal.trim())}
              className="self-start rounded border border-blue-400 px-3 py-1 text-sm text-blue-700 disabled:opacity-50"
            >
              {t.bots.grantAccess}
            </button>
            {grantedPrincipal !== null ? (
              <p role="status" className="text-sm text-green-700">
                {`${t.bots.accessGranted}: ${grantedPrincipal}`}
              </p>
            ) : null}
            {grantFailed ? (
              <p role="alert" className="text-sm text-red-700">
                {t.bots.grantFailed}
              </p>
            ) : null}
          </form>
        </div>

        {/* Scope */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.bots.scope}</h2>
          <p className="text-sm text-gray-500">{t.bots.noBots}</p>
        </div>
      </div>

      <div className="mt-6 rounded-lg border border-gray-200 p-4">
        <h2 className="mb-3 text-lg font-semibold">{t.bots.approvalsTitle}</h2>
        <form onSubmit={requestApproval} className="mb-3 flex flex-wrap items-end gap-3 text-sm">
          <label htmlFor="approval-bot-id">
            <span className="mr-1">{t.bots.botId}</span>
            <input
              id="approval-bot-id"
              value={botId}
              onChange={(event) => setBotId(event.target.value)}
              className="rounded border border-gray-300 px-2 py-1 font-mono text-sm"
            />
          </label>
          <label htmlFor="approval-rationale">
            <span className="mr-1">{t.bots.rationale}</span>
            <input
              id="approval-rationale"
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              className="rounded border border-gray-300 px-2 py-1 text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={requesting || !UUID_RE.test(botId.trim())}
            className="rounded border border-blue-400 px-3 py-1 text-sm text-blue-700 disabled:opacity-50"
          >
            {t.bots.requestApproval}
          </button>
          {requestFailed ? (
            <p role="alert" className="w-full text-sm text-red-700">
              {t.bots.requestFailed}
            </p>
          ) : null}
        </form>
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
          more.items.length === 0 ? (
            <p className="text-sm text-gray-500">{t.bots.approvalsEmpty}</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {more.items.map((approval) => (
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
        {approvals.kind === "ready" ? (
          <LoadMore hasMore={more.hasMore} busy={more.busy} failed={more.failed} onLoadMore={more.loadMore} />
        ) : null}
      </div>
    </section>
  );
}
