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

type HeaderAction = {
  key: "cv" | "ai-projects" | "github" | "publications";
  label: string;
  href: string;
  ariaLabel: string;
};

const HEADER_ACTION_DEFAULTS = {
  cv: "/assets/cv/CV_Piotr_Synak.pdf",
  aiProjects: "/assets/ai-projects/AI_Projects_Piotr_Synak.pdf",
  github: "https://github.com/kotsinus/Ask-about-Piotr",
  publications: "/assets/publications/Publications_Piotr_Synak.pdf"
} as const;

const HEADER_ACTION_ENV = {
  cv: process.env.NEXT_PUBLIC_CV_URL,
  aiProjects: process.env.NEXT_PUBLIC_AI_PROJECTS_URL,
  github: process.env.NEXT_PUBLIC_GITHUB_URL,
  publications: process.env.NEXT_PUBLIC_PUBLICATIONS_URL
} as const;

const normalizeHref = (value: string | undefined) => (value ?? "").trim();

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
  const messagesRef = useRef<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [lastTopic, setLastTopic] = useState<string | null>(null);
  const [activeDetailsIndex, setActiveDetailsIndex] = useState<number | null>(null);
  const [detailsExpanded, setDetailsExpanded] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const resizeRafRef = useRef<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = useRef(true);
  const apiUrl = useMemo(() => {
    const value = process.env.NEXT_PUBLIC_API_URL;
    if (!value || !value.trim()) {
      return "";
    }
    return value.trim().replace(/\/+$/, "");
  }, []);
  const apiConfigured = Boolean(apiUrl);

  const headerActions = useMemo(() => {
    const cvHref =
      HEADER_ACTION_ENV.cv !== undefined
        ? normalizeHref(HEADER_ACTION_ENV.cv)
        : HEADER_ACTION_DEFAULTS.cv;
    const aiProjectsHref =
      HEADER_ACTION_ENV.aiProjects !== undefined
        ? normalizeHref(HEADER_ACTION_ENV.aiProjects)
        : HEADER_ACTION_DEFAULTS.aiProjects;
    const githubHref =
      HEADER_ACTION_ENV.github !== undefined
        ? normalizeHref(HEADER_ACTION_ENV.github)
        : HEADER_ACTION_DEFAULTS.github;
    const publicationsHref =
      HEADER_ACTION_ENV.publications !== undefined
        ? normalizeHref(HEADER_ACTION_ENV.publications)
        : HEADER_ACTION_DEFAULTS.publications;

    const actions: HeaderAction[] = [
      {
        key: "cv",
        label: "CV (PDF)",
        href: cvHref,
        ariaLabel: "Open curriculum vitae (PDF)"
      },
      {
        key: "ai-projects",
        label: "AI Projects (PDF)",
        href: aiProjectsHref,
        ariaLabel: "Open selected AI and data system projects (PDF)"
      },
      {
        key: "github",
        label: "GitHub",
        href: githubHref,
        ariaLabel: "Open-source code and system architecture"
      },
      {
        key: "publications",
        label: "Publications (PDF)",
        href: publicationsHref,
        ariaLabel: "Open selected publications and research output (PDF)"
      }
    ];

    return actions.filter((action) => Boolean(action.href));
  }, []);

  // Keep a ref in sync with state so event handlers can reliably read the
  // latest messages even under rapid interactions (e.g. multiple quick Enter
  // presses before a re-render).
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const setMessagesWithRef = useCallback((updater: (prev: Message[]) => Message[]) => {
    setMessages((prev) => {
      const next = updater(prev);
      messagesRef.current = next;
      return next;
    });
  }, []);

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

  const resizeTextarea = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    if (resizeRafRef.current !== null) {
      window.cancelAnimationFrame(resizeRafRef.current);
    }

    resizeRafRef.current = window.requestAnimationFrame(() => {
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
    });
  }, []);

  useEffect(() => {
    return () => {
      if (resizeRafRef.current !== null) {
        window.cancelAnimationFrame(resizeRafRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const thresholdPx = 140;
    const updateAutoScrollFlag = () => {
      const doc = document.documentElement;
      const nearBottom = window.innerHeight + window.scrollY >= doc.scrollHeight - thresholdPx;
      shouldAutoScrollRef.current = nearBottom;
    };

    updateAutoScrollFlag();
    window.addEventListener("scroll", updateAutoScrollFlag, { passive: true });
    return () => {
      window.removeEventListener("scroll", updateAutoScrollFlag);
    };
  }, []);

  useEffect(() => {
    if (!shouldAutoScrollRef.current) {
      return;
    }
    const lastMessage = messages[messages.length - 1];
    const behavior: ScrollBehavior = lastMessage?.role === "assistant" ? "smooth" : "auto";
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, [messages]);

  useEffect(() => {
    if (latestAssistantAnswerIndex === null) {
      return;
    }
    setActiveDetailsIndex(latestAssistantAnswerIndex);
  }, [latestAssistantAnswerIndex]);

  useEffect(() => {
    resizeTextarea();
  }, [question, resizeTextarea]);

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
      setMessagesWithRef((prev) => [
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
    const messagesSnapshot = messagesRef.current;

    // Intentionally exclude the current question from `history` because it is
    // sent separately as `question` in the request body.
    const history = messagesSnapshot.slice(-6).map((message) => ({
      role: message.role,
      content:
        message.role === "assistant" && message.payload
          ? message.payload.answer
          : message.content
    }));

    // Protect against refresh/rehydration: only send last_topic when we have
    // usable history (at least one complete prior turn).
    const shouldSendLastTopic = messagesSnapshot.length >= 2;

    setQuestion("");
    setMessagesWithRef((prev) => [...prev, { role: "user", content: currentQuestion }]);
    setLoading(true);

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
        console.error("Backend error response:", {
          status: response.status,
          statusText: response.statusText,
          body: text
        });
        throw new Error("Backend error. Please try again in a moment.");
      }

      const data = (await response.json()) as ChatResponse;
      if (data.context?.conversation_id) {
        setConversationId(data.context.conversation_id);
      }
      if (data.context?.last_topic) {
        setLastTopic(data.context.last_topic);
      }
      setMessagesWithRef((prev) => [
        ...prev,
        { role: "assistant", content: data.formatted_answer, payload: data }
      ]);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown error occurred";
      setMessagesWithRef((prev) => [
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
            <div className="hero-title-row">
              <h1>Ask Piotr Synak</h1>
              {headerActions.length > 0 ? (
                <nav className="header-actions" aria-label="Header actions">
                  {headerActions.map((action) => {
                    // These header actions are documents / external resources and should
                    // always open in a new tab/window.
                    const openInNewTab = true;
                    return (
                      <a
                        key={action.key}
                        className="header-action-link"
                        href={action.href}
                        aria-label={action.ariaLabel}
                        title={action.ariaLabel}
                        {...(openInNewTab
                          ? {
                              target: "_blank",
                              rel: "noopener noreferrer"
                            }
                          : undefined)}
                      >
                        {action.label}
                      </a>
                    );
                  })}
                </nav>
              ) : null}
            </div>
            <p className="hero-subtitle">
              An open-source AI that explains my professional experience using verifiable sources
              only.
            </p>
            <p className="muted">Ask questions about my work, experience, or background.</p>
            <p className="muted">
              This assistant answers exclusively from retrieved documentation based on my CV,
              selected projects, and publications.
              <br />
              Each response includes source citations and explicitly states uncertainty when the
              available evidence is insufficient.
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
                placeholder="e.g. What is your professional background?"
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

          <p className="muted" aria-label="Trust signals">
            Evidence-based retrieval · Source citations · Explicit refusal behavior · Privacy-first
          </p>
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

