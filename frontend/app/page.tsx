/*
 * Copyright 2026 Piotr Synak
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * Purpose:
 * Chat UI that renders the strict answer format returned by the backend.
 */

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type EvidenceItem = {
  snippet: string;
  card_id: string;
};

type SourceRef = {
  card_id: string;
  section: string;
};

type ChatResponse = {
  category: string;
  answer: string;
  why_this_matters: string;
  evidence: EvidenceItem[];
  sources: SourceRef[];
  confidence: string;
  confidence_reason?: string | null;
  formatted_answer: string;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  payload?: ChatResponse;
};

const DEFAULT_API_URL = "http://localhost:8000";

const normalizePreviewText = (value: string, maxChars = 120) => {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "";
  }
  if (normalized.length <= maxChars) {
    return normalized;
  }
  return `${normalized.slice(0, maxChars).trimEnd()}…`;
};

type DetailsPanel = {
  key: "why" | "evidence" | "sources";
  title: string;
  preview: string;
  body: React.ReactNode;
};

const buildDetailsPanels = (response: ChatResponse): DetailsPanel[] => {
  const why = response.why_this_matters?.trim();
  const evidence = response.evidence?.filter((item) => item.snippet?.trim()) ?? [];
  const sources = response.sources?.filter((item) => item.card_id?.trim()) ?? [];

  const panels: DetailsPanel[] = [];

  if (why) {
    panels.push({
      key: "why",
      title: "Why this matters",
      preview: normalizePreviewText(why),
      body: <div className="rich-text">{why}</div>
    });
  }

  if (evidence.length > 0) {
    panels.push({
      key: "evidence",
      title: "Evidence",
      preview: normalizePreviewText(evidence[0]?.snippet ?? ""),
      body: (
        <ol className="evidence-list">
          {evidence.map((item, index) => (
            <li key={`${item.card_id}-${index}`}>
              <div className="rich-text">{item.snippet}</div>
              <div className="item-meta muted">Card: {item.card_id}</div>
            </li>
          ))}
        </ol>
      )
    });
  }

  if (sources.length > 0) {
    panels.push({
      key: "sources",
      title: "Sources",
      preview: normalizePreviewText(
        `${sources[0]?.card_id ?? ""}${sources[0]?.section ? ` — ${sources[0].section}` : ""}`
      ),
      body: (
        <ol className="sources-list">
          {sources.map((item, index) => (
            <li key={`${item.card_id}-${item.section}-${index}`}>
              <code>{item.card_id}</code>
              {item.section ? <span className="muted"> — {item.section}</span> : null}
            </li>
          ))}
        </ol>
      )
    });
  }

  return panels;
};

function AnswerDetailsAccordion({
  response,
  detailsId
}: {
  response: ChatResponse;
  detailsId: string;
}) {
  const panels = buildDetailsPanels(response);

  if (panels.length === 0) {
    return null;
  }

  return (
    <div id={detailsId} className="answer-details stack">
      <div className="details-heading">Answer details</div>
      {panels.map((panel) => (
        <details key={panel.key} className="accordion-panel">
          <summary>
            <span className="summary-title">{panel.title}</span>
            {panel.preview ? (
              <span className="summary-preview" title={panel.preview}>
                {panel.preview}
              </span>
            ) : null}
          </summary>
          <div className="panel-body">{panel.body}</div>
        </details>
      ))}
    </div>
  );
}

function AnswerDetailsPanel({
  response,
  expanded,
  pinned,
  onToggleExpanded,
  onTogglePinned
}: {
  response: ChatResponse | null;
  expanded: boolean;
  pinned: boolean;
  onToggleExpanded: () => void;
  onTogglePinned: () => void;
}) {
  const panels = response ? buildDetailsPanels(response) : [];

  const panelClassName = `rhs-details ${expanded ? "is-expanded" : "is-collapsed"}`;
  const pinLabel = pinned ? "Unpin details sidebar" : "Pin details sidebar";
  const toggleLabel = expanded ? "Collapse details sidebar" : "Expand details sidebar";

  return (
    <aside className={panelClassName} aria-label="Answer details">
      <div className="details-rail" aria-label="Details sidebar rail">
        <button
          type="button"
          className="rail-toggle"
          onClick={onToggleExpanded}
          aria-label={toggleLabel}
          title={toggleLabel}
        >
          {expanded ? ">" : "<"}
        </button>
        <div className="rail-label" aria-hidden="true">
          Details
        </div>
      </div>

      <div className="details-panel" hidden={!expanded}>
        <div className="details-panel-header">
          <div className="details-panel-title">Answer details</div>
          <div className="details-panel-controls" role="group" aria-label="Sidebar controls">
            <button
              type="button"
              className={`icon-button ${pinned ? "is-active" : ""}`}
              onClick={onTogglePinned}
              aria-pressed={pinned}
              aria-label={pinLabel}
              title={pinLabel}
            >
              <svg
                viewBox="0 0 24 24"
                width="16"
                height="16"
                aria-hidden="true"
                focusable="false"
              >
                <path
                  d="M14 2c.6 0 1 .4 1 1v3.2l4.2 4.2c.3.3.4.8.2 1.2-.2.4-.6.6-1 .6H14v7c0 .4-.3.8-.7.9-.4.1-.9 0-1.1-.4l-3-4.5H5.6c-.4 0-.8-.2-1-.6-.2-.4-.1-.9.2-1.2L9 6.2V3c0-.6.4-1 1-1h4z"
                  fill="currentColor"
                />
              </svg>
            </button>
          </div>
        </div>

        <div className="details-panel-body stack">
          {panels.length > 0 ? (
            panels.map((panel) => (
              <section key={panel.key} className="details-section">
                <h3 className="details-section-title">{panel.title}</h3>
                <div className="details-section-body">{panel.body}</div>
              </section>
            ))
          ) : (
            <div className="muted">Select an assistant answer and click Details to view metadata.</div>
          )}
        </div>
      </div>
    </aside>
  );
}

const hasAnyDetails = (response: ChatResponse) => {
  const hasWhy = Boolean(response.why_this_matters?.trim());
  const hasEvidence = (response.evidence?.length ?? 0) > 0;
  const hasSources = (response.sources?.length ?? 0) > 0;
  return hasWhy || hasEvidence || hasSources;
};

export default function HomePage() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeDetailsIndex, setActiveDetailsIndex] = useState<number | null>(null);
  const [detailsExpanded, setDetailsExpanded] = useState(false);
  const [detailsPinned, setDetailsPinned] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const apiUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL,
    []
  );

  const DETAILS_PINNED_STORAGE_KEY = "ask-about-piotr.detailsPinned";

  const activeDetailsResponse = useMemo(() => {
    if (activeDetailsIndex === null) {
      return null;
    }
    return messages[activeDetailsIndex]?.payload ?? null;
  }, [activeDetailsIndex, messages]);

  const togglePinned = useCallback(() => {
    setDetailsPinned((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(DETAILS_PINNED_STORAGE_KEY, next ? "1" : "0");
      } catch {
        // Ignore persistence errors (e.g. private mode)
      }
      setDetailsExpanded(next);
      return next;
    });
  }, []);

  const toggleExpanded = useCallback(() => {
    setDetailsExpanded((prev) => !prev);
  }, []);

  const resizeTextarea = () => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    const computed = window.getComputedStyle(textarea);
    const maxHeight = Number.parseFloat(computed.maxHeight || "0");
    const nextHeight = textarea.scrollHeight;
    if (Number.isFinite(maxHeight) && maxHeight > 0) {
      textarea.style.height = `${Math.min(nextHeight, maxHeight)}px`;
      textarea.style.overflowY = nextHeight > maxHeight ? "auto" : "hidden";
      return;
    }
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = "hidden";
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!detailsPinned) {
      return;
    }
    const lastIndex = messages.length - 1;
    if (lastIndex < 0) {
      return;
    }
    const lastMessage = messages[lastIndex];
    if (lastMessage?.role !== "assistant" || !lastMessage.payload) {
      return;
    }
    setActiveDetailsIndex(lastIndex);
    setDetailsExpanded(true);
  }, [detailsPinned, messages]);

  useEffect(() => {
    resizeTextarea();
  }, [question]);

  useEffect(() => {
    try {
      const storedPinned = window.localStorage.getItem(DETAILS_PINNED_STORAGE_KEY);
      const nextPinned = storedPinned === "1" || storedPinned === "true";
      setDetailsPinned(nextPinned);
      setDetailsExpanded(nextPinned);
    } catch {
      // Ignore persistence errors
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!detailsExpanded) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") {
        return;
      }
      event.preventDefault();
      setDetailsExpanded(false);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [detailsExpanded]);

  const submitQuestion = async () => {
    if (!question.trim()) {
      return;
    }
    const currentQuestion = question.trim();
    setQuestion("");
    setMessages((prev) => [...prev, { role: "user", content: currentQuestion }]);
    setLoading(true);

    const history = messages.slice(-6).map((message) => ({
      role: message.role,
      content:
        message.role === "assistant" && message.payload
          ? message.payload.answer
          : message.content
    }));

    try {
      const response = await fetch(`${apiUrl}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ question: currentQuestion, messages: history })
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Backend error");
      }

      const data = (await response.json()) as ChatResponse;
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.formatted_answer, payload: data }
      ]);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown error occurred";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${message}` }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }
    event.preventDefault();
    if (!loading) {
      void submitQuestion();
    }
  };

  const hasMessages = messages.length > 0;

  return (
    <main className="app-main">
      <div className="app-layout">
        <div className={`app-shell ${hasMessages ? "has-messages" : "empty"}`}>
          <header className="stack">
            <h1>Ask about Piotr</h1>
            <p className="muted">
              Ask a question about Piotr&apos;s experience. Responses are grounded in
              curated knowledge cards with citations.
            </p>
          </header>

          <section className={`chat-scroll stack ${hasMessages ? "" : "hidden"}`}>
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`chat-bubble ${message.role} ${
                  index === activeDetailsIndex ? "is-selected" : ""
                }`}
              >
                <div className="label">
                  {message.role === "user" ? "You" : "Assistant"}
                </div>
                {message.payload ? (
                  <div className="answer-view">
                    <div className="answer-main">
                      <div className="answer-prose">{message.payload.answer}</div>
                    </div>

                    <div
                      className="answer-meta"
                      role="group"
                      aria-label="Answer metadata"
                    >
                      <span
                        className="pill pill-confidence"
                        title={message.payload.confidence_reason ?? undefined}
                      >
                        Confidence: {message.payload.confidence}
                      </span>
                      {Array.isArray(message.payload.sources) &&
                      message.payload.sources.length > 0 ? (
                        <span className="meta-item">
                          Sources: {message.payload.sources.length}
                        </span>
                      ) : null}
                      {hasAnyDetails(message.payload) ? (
                        <button
                          type="button"
                          className="meta-link"
                          onClick={() => {
                            setActiveDetailsIndex(index);
                            setDetailsExpanded(true);
                          }}
                        >
                          Details
                        </button>
                      ) : null}
                    </div>
                  </div>
                ) : (
                  <div>{message.content}</div>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </section>

          <section
            className={`panel composer ${hasMessages ? "" : "composer-empty"}`}
          >
            <div className="input-row">
              <label className="label" htmlFor="question">
                Your question
              </label>
              <textarea
                id="question"
                placeholder="e.g. What did you build for Decreen?"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={handleKeyDown}
                ref={textareaRef}
              />
              <button onClick={submitQuestion} disabled={loading}>
                {loading ? "Asking..." : "Ask"}
              </button>
            </div>
          </section>
        </div>

        <AnswerDetailsPanel
          response={activeDetailsResponse}
          expanded={detailsExpanded}
          pinned={detailsPinned}
          onToggleExpanded={toggleExpanded}
          onTogglePinned={togglePinned}
        />
      </div>
    </main>
  );
}

