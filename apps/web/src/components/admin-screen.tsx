"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type OrgSnapshot } from "@/lib/api-client";
import { useAdminData } from "@/lib/use-admin-data";

const RUNBOOK_BASE = "/docs/runbooks";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const RUNBOOK_FILES: { key: keyof typeof import("@/i18n/en").default.admin.runbookLinks; file: string }[] = [
  { key: "serviceDown", file: "service-down" },
  { key: "restoreBackup", file: "restore-from-backup" },
  { key: "modelFailing", file: "model-endpoint-failing" },
  { key: "vectorDegraded", file: "vector-store-degraded" },
  { key: "permissionLag", file: "permission-sync-lag" },
  { key: "diskFull", file: "disk-full" },
  { key: "leakedKey", file: "leaked-key" },
];

function OrgForms({ snapshot, onCreated }: { snapshot: OrgSnapshot; onCreated: () => void }) {
  const { t } = useI18n();
  const [divisionName, setDivisionName] = useState("");
  const [teamName, setTeamName] = useState("");
  const [teamDivision, setTeamDivision] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<"division" | "team" | null>(null);

  async function run(kind: "division" | "team", action: () => Promise<unknown>, reset: () => void) {
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      await action();
      reset();
      onCreated();
    } catch {
      setError(kind);
    } finally {
      setBusy(false);
    }
  }

  const divisionTrimmed = divisionName.trim();
  const teamTrimmed = teamName.trim();

  return (
    <div className="mb-4 grid gap-4 md:grid-cols-2 text-sm">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!divisionTrimmed) return;
          void run(
            "division",
            () => api.createDivision({ org_id: snapshot.org_id, name: divisionTrimmed }),
            () => setDivisionName(""),
          );
        }}
        className="flex flex-col gap-2"
      >
        <label htmlFor="org-division-name">
          <span className="mr-1">{t.admin.divisionName}</span>
          <input
            id="org-division-name"
            value={divisionName}
            onChange={(event) => setDivisionName(event.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1"
          />
        </label>
        <button
          type="submit"
          disabled={busy || !divisionTrimmed}
          className="self-start rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50"
        >
          {t.admin.addDivision}
        </button>
        {error === "division" ? (
          <p role="alert" className="text-red-700">
            {t.admin.divisionFailed}
          </p>
        ) : null}
      </form>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!teamTrimmed || !teamDivision) return;
          void run(
            "team",
            () => api.createTeam({ division_id: teamDivision, name: teamTrimmed }),
            () => setTeamName(""),
          );
        }}
        className="flex flex-col gap-2"
      >
        <label htmlFor="org-team-name">
          <span className="mr-1">{t.admin.teamName}</span>
          <input
            id="org-team-name"
            value={teamName}
            onChange={(event) => setTeamName(event.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1"
          />
        </label>
        <label htmlFor="org-team-division">
          <span className="mr-1">{t.admin.teamDivision}</span>
          <select
            id="org-team-division"
            value={teamDivision}
            onChange={(event) => setTeamDivision(event.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1"
          >
            <option value="" />
            {snapshot.divisions.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          disabled={busy || !teamTrimmed || !teamDivision}
          className="self-start rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50"
        >
          {t.admin.addTeam}
        </button>
        {error === "team" ? (
          <p role="alert" className="text-red-700">
            {t.admin.teamFailed}
          </p>
        ) : null}
      </form>
    </div>
  );
}

const ROLE_NAMES = ["admin", "ai_engineer", "evaluator", "compliance", "business_user"] as const;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type AccessOutcome = "user-failed" | "member-added" | "member-failed" | "role-granted" | "role-failed" | null;

function OrgAccessForms({ snapshot, onChanged }: { snapshot: OrgSnapshot; onChanged: () => void }) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [userDivision, setUserDivision] = useState("");
  const [memberTeam, setMemberTeam] = useState("");
  const [memberUser, setMemberUser] = useState("");
  const [roleUser, setRoleUser] = useState("");
  const [role, setRole] = useState("");
  const [adminConfirmed, setAdminConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<AccessOutcome>(null);

  const activeUsers = snapshot.users.filter((u) => u.status !== "disabled");
  const emailTrimmed = email.trim();
  const nameTrimmed = displayName.trim();
  const userValid = EMAIL_RE.test(emailTrimmed) && nameTrimmed.length > 0;
  const roleValid = roleUser !== "" && role !== "" && (role !== "admin" || adminConfirmed);

  async function run(action: () => Promise<unknown>, ok: AccessOutcome, failed: AccessOutcome, reset: () => void) {
    if (busy) return;
    setOutcome(null);
    setBusy(true);
    try {
      await action();
      reset();
      setOutcome(ok);
      onChanged();
    } catch {
      setOutcome(failed);
    } finally {
      setBusy(false);
    }
  }

  const field = "w-full rounded border border-gray-300 px-2 py-1";
  const button = "self-start rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50";

  return (
    <div className="mb-4 grid gap-4 md:grid-cols-3 text-sm">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!userValid) return;
          void run(
            () =>
              api.createOrgUser({
                org_id: snapshot.org_id,
                email: emailTrimmed,
                display_name: nameTrimmed,
                ...(userDivision ? { division_id: userDivision } : {}),
              }),
            null,
            "user-failed",
            () => {
              setEmail("");
              setDisplayName("");
              setUserDivision("");
            },
          );
        }}
        className="flex flex-col gap-2"
      >
        <label htmlFor="org-user-email">
          <span className="mr-1">{t.admin.userEmail}</span>
          <input id="org-user-email" value={email} onChange={(e) => setEmail(e.target.value)} className={field} />
        </label>
        <label htmlFor="org-user-name">
          <span className="mr-1">{t.admin.userDisplayName}</span>
          <input id="org-user-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} className={field} />
        </label>
        <label htmlFor="org-user-division">
          <span className="mr-1">{t.admin.userDivision}</span>
          <select id="org-user-division" value={userDivision} onChange={(e) => setUserDivision(e.target.value)} className={field}>
            <option value="" />
            {snapshot.divisions.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={busy || !userValid} className={button}>
          {t.admin.addUser}
        </button>
        {outcome === "user-failed" ? (
          <p role="alert" className="text-red-700">
            {t.admin.userFailed}
          </p>
        ) : null}
      </form>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!memberTeam || !memberUser) return;
          void run(
            () => api.addTeamMember({ team_id: memberTeam, user_id: memberUser }),
            "member-added",
            "member-failed",
            () => setMemberUser(""),
          );
        }}
        className="flex flex-col gap-2"
      >
        <label htmlFor="org-member-team">
          <span className="mr-1">{t.admin.memberTeam}</span>
          <select id="org-member-team" value={memberTeam} onChange={(e) => setMemberTeam(e.target.value)} className={field}>
            <option value="" />
            {snapshot.teams.map((team) => (
              <option key={team.id} value={team.id}>
                {team.name}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="org-member-user">
          <span className="mr-1">{t.admin.memberUser}</span>
          <select id="org-member-user" value={memberUser} onChange={(e) => setMemberUser(e.target.value)} className={field}>
            <option value="" />
            {activeUsers.map((u) => (
              <option key={u.id} value={u.id}>
                {u.display_name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={busy || !memberTeam || !memberUser} className={button}>
          {t.admin.addToTeam}
        </button>
        {outcome === "member-added" ? (
          <p role="status" className="text-green-700">
            {t.admin.memberAdded}
          </p>
        ) : null}
        {outcome === "member-failed" ? (
          <p role="alert" className="text-red-700">
            {t.admin.memberFailed}
          </p>
        ) : null}
      </form>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!roleValid) return;
          void run(
            () => api.grantOrgRole({ user_id: roleUser, role_name: role }),
            "role-granted",
            "role-failed",
            () => {
              setAdminConfirmed(false);
              setRole("");
            },
          );
        }}
        className="flex flex-col gap-2"
      >
        <label htmlFor="org-role-user">
          <span className="mr-1">{t.admin.roleUser}</span>
          <select id="org-role-user" value={roleUser} onChange={(e) => setRoleUser(e.target.value)} className={field}>
            <option value="" />
            {activeUsers.map((u) => (
              <option key={u.id} value={u.id}>
                {u.display_name}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="org-role">
          <span className="mr-1">{t.admin.role}</span>
          <select
            id="org-role"
            value={role}
            onChange={(e) => {
              setRole(e.target.value);
              setAdminConfirmed(false);
            }}
            className={field}
          >
            <option value="" />
            {ROLE_NAMES.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        {role === "admin" ? (
          <label htmlFor="org-role-admin-confirm" className="flex items-center gap-2">
            <input
              id="org-role-admin-confirm"
              type="checkbox"
              checked={adminConfirmed}
              onChange={(e) => setAdminConfirmed(e.target.checked)}
            />
            <span>{t.admin.adminRoleConfirm}</span>
          </label>
        ) : null}
        <button type="submit" disabled={busy || !roleValid} className={button}>
          {t.admin.grantRole}
        </button>
        {outcome === "role-granted" ? (
          <p role="status" className="text-green-700">
            {t.admin.roleGranted}
          </p>
        ) : null}
        {outcome === "role-failed" ? (
          <p role="alert" className="text-red-700">
            {t.admin.roleFailed}
          </p>
        ) : null}
      </form>
    </div>
  );
}

export function AdminScreen() {
  const { t } = useI18n();
  const [showDeactivate, setShowDeactivate] = useState(false);
  const [targetId, setTargetId] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [orgReload, setOrgReload] = useState(0);
  const org = useAdminData<OrgSnapshot>(() => api.getOrgSnapshot(), orgReload);

  const target = targetId.trim();
  const owner = ownerId.trim();
  // Both must be UUIDs and different: assets cannot be transferred to the user being deactivated.
  const valid = UUID_RE.test(target) && UUID_RE.test(owner) && target.toLowerCase() !== owner.toLowerCase();

  async function deactivate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!valid || busy) return;
    setFailed(false);
    setSummary(null);
    setBusy(true);
    try {
      const result = await api.deactivateUser(target, { transfer_to_id: owner });
      setTargetId("");
      setOwnerId("");
      setSummary(
        `${t.admin.userDeactivated}: ${result.documents_transferred} ${t.admin.documentsWord}, ` +
          `${result.folders_transferred} ${t.admin.foldersWord}, ${result.sessions_purged} ${t.admin.sessionsWord}`,
      );
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">{t.admin.title}</h1>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Configuration-as-code export */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.admin.configExport}</h2>
          <p className="mb-3 text-sm text-gray-600">
            {t.admin.configExportDescription}
          </p>
          <a
            href="/api/v1/admin/config/export?format=yaml"
            download="e2eai.yaml"
            className="inline-flex rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            {t.admin.exportConfiguration}
          </a>
        </div>

        {/* Offboarding */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.admin.offboarding}</h2>
          <p className="mb-3 text-sm text-gray-600">
            {t.admin.transferTo}
          </p>
          <button
            type="button"
            onClick={() => setShowDeactivate((open) => !open)}
            className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            {t.admin.deactivateUser}
          </button>
          {showDeactivate ? (
            <form onSubmit={deactivate} className="mt-3 flex flex-col gap-2 text-sm">
              <label htmlFor="deactivate-target">
                <span className="mr-1">{t.admin.deactivateTarget}</span>
                <input
                  id="deactivate-target"
                  value={targetId}
                  onChange={(event) => setTargetId(event.target.value)}
                  className="w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs"
                />
              </label>
              <label htmlFor="deactivate-owner">
                <span className="mr-1">{t.admin.newOwner}</span>
                <input
                  id="deactivate-owner"
                  value={ownerId}
                  onChange={(event) => setOwnerId(event.target.value)}
                  className="w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs"
                />
              </label>
              <button
                type="submit"
                disabled={busy || !valid}
                className="self-start rounded border border-red-500 px-3 py-1 text-sm text-red-700 disabled:opacity-50"
              >
                {t.admin.confirmDeactivation}
              </button>
              {summary !== null ? (
                <p role="status" className="text-sm text-green-700">
                  {summary}
                </p>
              ) : null}
              {failed ? (
                <p role="alert" className="text-sm text-red-700">
                  {t.admin.deactivateFailed}
                </p>
              ) : null}
            </form>
          ) : null}
        </div>

        {/* Organization */}
        <section aria-labelledby="admin-org-title" className="rounded-lg border border-gray-200 p-4 lg:col-span-2">
          <h2 id="admin-org-title" className="mb-3 text-lg font-semibold">
            {t.admin.organization}
          </h2>
          {org.kind === "loading" ? <p className="text-sm text-gray-600">{t.admin.orgLoading}</p> : null}
          {org.kind === "forbidden" ? (
            <p role="alert" className="text-sm text-amber-700">
              {t.admin.orgAdminOnly}
            </p>
          ) : null}
          {org.kind === "error" ? (
            <p role="alert" className="text-sm text-red-700">
              {t.admin.orgLoadFailed}
            </p>
          ) : null}
          {org.kind === "ready" ? <OrgForms snapshot={org.data} onCreated={() => setOrgReload((key) => key + 1)} /> : null}
          {org.kind === "ready" ? <OrgAccessForms snapshot={org.data} onChanged={() => setOrgReload((key) => key + 1)} /> : null}
          {org.kind === "ready" ? (
            <div className="grid gap-4 md:grid-cols-3 text-sm">
              <div>
                <h3 className="mb-1 font-medium">{t.admin.divisions}</h3>
                {org.data.divisions.length === 0 ? (
                  <p className="text-gray-600">{t.admin.orgEmpty}</p>
                ) : (
                  <ul className="space-y-1">
                    {org.data.divisions.map((d) => (
                      <li key={d.id}>{d.name}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <h3 className="mb-1 font-medium">{t.admin.teams}</h3>
                {org.data.teams.length === 0 ? (
                  <p className="text-gray-600">{t.admin.orgEmpty}</p>
                ) : (
                  <ul className="space-y-1">
                    {org.data.teams.map((team) => (
                      <li key={team.id}>{team.name}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <h3 className="mb-1 font-medium">{t.admin.users}</h3>
                {org.data.users.length === 0 ? (
                  <p className="text-gray-600">{t.admin.orgEmpty}</p>
                ) : (
                  <ul className="space-y-1">
                    {org.data.users.map((u) => (
                      <li key={u.id}>
                        {u.display_name} <span className="text-gray-600">({u.email})</span>
                        {u.status === "disabled" ? <span className="ml-1 text-red-700">[{t.admin.statusDisabled}]</span> : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : null}
        </section>

        {/* Runbooks */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-semibold">{t.admin.runbooks}</h2>
          <ul className="space-y-2">
            {RUNBOOK_FILES.map(({ key, file }) => (
              <li key={key}>
                <a
                  href={`${RUNBOOK_BASE}/${file}`}
                  className="text-sm text-blue-600 hover:underline"
                >
                  {t.admin.runbookLinks[key]}
                </a>
              </li>
            ))}
          </ul>
        </div>

      </div>
    </section>
  );
}
