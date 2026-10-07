"use client";

import { useI18n } from "@/i18n/context";

// Chat screen shell — internal component boundary.
// If assistant-ui is added later (pinned, MIT, no cloud service),
// swap the internals to Thread/ThreadList; the API surface stays the same.
export function ChatScreen() {
  const { t } = useI18n();

  const scopes = [
    { value: "all", label: t.chat.scopeAll },
    { value: "my_documents", label: t.chat.scopeMyDocs },
    { value: "shared_with_me", label: t.chat.scopeShared },
    { value: "my_team", label: t.chat.scopeTeam },
    { value: "this_document", label: t.chat.scopeDocument },
  ];

  return (
    <section className="flex h-full flex-col">
      <h1 className="mb-4 text-2xl font-bold">{t.chat.title}</h1>

      <div className="flex flex-1 gap-4">
        {/* Conversation list */}
        <aside
          role="region"
          aria-label={t.chat.conversations}
          className="hidden w-64 flex-col border-r border-gray-200 pr-4 md:flex"
        >
          <button
            type="button"
            className="mb-3 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            {t.chat.newConversation}
          </button>
          <div className="flex-1 overflow-y-auto text-sm text-gray-500">
            {t.chat.noConversations}
          </div>
        </aside>

        {/* Chat area */}
        <div className="flex flex-1 flex-col">
          {/* Scope picker */}
          <div className="mb-3 flex items-center gap-2">
            <label htmlFor="scope-select" className="text-sm font-medium text-gray-700">
              {t.chat.scope}
            </label>
            <select
              id="scope-select"
              role="combobox"
              aria-label={t.chat.scope}
              className="rounded border border-gray-300 px-2 py-1 text-sm"
            >
              {scopes.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          {/* Messages area placeholder */}
          <div className="flex-1 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-4">
            <p className="text-center text-sm text-gray-400">
              {t.chat.noConversations}
            </p>
          </div>

          {/* Input area */}
          <div className="mt-3 flex gap-2">
            <label htmlFor="chat-input" className="sr-only">
              {t.chat.askPlaceholder}
            </label>
            <input
              id="chat-input"
              type="text"
              role="textbox"
              aria-label={t.chat.askPlaceholder}
              placeholder={t.chat.askPlaceholder}
              className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <button
              type="button"
              className="rounded bg-red-500 px-3 py-2 text-sm font-medium text-white hover:bg-red-600"
            >
              {t.chat.stop}
            </button>
          </div>

          {/* Feedback */}
          <div className="mt-2 flex items-center gap-2 text-sm text-gray-600">
            <span>{t.chat.feedback}</span>
            <button
              type="button"
              className="rounded border border-green-300 px-2 py-1 text-green-700 hover:bg-green-50"
            >
              {t.chat.thumbsUp}
            </button>
            <button
              type="button"
              className="rounded border border-red-300 px-2 py-1 text-red-700 hover:bg-red-50"
            >
              {t.chat.thumbsDown}
            </button>
          </div>

          {/* Citations */}
          <div
            role="region"
            aria-label={t.chat.citations}
            className="mt-3 rounded border border-gray-200 bg-white p-3"
          >
            <h3 className="mb-1 text-sm font-medium text-gray-700">
              {t.chat.citations}
            </h3>
            <p className="text-sm text-gray-400">{t.chat.noCitations}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
