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

import { useEffect, useMemo, useRef, useState } from "react";

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

export default function HomePage() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const apiUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL,
    []
  );

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
    resizeTextarea();
  }, [question]);

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
    <main className={`app-shell ${hasMessages ? "has-messages" : "empty"}`}>
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
            className={`chat-bubble ${message.role}`}
          >
            <div className="label">
              {message.role === "user" ? "You" : "Assistant"}
            </div>
            {message.payload ? (
              <div className="answer-block">
                <pre>{message.payload.formatted_answer}</pre>
              </div>
            ) : (
              <div>{message.content}</div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </section>

      <section className={`panel composer ${hasMessages ? "" : "composer-empty"}`}>
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
    </main>
  );
}

