"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type ChatScope, type Citation } from "@/lib/api-client";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

// Chat screen shell — internal component boundary.
// If assistant-ui is added later (pinned, MIT, no cloud service),
// swap the internals to Thread/ThreadList; the API surface stays the same.
export function ChatScreen() {
  const { t } = useI18n();
  const [scope, setScope] = useState<ChatScope>("all");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [sending, setSending] = useState(false);

  const scopes: { value: ChatScope; label: string }[] = [
    { value: "all", label: t.chat.scopeAll },
    { value: "my_documents", label: t.chat.scopeMyDocs },
    { value: "shared_with_me", label: t.chat.scopeShared },
    { value: "my_team", label: t.chat.scopeTeam },
    { value: "this_document", label: t.chat.scopeDocument },
  ];

  async function handleNewConversation() {
    setStatus("");
    try {
      const conv = await api.createConversation(t.chat.newConversation);
      setConversations((items) => [conv.id, ...items]);
      setMessages([]);
      setQuestion("");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not create conversation");
    }
  }

  async function handleSend() {
    const trimmed = question.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setStatus("");
    setMessages((items) => [...items, { role: "user", content: trimmed }]);
    setQuestion("");
    try {
      const response = await api.ask(trimmed, scope, undefined);
      setMessages((items) => [
        ...items,
        { role: "assistant", content: response.answer, citations: response.citations ?? [] },
      ]);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Chat request failed");
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="flex h-full flex-col">
      <h1 className="mb-4 text-2xl font-bold">{t.chat.title}</h1>

      <div className="flex flex-1 gap-4">
        <aside
          role="region"
          aria-label={t.chat.conversations}
          className="hidden w-64 flex-col border-r border-gray-200 pr-4 md:flex"
        >
          <button
            type="button"
            onClick={handleNewConversation}
            className="mb-3 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            {t.chat.newConversation}
          </button>
          <div className="flex-1 overflow-y-auto text-sm text-gray-500">
            {conversations.length ? (
              <ul className="space-y-1">
                {conversations.map((id) => (
                  <li key={id} className="rounded bg-gray-50 px-2 py-1 text-gray-700">
                    {id}
                  </li>
                ))}
              </ul>
            ) : (
              t.chat.noConversations
            )}
          </div>
        </aside>

        <div className="flex flex-1 flex-col">
          <div className="mb-3 flex items-center gap-2">
            <label htmlFor="scope-select" className="text-sm font-medium text-gray-700">
              {t.chat.scope}
            </label>
            <select
              id="scope-select"
              role="combobox"
              aria-label={t.chat.scope}
              value={scope}
              onChange={(event) => setScope(event.target.value as ChatScope)}
              className="rounded border border-gray-300 px-2 py-1 text-sm"
            >
              {scopes.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex-1 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-4">
            {messages.length ? (
              <ol className="space-y-3">
                {messages.map((message, index) => (
                  <li
                    key={`${message.role}-${index}`}
                    className={message.role === "assistant" ? "rounded bg-white p-3" : "rounded bg-blue-50 p-3"}
                  >
                    <p className="text-sm font-semibold capitalize">{message.role}</p>
                    <p className="text-sm">{message.content}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-center text-sm text-gray-400">{t.chat.noConversations}</p>
            )}
          </div>

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
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void handleSend();
                }
              }}
              className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={sending || !question.trim()}
              className="rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Send
            </button>
            <button
              type="button"
              onClick={() => setStatus("Stopped")}
              className="rounded bg-red-500 px-3 py-2 text-sm font-medium text-white hover:bg-red-600"
            >
              {t.chat.stop}
            </button>
          </div>

          {status ? <p role="status" className="mt-2 text-sm text-red-700">{status}</p> : null}

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

          <div
            role="region"
            aria-label={t.chat.citations}
            className="mt-3 rounded border border-gray-200 bg-white p-3"
          >
            <h3 className="mb-1 text-sm font-medium text-gray-700">{t.chat.citations}</h3>
            {messages.some((message) => message.citations?.length) ? (
              <ul className="space-y-1 text-sm text-gray-600">
                {messages.flatMap((message) => message.citations ?? []).map((citation, index) => (
                  <li key={`${citation.document ?? citation.document_id}-${citation.chunk_id ?? index}-${index}`}>
                    {citation.document ?? citation.document_id ?? "document"} · page {citation.page ?? "?"}
                    {citation.section ? ` · ${citation.section}` : ""}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-400">{t.chat.noCitations}</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
