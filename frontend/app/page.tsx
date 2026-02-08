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
import Image from "next/image";

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
  context?: {
    conversation_id?: string | null;
    last_topic?: string | null;
  };
};

type Message = {
  role: "user" | "assistant";
  content: string;
  payload?: ChatResponse;
};

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

function AnswerDetailsPanel({
  response,
  expanded,
  onToggleExpanded
}: {
  response: ChatResponse | null;
  expanded: boolean;
  onToggleExpanded: () => void;
}) {
  const panels = response ? buildDetailsPanels(response) : [];

  const [collapsedSections, setCollapsedSections] = useState({
    evidence: false,
    sources: false
  });

  const toggleCollapsibleSection = useCallback((key: "evidence" | "sources") => {
    setCollapsedSections((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const panelClassName = `rhs-details ${expanded ? "is-expanded" : "is-collapsed"}`;
  const toggleLabel = expanded ? "Collapse details sidebar" : "Expand details sidebar";

  return (
    <aside className={panelClassName} aria-label="Answer details">
      <button
        type="button"
        className="details-rail"
        onClick={onToggleExpanded}
        aria-label={toggleLabel}
        aria-expanded={expanded}
        title={toggleLabel}
      >
        <span className="rail-toggle" aria-hidden="true">
          {expanded ? ">" : "<"}
        </span>
        <span className="rail-label" aria-hidden="true">
          Details
        </span>
      </button>

      <div className="details-panel" hidden={!expanded}>
        <div className="details-panel-body stack">
          {panels.length > 0 ? (
            panels.map((panel) => (
              <section key={panel.key} className="details-section">
                {panel.key === "why" ? (
                  <>
                    <h3 className="details-section-title">{panel.title}</h3>
                    <div className="details-section-body">{panel.body}</div>
                  </>
                ) : panel.key === "evidence" || panel.key === "sources" ? (
                  <>
                    <h3 className="details-section-title has-toggle">
                      <button
                        type="button"
                        className="details-section-toggle"
                        onClick={() => {
                          if (panel.key === "evidence") {
                            toggleCollapsibleSection("evidence");
                          }
                          if (panel.key === "sources") {
                            toggleCollapsibleSection("sources");
                          }
                        }}
                        aria-expanded={
                          panel.key === "evidence"
                            ? !collapsedSections.evidence
                            : !collapsedSections.sources
                        }
                        aria-controls={`details-section-${panel.key}`}
                      >
                        <span className="details-section-toggle-label">{panel.title}</span>
                        <span className="details-section-chevron" aria-hidden="true">
                          {panel.key === "evidence"
                            ? collapsedSections.evidence
                              ? "˅"
                              : "˄"
                            : collapsedSections.sources
                              ? "˅"
                              : "˄"}
                        </span>
                      </button>
                    </h3>
                    <div
                      id={`details-section-${panel.key}`}
                      className="details-section-body"
                      hidden={
                        panel.key === "evidence"
                          ? collapsedSections.evidence
                          : collapsedSections.sources
                      }
                    >
                      {panel.body}
                    </div>
                  </>
                ) : null}
              </section>
            ))
          ) : (
            <div className="muted">
              Select Piotr&apos;s answer to view why/evidence/sources in the Details sidebar.
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

export default function HomePage() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [lastTopic, setLastTopic] = useState<string | null>(null);
  const [activeDetailsIndex, setActiveDetailsIndex] = useState<number | null>(null);
  const [detailsExpanded, setDetailsExpanded] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const apiUrl = useMemo(() => {
    const value = process.env.NEXT_PUBLIC_API_URL;
    if (!value || !value.trim()) {
      return "";
    }
    return value.trim().replace(/\/+$/, "");
  }, []);
  const apiConfigured = Boolean(apiUrl);

  const latestAssistantAnswerIndex = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message?.role === "assistant" && message.payload) {
        return index;
      }
    }
    return null;
  }, [messages]);

  const activeDetailsResponse = useMemo(() => {
    if (activeDetailsIndex === null) {
      return null;
    }
    return messages[activeDetailsIndex]?.payload ?? null;
  }, [activeDetailsIndex, messages]);

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
    if (latestAssistantAnswerIndex === null) {
      return;
    }
    setActiveDetailsIndex(latestAssistantAnswerIndex);
  }, [latestAssistantAnswerIndex]);

  useEffect(() => {
    resizeTextarea();
  }, [question]);

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

    if (!apiConfigured) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "Error: API URL not configured. Set NEXT_PUBLIC_API_URL (e.g. https://your-backend.example) and rebuild/redeploy the frontend."
        }
      ]);
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

    // Protect against refresh/rehydration: only send last_topic when we have
    // usable history (at least one complete prior turn).
    const shouldSendLastTopic = messages.length >= 2;

    try {
      const response = await fetch(`${apiUrl}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        credentials: "include",
        body: JSON.stringify({
          question: currentQuestion,
          messages: history,
          context: {
            conversation_id: conversationId,
            last_topic: shouldSendLastTopic ? lastTopic : null
          }
        })
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Backend error");
      }

      const data = (await response.json()) as ChatResponse;
      if (data.context?.conversation_id) {
        setConversationId(data.context.conversation_id);
      }
      if (data.context?.last_topic) {
        setLastTopic(data.context.last_topic);
      }
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
  const layoutClassName = `app-layout ${detailsExpanded ? "details-expanded" : ""}`.trim();

  return (
    <main className="app-main">
      <div className={layoutClassName}>
        <div className={`app-shell ${hasMessages ? "has-messages" : "empty"}`}>
          <header className="stack">
            <h1>Ask Piotr Synak</h1>
            <p className="hero-subtitle">An evidence-grounded AI explaining my work</p>
            <p className="muted">
              Ask me about my experience. I answer only from retrieved source material, with citations and explicit uncertainty when evidence is missing.
            </p>

            {!apiConfigured ? (
              <div className="panel panel-warning" role="status" aria-live="polite">
                <div className="panel-warning-title">API URL not configured</div>
                <div className="muted">
                  This public demo needs <code>NEXT_PUBLIC_API_URL</code> to be set at build time.
                  Without it, the frontend cannot reach the backend API.
                </div>
              </div>
            ) : null}
          </header>

          <section className={`chat-scroll stack ${hasMessages ? "" : "hidden"}`}>
            {messages.map((message, index) => {
              const selectable = message.role === "assistant" && Boolean(message.payload);
              const bubbleClassName = `chat-bubble ${message.role} ${
                index === activeDetailsIndex ? "is-selected" : ""
              } ${selectable ? "is-clickable" : ""}`.trim();

              const bubbleBody = (
                <>
                  <div className="label">
                    {message.role === "user" ? (
                      "You"
                    ) : (
                      <span className="label-with-avatar">
                        <Image
                          src="/piotr_synak.jpg"
                          width={18}
                          height={18}
                          className="avatar"
                          alt="Piotr Synak"
                        />
                        <span>Piotr</span>
                      </span>
                    )}
                  </div>
                  {message.payload ? (
                    <div className="answer-view">
                      <div className="answer-main">
                        <div className="answer-prose">{message.payload.answer}</div>
                      </div>

                      <div className="answer-meta" role="group" aria-label="Answer metadata">
                        <span
                          className="pill pill-confidence"
                          title={message.payload.confidence_reason ?? undefined}
                        >
                          Confidence: {message.payload.confidence}
                        </span>
                        {Array.isArray(message.payload.sources) &&
                        message.payload.sources.length > 0 ? (
                          <span className="meta-item">Sources: {message.payload.sources.length}</span>
                        ) : null}
                      </div>
                    </div>
                  ) : (
                    <div>{message.content}</div>
                  )}
                </>
              );

              if (selectable) {
                return (
                  <button
                    key={`${message.role}-${index}`}
                    type="button"
                    className={bubbleClassName}
                    onClick={() => {
                      setActiveDetailsIndex(index);
                      setDetailsExpanded(true);
                    }}
                    aria-current={index === activeDetailsIndex ? "true" : undefined}
                  >
                    {bubbleBody}
                  </button>
                );
              }

              return (
                <div key={`${message.role}-${index}`} className={bubbleClassName}>
                  {bubbleBody}
                </div>
              );
            })}
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
                rows={1}
                disabled={!apiConfigured}
              />
              <button onClick={submitQuestion} disabled={loading || !apiConfigured}>
                {loading ? "Asking..." : "Ask"}
              </button>
            </div>
          </section>
        </div>

        <AnswerDetailsPanel
          key={activeDetailsIndex ?? "no-active-details"}
          response={activeDetailsResponse}
          expanded={detailsExpanded}
          onToggleExpanded={toggleExpanded}
        />
      </div>
    </main>
  );
}

