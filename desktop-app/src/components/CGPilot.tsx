import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Clock,
  FileText,
  History,
  Lightbulb,
  Loader2,
  Maximize2,
  MessageCircle,
  MessageSquare,
  Minimize2,
  Plus,
  Send,
  Trash2,
  User,
  Wrench,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { askCGPilot, getCGPilotStatus, getChatHistory, getChatSession, deleteChatSession } from "../lib/api";
import type { CGPilotStep, CGPilotStatus, CGPilotToolUse, ChatSessionSummary, SourceRef } from "../lib/types";
import { useProjectContext } from "../App";

interface CGPilotProps {
  projectId: string;
  projectPath: string;
  indexStatus?: string;
  pendingSessionId?: string | null;
  onClearPendingSession?: () => void;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  tools?: CGPilotToolUse[];
  steps?: CGPilotStep[];
}

function SourceList({ sources }: { sources: SourceRef[] }) {
  if (sources.length === 0) return null;

  const deduped = sources.filter(
    (source, index, all) =>
      all.findIndex(
        (item) =>
          item.file_path === source.file_path &&
          item.start_line === source.start_line &&
          item.end_line === source.end_line
      ) === index
  );

  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {deduped.slice(0, 6).map((source, index) => (
        <span
          key={`${source.file_path}-${source.start_line}-${index}`}
          className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-md border border-border bg-bg-tertiary px-2 py-1 text-xs text-text-secondary"
        >
          <FileText className="h-3 w-3 flex-shrink-0 text-accent-cyan" />
          <span className="truncate">
            {source.file_path}
            {source.start_line ? `:${source.start_line}` : ""}
          </span>
        </span>
      ))}
    </div>
  );
}

function stepIcon(action: string) {
  switch (action) {
    case "plan":
      return <Lightbulb className="h-3.5 w-3.5 text-amber-400" />;
    case "tool_call":
      return <Wrench className="h-3.5 w-3.5 text-accent-cyan" />;
    case "observation":
      return <FileText className="h-3.5 w-3.5 text-accent-blue" />;
    case "final":
      return <Bot className="h-3.5 w-3.5 text-accent-green" />;
    default:
      return <Bot className="h-3.5 w-3.5" />;
  }
}

function stepLabel(action: string) {
  switch (action) {
    case "plan":
      return "Plans";
    case "tool_call":
      return "Tool call";
    case "observation":
      return "Analyses";
    case "final":
      return "Answer";
    default:
      return action;
  }
}

function StepTimeline({ steps }: { steps: CGPilotStep[] }) {
  if (steps.length === 0) return null;

  const [expanded, setExpanded] = useState(false);

  return (
    <div className="mt-3 border-t border-border pt-2">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-1.5 text-xs font-medium text-text-muted hover:text-text-secondary transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
        <Wrench className="h-3 w-3" />
        {steps.length} step{steps.length > 1 ? "s" : ""} taken
      </button>

      {expanded && (
        <div className="mt-2 space-y-1.5 pl-3 border-l-2 border-border">
          {steps.map((step, index) => (
            <div key={index} className="flex gap-2 text-xs">
              <div className="mt-0.5 flex-shrink-0">
                {stepIcon(step.action)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 text-text-muted">
                  <span className="rounded bg-bg-tertiary px-1 font-mono text-[10px]">
                    #{step.round}
                  </span>
                  <span>{stepLabel(step.action)}</span>
                  {step.tool_name && (
                    <code className="rounded bg-bg-tertiary px-1 font-mono text-[10px] text-accent-cyan">
                      {step.tool_name}
                    </code>
                  )}
                </div>
                {(step.message || step.tool_summary) && (
                  <p className="mt-0.5 leading-relaxed text-text-secondary">
                    {step.message || step.tool_summary}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function HistoryPanel({
  sessions,
  onSelect,
  onDelete,
}: {
  sessions: ChatSessionSummary[];
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-text-muted">
        <MessageSquare className="mb-3 h-8 w-8 opacity-50" />
        <p className="text-sm">No chat history yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-1 px-3 py-2">
      {sessions.map((s) => (
        <div
          key={s.session_id}
          className="group flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2.5 text-sm hover:bg-bg-hover transition-colors"
          onClick={() => onSelect(s.session_id)}
        >
          <MessageSquare className="h-4 w-4 flex-shrink-0 text-text-muted" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-text-primary">{s.title || "(no title)"}</div>
            <div className="text-xs text-text-muted">
              {s.message_count} message{s.message_count !== 1 ? "s" : ""}
            </div>
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(s.session_id);
            }}
            className="flex-shrink-0 rounded p-1 text-text-muted opacity-0 group-hover:opacity-100 hover:bg-bg-tertiary hover:text-accent-red transition-all"
            title="Delete session"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}

export function CGPilot({ projectId, projectPath, indexStatus, pendingSessionId, onClearPendingSession }: CGPilotProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [status, setStatus] = useState<CGPilotStatus | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { selectedFilePath } = useProjectContext();
  const [attachedFilePath, setAttachedFilePath] = useState<string | null>(null);
  const dismissedPathRef = useRef<string | null>(null);

  useEffect(() => {
    if (!selectedFilePath) {
      setAttachedFilePath(null);
      dismissedPathRef.current = null;
    } else if (selectedFilePath !== dismissedPathRef.current) {
      setAttachedFilePath(selectedFilePath);
    }
  }, [selectedFilePath]);

  const handleDismissFile = useCallback(() => {
    setAttachedFilePath(null);
    dismissedPathRef.current = attachedFilePath;
  }, [attachedFilePath]);

  const isIndexing = indexStatus === "queued" || indexStatus === "running";
  const canChat = Boolean(status?.ready) && !isIndexing;

  useEffect(() => {
    let cancelled = false;

    async function loadStatus() {
      try {
        const result = await getCGPilotStatus(projectId);
        if (!cancelled) {
          setStatus(result);
        }
      } catch (err) {
        if (!cancelled) {
          setStatus({
            project_id: projectId,
            indexed: false,
            ready: false,
            reason: (err as Error).message,
          });
        }
      }
    }

    loadStatus();
    const interval = setInterval(loadStatus, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [projectId, indexStatus]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending, isOpen, isExpanded, showHistory]);

  const disabledReason = useMemo(() => {
    if (isIndexing) return "Indexing is still running.";
    if (!status) return "Checking project index.";
    if (!status.ready) return status.reason || "CG-pilot is not ready.";
    return "";
  }, [isIndexing, status]);

  // ── Load history list ──────────────────────────────────────────────────

  const loadSessions = useCallback(async () => {
    setIsLoadingHistory(true);
    try {
      const list = await getChatHistory(projectId);
      setSessions(list);
    } catch {
      // ignore
    } finally {
      setIsLoadingHistory(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (showHistory) {
      loadSessions();
    }
  }, [showHistory, loadSessions]);

  // ── Load a previous session ────────────────────────────────────────────

  const loadSession = useCallback(async (sid: string) => {
    try {
      const detail = await getChatSession(projectId, sid);
      setSessionId(sid);
      setMessages(
        detail.messages.map((m, i) => ({
          id: `${sid}-${i}`,
          role: m.role as "user" | "assistant",
          content: m.content,
          sources: m.sources,
          tools: m.tools_used,
          steps: m.steps,
        }))
      );
      setShowHistory(false);
    } catch {
      // ignore
    }
  }, [projectId]);

  // ── New chat ───────────────────────────────────────────────────────────

  const newChat = useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setError(null);
    setShowHistory(false);
  }, []);

  // ── Delete a session ───────────────────────────────────────────────────

  const deleteSession = useCallback(async (sid: string) => {
    try {
      await deleteChatSession(projectId, sid);
      setSessions((prev) => prev.filter((s) => s.session_id !== sid));
      if (sessionId === sid) {
        newChat();
      }
    } catch {
      // ignore
    }
  }, [projectId, sessionId, newChat]);

  // ── Handle pending session from dashboard click ────────────────────────

  useEffect(() => {
    if (pendingSessionId) {
      setIsOpen(true);
      loadSession(pendingSessionId);
      onClearPendingSession?.();
    }
  }, [pendingSessionId, loadSession, onClearPendingSession]);

  // ── Submit ─────────────────────────────────────────────────────────────

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const text = input.trim();
    if (!text || !canChat || isSending) return;

    const userMessage: ChatMessage = {
      id: `${Date.now()}-user`,
      role: "user",
      content: text,
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setError(null);
    setIsSending(true);

    try {
      const history = messages.slice(-10).map((message) => ({
        role: message.role,
        content: message.content,
      }));
      const fileContext = attachedFilePath ? { file_path: attachedFilePath } : undefined;
      const response = await askCGPilot(
        projectId, projectPath, text, history, fileContext, sessionId ?? undefined
      );
      setSessionId(response.session_id);
      setMessages((current) => [
        ...current,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          tools: response.tools_used,
          steps: response.steps,
        },
      ]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsSending(false);
    }
  };

  const panelClasses = isExpanded
    ? "fixed inset-4 z-50 flex flex-col overflow-hidden rounded-lg border border-border bg-bg-primary shadow-2xl"
    : "fixed bottom-24 right-6 z-50 flex h-[560px] w-[420px] max-h-[calc(100vh-7rem)] max-w-[calc(100vw-3rem)] flex-col overflow-hidden rounded-lg border border-border bg-bg-secondary shadow-2xl";

  return (
    <>
      <button
        onClick={() => setIsOpen((value) => !value)}
        className="fixed bottom-6 right-6 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-accent-blue text-white shadow-lg transition-colors hover:bg-accent-blue/80"
        title="CG-pilot"
      >
        {isOpen ? <X className="h-5 w-5" /> : <MessageCircle className="h-5 w-5" />}
      </button>

      {isOpen && (
        <>
          {isExpanded && <div className="fixed inset-0 z-40 bg-black/50" />}
          <section className={panelClasses}>
            <header className="flex items-center justify-between border-b border-border px-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-accent-blue/15 text-accent-blue">
                  <Bot className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-semibold text-text-primary">CG-pilot</h2>
                  <p className="truncate text-xs text-text-muted">
                    {canChat ? "Ready" : disabledReason}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => { setShowHistory((v) => !v); }}
                  className={`rounded-md p-2 transition-colors hover:bg-bg-hover ${
                    showHistory ? "bg-accent-blue/15 text-accent-blue" : "text-text-secondary hover:text-text-primary"
                  }`}
                  title={showHistory ? "Close history" : "Chat history"}
                >
                  <History className="h-4 w-4" />
                </button>
                <button
                  onClick={newChat}
                  className="rounded-md p-2 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
                  title="New chat"
                >
                  <Plus className="h-4 w-4" />
                </button>
                <button
                  onClick={() => setIsExpanded((value) => !value)}
                  className="rounded-md p-2 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
                  title={isExpanded ? "Compact view" : "Full page view"}
                >
                  {isExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                </button>
                <button
                  onClick={() => setIsOpen(false)}
                  className="rounded-md p-2 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
                  title="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </header>

            {showHistory ? (
              <div className="flex-1 overflow-y-auto">
                <div className="border-b border-border px-4 py-2">
                  <h3 className="text-sm font-medium text-text-secondary flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    Chat History
                  </h3>
                </div>
                {isLoadingHistory ? (
                  <div className="flex justify-center py-8">
                    <Loader2 className="h-5 w-5 animate-spin text-text-muted" />
                  </div>
                ) : (
                  <HistoryPanel
                    sessions={sessions}
                    onSelect={loadSession}
                    onDelete={deleteSession}
                  />
                )}
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto px-4 py-4">
                {messages.length === 0 ? (
                  <div className="flex h-full items-center justify-center text-center text-sm text-text-muted">
                    <div>
                      <Bot className="mx-auto mb-3 h-10 w-10 opacity-60" />
                      <p>Ask about {projectId}</p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {messages.map((message) => (
                      <div
                        key={message.id}
                        className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}
                      >
                        {message.role === "assistant" && (
                          <Bot className="mt-2 h-5 w-5 flex-shrink-0 text-accent-blue" />
                        )}
                        <div
                          className={`max-w-[86%] rounded-lg border px-3 py-2 text-sm leading-6 ${
                            message.role === "user"
                              ? "border-accent-blue/30 bg-accent-blue/15 text-text-primary"
                              : "border-border bg-bg-tertiary text-text-primary"
                          }`}
                        >
                          <div className="markdown-content break-words">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                code({ className, children, ...props }) {
                                  const isInline = !className;
                                  return isInline ? (
                                    <code className="rounded bg-bg-primary px-1 py-0.5 font-mono text-xs" {...props}>
                                      {children}
                                    </code>
                                  ) : (
                                    <code className={`rounded-lg bg-bg-primary p-3 font-mono text-xs block overflow-x-auto ${className}`} {...props}>
                                      {children}
                                    </code>
                                  );
                                },
                                pre({ children }) {
                                  return (
                                    <pre className="rounded-lg bg-bg-primary p-3 overflow-x-auto my-2">
                                      {children}
                                    </pre>
                                  );
                                },
                                a({ href, children }) {
                                  return (
                                    <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent-blue hover:underline">
                                      {children}
                                    </a>
                                  );
                                },
                                p({ children }) {
                                  return <p className="mb-2 last:mb-0">{children}</p>;
                                },
                                ul({ children }) {
                                  return <ul className="list-disc pl-5 mb-2">{children}</ul>;
                                },
                                ol({ children }) {
                                  return <ol className="list-decimal pl-5 mb-2">{children}</ol>;
                                },
                                li({ children }) {
                                  return <li className="mb-1">{children}</li>;
                                },
                                h1({ children }) {
                                  return <h1 className="text-lg font-bold mb-2 mt-3">{children}</h1>;
                                },
                                h2({ children }) {
                                  return <h2 className="text-base font-bold mb-2 mt-3">{children}</h2>;
                                },
                                h3({ children }) {
                                  return <h3 className="text-sm font-bold mb-1 mt-2">{children}</h3>;
                                },
                                blockquote({ children }) {
                                  return <blockquote className="border-l-2 border-accent-blue/50 pl-3 italic text-text-secondary my-2">{children}</blockquote>;
                                },
                              }}
                            >
                              {message.content}
                            </ReactMarkdown>
                          </div>
                          {message.role === "assistant" && (
                            <>
                              <StepTimeline steps={message.steps || []} />
                              <SourceList sources={message.sources || []} />
                            </>
                          )}
                        </div>
                        {message.role === "user" && (
                          <User className="mt-2 h-5 w-5 flex-shrink-0 text-accent-cyan" />
                        )}
                      </div>
                    ))}
                    {isSending && (
                      <div className="flex items-center gap-2 text-sm text-text-muted">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        CG-pilot is working
                      </div>
                    )}
                    {error && (
                      <div className="rounded-md border border-accent-red/30 bg-accent-red/10 px-3 py-2 text-sm text-accent-red">
                        {error}
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>
            )}

            {!showHistory && (
              <form onSubmit={handleSubmit} className="border-t border-border p-3">
                {attachedFilePath && (
                  <div className="mb-2 flex items-center gap-1.5 rounded-md border border-accent-blue/30 bg-accent-blue/10 px-2.5 py-1.5 text-xs text-text-secondary">
                    <FileText className="h-3.5 w-3.5 flex-shrink-0 text-accent-blue" />
                    <span className="truncate font-mono">{attachedFilePath}</span>
                    <button
                      type="button"
                      onClick={handleDismissFile}
                      className="ml-auto flex h-4 w-4 flex-shrink-0 items-center justify-center rounded text-text-muted hover:bg-bg-hover hover:text-text-primary"
                      title="Remove file from context"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                )}
                <div className="flex items-end gap-2">
                  <textarea
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        handleSubmit(event);
                      }
                    }}
                    disabled={!canChat || isSending}
                    placeholder={canChat ? "Ask CG-pilot..." : disabledReason}
                    rows={2}
                    className="min-h-[44px] flex-1 resize-none rounded-md border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary outline-none placeholder:text-text-muted focus:border-accent-blue disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <button
                    type="submit"
                    disabled={!input.trim() || !canChat || isSending}
                    className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-md bg-accent-blue text-white transition-colors hover:bg-accent-blue/80 disabled:cursor-not-allowed disabled:opacity-50"
                    title="Send"
                  >
                    {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </button>
                </div>
              </form>
            )}
          </section>
        </>
      )}
    </>
  );
}
