"use client";

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/i18n/context";
import { api, type ChatScope, type Citation, type Conversation } from "@/lib/api-client";

interface ChatMessage {
  id?: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

/** Error title from the API's problem+json (never the stack/detail), else the fallback. */
function reason(error: unknown, fallback: string): string {
  const title = (error as { title?: unknown } | null)?.title;
  return typeof title === "string" && title ? title : fallback;
}

// Chat screen shell — internal component boundary.
// If assistant-ui is added later (pinned, MIT, no cloud service),
// swap the internals to Thread/ThreadList; the API surface stays the same.
export function ChatScreen() {
  const { t } = useI18n();
  const [scope, setScope] = useState<ChatScope>("all");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [notice, setNotice] = useState("");
  const [sending, setSending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const scopes: { value: ChatScope; label: string }[] = [
    { value: "all", label: t.chat.scopeAll },
    { value: "my_documents", label: t.chat.scopeMyDocs },
    { value: "shared_with_me", label: t.chat.scopeShared },
    { value: "my_team", label: t.chat.scopeTeam },
    { value: "this_document", label: t.chat.scopeDocument },
  ];

  // Saved conversations survive a reload (UAT-CHAT-001); a signed-out visitor just sees none.
  useEffect(() => {
    let cancelled = false;
    api
      .listConversations()
      .then((result) => {
        if (!cancelled) setConversations(result.conversations ?? []);
      })
      .catch(() => {
        /* not signed in: leave the list empty */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const lastAssistantId = [...messages].reverse().find((m) => m.role === "assistant" && m.id)?.id;
  // Index of the newest assistant answer: its citations live in the Citations panel; earlier answers keep theirs inline.
  const latestAssistantIndex = messages.map((m) => m.role).lastIndexOf("assistant");

  async function handleNewConversation() {
    setStatus("");
    setNotice("");
    try {
      const conv = await api.createConversation(t.chat.newConversation);
      setConversations((items) => [conv, ...items]);
      setActiveId(conv.id);
      setMessages([]);
      setQuestion("");
    } catch (error) {
      setStatus(reason(error, t.chat.requestFailed));
    }
  }

  async function handleOpen(id: string) {
    setStatus("");
    setNotice("");
    setActiveId(id);
    try {
      const history = await api.listMessages(id);
      setMessages(
        history.messages.map((m) => ({ id: m.id, role: m.role, content: m.content, citations: m.citations })),
      );
    } catch (error) {
      setStatus(reason(error, t.chat.requestFailed));
    }
  }

  async function handleSend() {
    const trimmed = question.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setStatus("");
    setNotice("");
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      let convId = activeId;
      if (!convId) {
        // The first question starts a conversation named after it, so history is saved and findable.
        const conv = await api.createConversation(trimmed.slice(0, 60));
        convId = conv.id;
        setConversations((items) => [conv, ...items]);
        setActiveId(conv.id);
      }
      setMessages((items) => [...items, { role: "user", content: trimmed }]);
      setQuestion("");
      const response = await api.sendMessage(convId, trimmed, scope, undefined, controller.signal);
      if (controller.signal.aborted) {
        // Stopped while in flight: drop the answer, but mark the message the server still created.
        if (response.message_id) await api.stopMessage(response.message_id).catch(() => undefined);
        return;
      }
      setMessages((items) => [
        ...items,
        { id: response.message_id, role: "assistant", content: response.answer, citations: response.citations ?? [] },
      ]);
    } catch (error) {
      if (!controller.signal.aborted) setStatus(reason(error, t.chat.requestFailed));
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setSending(false);
    }
  }

  async function handleStop() {
    setStatus("");
    if (sending && abortRef.current) {
      abortRef.current.abort();
      setNotice(t.chat.stopped);
      return;
    }
    if (!lastAssistantId) return;
    try {
      await api.stopMessage(lastAssistantId);
      setNotice(t.chat.stopped);
    } catch {
      setStatus(t.chat.stopFailed);
    }
  }

  async function handleFeedback(rating: "up" | "down") {
    if (!lastAssistantId) return;
    setStatus("");
    try {
      await api.recordFeedback(lastAssistantId, { rating });
      setNotice(t.chat.feedbackThanks);
    } catch {
      setStatus(t.chat.feedbackFailed);
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
                {conversations.map((conv) => (
                  <li key={conv.id}>
                    <button
                      type="button"
                      onClick={() => void handleOpen(conv.id)}
                      aria-current={conv.id === activeId ? "true" : undefined}
                      className={`w-full rounded px-2 py-1 text-left text-gray-700 hover:bg-gray-100 ${conv.id === activeId ? "bg-blue-50 font-medium" : "bg-gray-50"}`}
                    >
                      {conv.title}
                    </button>
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
                    key={`${message.id ?? message.role}-${index}`}
                    className={message.role === "assistant" ? "rounded bg-white p-3" : "rounded bg-blue-50 p-3"}
                  >
                    <p className="text-sm font-semibold capitalize">{message.role}</p>
                    <p className="text-sm">{message.content}</p>
                    {message.role === "assistant" && message.citations?.length && index !== latestAssistantIndex ? (
                      <ul className="mt-1 space-y-0.5 text-xs text-gray-500" aria-label={t.chat.citations}>
                        {message.citations.map((citation, cIndex) => (
                          <li key={`${citation.document ?? citation.document_id}-${citation.chunk_id ?? cIndex}-${cIndex}`}>
                            {citation.document ?? citation.document_id ?? "document"} · page {citation.page ?? "?"}
                            {citation.section ? ` · ${citation.section}` : ""}
                          </li>
                        ))}
                      </ul>
                    ) : null}
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
              {t.chat.send}
            </button>
            <button
              type="button"
              onClick={() => void handleStop()}
              disabled={!sending && !lastAssistantId}
              className="rounded bg-red-500 px-3 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-50"
            >
              {t.chat.stop}
            </button>
          </div>

          {status ? <p role="status" className="mt-2 text-sm text-red-700">{status}</p> : null}
          {notice ? <p role="status" className="mt-2 text-sm text-green-700">{notice}</p> : null}

          <div className="mt-2 flex items-center gap-2 text-sm text-gray-600">
            <span>{t.chat.feedback}</span>
            <button
              type="button"
              disabled={!lastAssistantId}
              onClick={() => void handleFeedback("up")}
              className="rounded border border-green-300 px-2 py-1 text-green-700 hover:bg-green-50 disabled:opacity-50"
            >
              {t.chat.thumbsUp}
            </button>
            <button
              type="button"
              disabled={!lastAssistantId}
              onClick={() => void handleFeedback("down")}
              className="rounded border border-red-300 px-2 py-1 text-red-700 hover:bg-red-50 disabled:opacity-50"
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
            {(() => {
              const latestCitations = [...messages].reverse().find((m) => m.role === "assistant")?.citations ?? [];
              return latestCitations.length ? (
                <ul className="space-y-1 text-sm text-gray-600">
                  {latestCitations.map((citation, index) => (
                    <li key={`${citation.document ?? citation.document_id}-${citation.chunk_id ?? index}-${index}`}>
                      {citation.document ?? citation.document_id ?? "document"} · page {citation.page ?? "?"}
                      {citation.section ? ` · ${citation.section}` : ""}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-gray-400">{t.chat.noCitations}</p>
              );
            })()}
          </div>
        </div>
      </div>
    </section>
  );
}
