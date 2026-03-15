import { useState, useRef, useEffect } from "react";
import { Send, User, Bot, FileText, Scale, Users } from "lucide-react";
import { useProjectContext } from "../App";
import { useSSE } from "../hooks/useSSE";
import { StreamingText } from "../components/shared/StreamingText";
import { ConfidenceBar } from "../components/shared/ConfidenceBar";
import { Badge } from "../components/shared/Badge";
import type { ConversationMessage } from "../lib/types";

export default function QnA() {
  const { projectName } = useProjectContext();
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [selectedAnswer, setSelectedAnswer] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const {
    chunks,
    sources,
    decisions,
    experts,
    isStreaming,
    error,
    sendQuestion,
    reset,
  } = useSSE();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  useEffect(() => {
    if (chunks.length > 0 && selectedAnswer !== null) {
      setMessages((prev) =>
        prev.map((msg, idx) =>
          idx === selectedAnswer
            ? {
                ...msg,
                content: chunks.join(""),
                sources,
                decisions,
                experts,
                confidence: sources.length > 0 ? sources[0].relevance_score : 0,
              }
            : msg
        )
      );
    }
  }, [chunks, sources, decisions, experts, selectedAnswer]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || !projectName || isStreaming) return;

    const userMessage: ConversationMessage = {
      id: Date.now().toString(),
      role: "user",
      content: question,
      timestamp: new Date(),
    };

    const aiMessage: ConversationMessage = {
      id: (Date.now() + 1).toString(),
      role: "assistant",
      content: "",
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage, aiMessage]);
    setSelectedAnswer(messages.length + 1);
    setQuestion("");
    reset();

    try {
      await sendQuestion(projectName, question);
    } catch (err) {
      console.error("Failed to send question:", err);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const currentSources = selectedAnswer !== null ? messages[selectedAnswer]?.sources : sources;
  const currentDecisions = selectedAnswer !== null ? messages[selectedAnswer]?.decisions : decisions;
  const currentExperts = selectedAnswer !== null ? messages[selectedAnswer]?.experts : experts;

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col">
        <div className="p-4 border-b border-border">
          <h1 className="text-xl font-semibold">Q&A</h1>
          <p className="text-sm text-text-secondary">Ask questions about your codebase</p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center py-12 text-text-muted">
              <Bot className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>Ask a question to get started</p>
              <p className="text-sm mt-2">
                Example: "How does authentication work in this project?"
              </p>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div
              key={msg.id}
              onClick={() => msg.role === "assistant" && setSelectedAnswer(idx)}
              className={`
                max-w-[80%] rounded-xl p-4 cursor-pointer transition-colors
                ${
                  msg.role === "user"
                    ? "ml-auto bg-accent-blue/20 border border-accent-blue/30"
                    : selectedAnswer === idx
                    ? "bg-bg-secondary border border-accent-blue/50"
                    : "bg-bg-secondary border border-border hover:border-text-muted"
                }
              `}
            >
              <div className="flex items-start gap-3">
                {msg.role === "user" ? (
                  <User className="w-5 h-5 text-accent-blue mt-1" />
                ) : (
                  <Bot className="w-5 h-5 text-accent-violet mt-1" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-text-primary whitespace-pre-wrap">
                    {msg.content || (isStreaming && selectedAnswer === idx ? (
                      <StreamingText text={chunks.join("")} />
                    ) : null)}
                  </div>
                  {msg.role === "assistant" && msg.confidence !== undefined && msg.confidence > 0 && (
                    <div className="mt-3 pt-3 border-t border-border">
                      <div className="flex items-center gap-2 text-xs text-text-muted mb-2">
                        <span>Confidence:</span>
                        <ConfidenceBar score={msg.confidence} size="sm" />
                      </div>
                      {msg.sources && msg.sources.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {msg.sources.slice(0, 5).map((source, i) => (
                            <Badge key={i} variant="default" size="sm">
                              <FileText className="w-3 h-3 mr-1" />
                              {source.file_path}:{source.start_line}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}

          {error && (
            <div className="bg-accent-red/20 border border-accent-red/30 rounded-lg p-4 text-accent-red">
              {error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <form onSubmit={handleSubmit} className="p-4 border-t border-border">
          <div className="flex gap-3">
            <textarea
              ref={inputRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your codebase..."
              className="flex-1 bg-bg-secondary border border-border rounded-lg px-4 py-3 text-text-primary placeholder-text-muted resize-none focus:outline-none focus:border-accent-blue"
              rows={2}
              disabled={isStreaming}
            />
            <button
              type="submit"
              disabled={!question.trim() || isStreaming}
              className="px-4 py-2 bg-accent-blue hover:bg-accent-blue/80 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white transition-colors"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
          <p className="text-xs text-text-muted mt-2">
            Press Enter to send, Shift+Enter for new line
          </p>
        </form>
      </div>

      <div className="w-80 border-l border-border bg-bg-secondary overflow-y-auto">
        <div className="p-4 border-b border-border">
          <h2 className="font-semibold">Context</h2>
        </div>
        <div className="p-4">
          {!selectedAnswer && !isStreaming ? (
            <div className="text-center py-8 text-text-muted">
              <p className="text-sm">Ask a question to see context here</p>
            </div>
          ) : (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-medium text-text-secondary mb-2 flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  Sources
                </h3>
                <div className="space-y-2">
                  {(currentSources || sources).map((source, i) => (
                    <div
                      key={i}
                      className="bg-bg-tertiary rounded-lg p-2 text-sm cursor-pointer hover:bg-bg-hover"
                    >
                      <div className="font-mono text-text-primary truncate">
                        {source.file_path}
                      </div>
                      <div className="text-xs text-text-muted">
                        Lines {source.start_line}-
                        {source.end_line}
                      </div>
                    </div>
                  ))}
                  {(!currentSources || currentSources.length === 0) && !isStreaming && (
                    <p className="text-sm text-text-muted">No sources found</p>
                  )}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-medium text-text-secondary mb-2 flex items-center gap-2">
                  <Scale className="w-4 h-4" />
                  Decisions
                </h3>
                <div className="space-y-2">
                  {(currentDecisions || decisions).map((dec, i) => (
                    <div
                      key={i}
                      className="bg-bg-tertiary rounded-lg p-2 text-sm"
                    >
                      <div className="font-medium text-text-primary">
                        {dec.title}
                      </div>
                      <div className="text-xs text-text-muted mt-1 line-clamp-2">
                        {dec.decision}
                      </div>
                    </div>
                  ))}
                  {(!currentDecisions || currentDecisions.length === 0) && !isStreaming && (
                    <p className="text-sm text-text-muted">No decisions referenced</p>
                  )}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-medium text-text-secondary mb-2 flex items-center gap-2">
                  <Users className="w-4 h-4" />
                  Experts
                </h3>
                <div className="space-y-2">
                  {(currentExperts || experts).map((expert, i) => (
                    <div
                      key={i}
                      className="bg-bg-tertiary rounded-lg p-2 text-sm"
                    >
                      <div className="font-medium text-text-primary">
                        {expert.name}
                      </div>
                      <ConfidenceBar
                        score={expert.expertise_score}
                        size="sm"
                      />
                    </div>
                  ))}
                  {(!currentExperts || currentExperts.length === 0) && !isStreaming && (
                    <p className="text-sm text-text-muted">No experts found</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
