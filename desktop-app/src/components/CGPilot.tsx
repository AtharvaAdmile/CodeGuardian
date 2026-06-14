import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { X, Trash2, Copy } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  askCGPilot,
  getCGPilotStatus,
  getChatHistory,
  getChatSession,
  deleteChatSession,
} from "../lib/api";
import type {
  CGPilotStep,
  CGPilotStatus,
  CGPilotToolUse,
  ChatSessionSummary,
  SourceRef,
} from "../lib/types";
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

// ── helpers ──────────────────────────────────────────────────────────────────

function stepLabel(action: string): string {
  switch (action) {
    case "plan":        return "PLANNING";
    case "tool_call":   return "WORKING_";
    case "observation": return "OBSERVE_";
    case "final":       return "COMPLETE";
    default:            return action.toUpperCase().slice(0, 8).padEnd(8, "_");
  }
}

function SpinChar() {
  const FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"];
  const [f, setF] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setF((x) => (x + 1) % FRAMES.length), 120);
    return () => clearInterval(t);
  }, []);
  return <span className="text-primary select-none">{FRAMES[f]}</span>;
}

// ── sub-components ────────────────────────────────────────────────────────────

function ExecutionLog({ steps }: { steps: CGPilotStep[] }) {
  if (steps.length === 0) return null;
  return (
    <details className="mb-3 group">
      <summary className="cursor-pointer list-none flex items-center gap-2 text-secondary text-[10px] font-extrabold tracking-[0.08em] border border-secondary/30 px-2 py-1.5 hover:bg-secondary/5 transition-colors select-none">
        <span className="transition-transform group-open:rotate-90 inline-block">▶</span>
        ┌ EXECUTION_LOG: {steps.length} STEP{steps.length !== 1 ? "S" : ""} TAKEN
      </summary>
      <div className="mt-1.5 ml-3 border-l border-outline-variant pl-3 py-1 font-mono text-[10px] text-on-surface-variant space-y-0.5">
        {steps.map((step, i) => {
          const isLast = i === steps.length - 1;
          const connector = isLast ? "└─" : "├─";
          const label = stepLabel(step.action);
          const detail = step.tool_name || step.message || step.tool_summary || "";
          return (
            <p key={i} className="leading-5">
              {connector} [{label}]{" "}
              {step.tool_name && (
                <span className="text-primary">{step.tool_name} </span>
              )}
              {detail && step.tool_name !== detail && (
                <span className="text-on-surface-variant/70">
                  {detail.slice(0, 80)}
                </span>
              )}
            </p>
          );
        })}
      </div>
    </details>
  );
}

function SourceChip({ source }: { source: SourceRef }) {
  const path = source.file_path
    ? source.file_path + (source.start_line ? `:${source.start_line}` : "")
    : "";
  if (!path) return null;
  return (
    <div className="flex items-center gap-2 bg-surface-container-highest px-2.5 py-1 border border-outline-variant w-fit hover:border-primary cursor-pointer group transition-colors">
      <span className="text-primary text-[10px] font-mono shrink-0">📄</span>
      <span className="font-mono text-[10px] text-primary truncate max-w-[200px]">{path}</span>
    </div>
  );
}

function SourceList({ sources }: { sources: SourceRef[] }) {
  if (sources.length === 0) return null;
  const deduped = sources.filter(
    (s, i, all) =>
      all.findIndex((x) => x.file_path === s.file_path && x.start_line === s.start_line) === i
  );
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {deduped.slice(0, 6).map((s, i) => (
        <SourceChip key={i} source={s} />
      ))}
    </div>
  );
}

function CodeBlock({ children, language }: { children: string; language?: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(children).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="my-3 border border-outline-variant bg-black overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1 border-b border-outline-variant bg-surface-container">
        <span className="text-[9px] font-extrabold tracking-[0.12em] text-on-surface-variant uppercase">
          {language || "SHELL"}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[9px] text-on-surface-variant hover:text-primary transition-colors"
        >
          <Copy className="w-2.5 h-2.5" />
          {copied ? "COPIED" : "COPY"}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto font-mono text-[11px] leading-5 text-terminal-white">
        <code>{children}</code>
      </pre>
    </div>
  );
}

function AssistantBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="flex flex-col items-start">
      <div className="w-[90%]">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-[10px] font-extrabold tracking-[0.1em] text-secondary">
            CG_PILOT
          </span>
        </div>
        <div className="tui-border bg-surface-container-low p-4">
          <span className="tui-border-title text-primary">RESPONSE</span>
          <div className="text-[12px] text-on-surface leading-6 break-words">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || "");
                  const isBlock = Boolean(className);
                  const content = String(children).replace(/\n$/, "");
                  if (isBlock) {
                    return <CodeBlock language={match?.[1]?.toUpperCase()}>{content}</CodeBlock>;
                  }
                  return (
                    <code
                      className="bg-black border border-outline-variant px-1.5 py-0.5 font-mono text-[10px] text-primary"
                      {...props}
                    >
                      {children}
                    </code>
                  );
                },
                pre({ children }) {
                  return <>{children}</>;
                },
                p({ children }) {
                  return <p className="mb-3 last:mb-0">{children}</p>;
                },
                ul({ children }) {
                  return <ul className="list-none pl-3 mb-2 space-y-1">{children}</ul>;
                },
                ol({ children }) {
                  return <ol className="list-none pl-3 mb-2 space-y-1">{children}</ol>;
                },
                li({ children }) {
                  return (
                    <li className="flex items-baseline gap-2">
                      <span className="text-primary shrink-0">·</span>
                      <span>{children}</span>
                    </li>
                  );
                },
                h1({ children }) {
                  return <h1 className="text-[14px] font-extrabold uppercase tracking-[0.08em] mb-2 mt-3 text-on-surface">{children}</h1>;
                },
                h2({ children }) {
                  return <h2 className="text-[12px] font-extrabold uppercase tracking-[0.08em] mb-2 mt-3 text-primary">{children}</h2>;
                },
                h3({ children }) {
                  return <h3 className="text-[11px] font-extrabold uppercase mb-1 mt-2 text-on-surface">{children}</h3>;
                },
                blockquote({ children }) {
                  return (
                    <blockquote className="border-l-2 border-tertiary pl-3 text-on-surface-variant my-2 italic">
                      {children}
                    </blockquote>
                  );
                },
                a({ href, children }) {
                  return (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary underline hover:text-primary-container"
                    >
                      {children}
                    </a>
                  );
                },
                strong({ children }) {
                  return <strong className="text-primary font-bold">{children}</strong>;
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
          {message.steps && message.steps.length > 0 && (
            <ExecutionLog steps={message.steps} />
          )}
          {message.sources && message.sources.length > 0 && (
            <SourceList sources={message.sources} />
          )}
        </div>
      </div>
    </div>
  );
}

function HistoryPanel({
  sessions,
  onSelect,
  onDelete,
  isLoading,
}: {
  sessions: ChatSessionSummary[];
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-12 gap-2 text-[11px] text-on-surface-variant font-mono">
        <SpinChar />
        <span>LOADING_SESSIONS...</span>
      </div>
    );
  }
  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 font-mono text-on-surface-variant text-[11px] uppercase tracking-[0.1em]">
        <p>-- NULL_HISTORY --</p>
        <p className="text-[10px] mt-1 normal-case text-outline">no chat sessions yet</p>
      </div>
    );
  }
  return (
    <div className="divide-y divide-outline-variant/30">
      {sessions.map((s, i) => (
        <div
          key={s.session_id}
          className="group flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-surface-container-high transition-colors font-mono"
          onClick={() => onSelect(s.session_id)}
        >
          <span className="text-outline text-[10px] shrink-0 tabular-nums">
            [{String(i + 1).padStart(2, "0")}]
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] text-on-surface truncate">
              {s.title || "(untitled)"}
            </p>
            <p className="text-[10px] text-on-surface-variant mt-0.5">
              {s.message_count} msg{s.message_count !== 1 ? "s" : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(s.session_id);
            }}
            className="shrink-0 p-1 text-on-surface-variant opacity-0 group-hover:opacity-100 hover:text-terminal-error transition-all"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      ))}
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export function CGPilot({
  projectId,
  projectPath,
  indexStatus,
  pendingSessionId,
  onClearPendingSession,
}: CGPilotProps) {
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
        if (!cancelled) setStatus(result);
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
    if (isIndexing) return "Indexing in progress — please wait.";
    if (!status) return "Checking index status...";
    if (!status.ready) return status.reason || "Not ready.";
    return "";
  }, [isIndexing, status]);

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
    if (showHistory) loadSessions();
  }, [showHistory, loadSessions]);

  const loadSession = useCallback(
    async (sid: string) => {
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
    },
    [projectId]
  );

  const newChat = useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setError(null);
    setShowHistory(false);
  }, []);

  const deleteSession = useCallback(
    async (sid: string) => {
      try {
        await deleteChatSession(projectId, sid);
        setSessions((prev) => prev.filter((s) => s.session_id !== sid));
        if (sessionId === sid) newChat();
      } catch {
        // ignore
      }
    },
    [projectId, sessionId, newChat]
  );

  useEffect(() => {
    if (pendingSessionId) {
      setIsOpen(true);
      loadSession(pendingSessionId);
      onClearPendingSession?.();
    }
  }, [pendingSessionId, loadSession, onClearPendingSession]);

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
      const history = messages.slice(-10).map((m) => ({
        role: m.role,
        content: m.content,
      }));
      const fileContext = attachedFilePath
        ? { file_path: attachedFilePath }
        : undefined;
      const response = await askCGPilot(
        projectId,
        projectPath,
        text,
        history,
        fileContext,
        sessionId ?? undefined
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

  // ── panel sizing ──────────────────────────────────────────────────────────

  const panelClasses = isExpanded
    ? "fixed inset-4 z-50 flex flex-col overflow-hidden border border-outline-variant bg-surface font-mono shadow-2xl"
    : "fixed bottom-20 right-6 z-50 flex h-[600px] w-[480px] max-h-[calc(100vh-7rem)] max-w-[calc(100vw-3rem)] flex-col overflow-hidden border border-outline-variant bg-surface font-mono shadow-2xl";

  // Line count proxy (rough: count total chars / 80 per line)
  const approxLines = messages.reduce((s, m) => s + Math.ceil(m.content.length / 80), 0);

  return (
    <>
      {/* FAB */}
      <button
        onClick={() => setIsOpen((v) => !v)}
        className={`fixed bottom-8 right-6 z-40 px-3 py-2 font-mono text-[11px] font-extrabold tracking-[0.1em] transition-colors ${
          isOpen
            ? "bg-terminal-error/10 border border-terminal-error text-terminal-error hover:bg-terminal-error hover:text-surface"
            : "bg-primary text-on-primary hover:bg-primary-container"
        }`}
        title="CG-Pilot"
      >
        {isOpen ? "[ CLOSE ]" : ">_ CG-PILOT"}
      </button>

      {isOpen && (
        <>
          {isExpanded && (
            <div
              className="fixed inset-0 z-40 bg-black/60"
              onClick={() => setIsExpanded(false)}
            />
          )}

          <section className={panelClasses}>
            {/* ── Header ─────────────────────────────────────────────────── */}
            <header className="flex items-center justify-between px-4 h-12 border-b border-outline-variant bg-surface shrink-0">
              <div className="flex items-center gap-3">
                <span className="text-primary font-extrabold text-[14px] tracking-[0.06em]">
                  CG-Pilot
                </span>
                <span
                  className={`text-[10px] font-extrabold tracking-[0.1em] px-2 border ${
                    canChat
                      ? "border-secondary text-secondary"
                      : isIndexing
                      ? "border-tertiary text-tertiary"
                      : "border-outline-variant text-on-surface-variant"
                  }`}
                >
                  {canChat ? "READY" : isIndexing ? "INDEXING" : "STANDBY"}
                </span>
                <div className="hidden sm:flex items-center gap-4 ml-2">
                  <button
                    onClick={() => setShowHistory(false)}
                    className={`text-[12px] pb-0.5 transition-colors ${
                      !showHistory
                        ? "text-primary border-b-2 border-primary"
                        : "text-on-surface-variant hover:text-primary"
                    }`}
                  >
                    Console
                  </button>
                  <button
                    onClick={() => setShowHistory(true)}
                    className={`text-[12px] pb-0.5 transition-colors ${
                      showHistory
                        ? "text-primary border-b-2 border-primary"
                        : "text-on-surface-variant hover:text-primary"
                    }`}
                  >
                    History
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={newChat}
                  className="px-1.5 py-1 text-[10px] font-mono text-on-surface-variant hover:text-primary hover:bg-surface-container-high transition-colors"
                  title="New chat"
                >
                  [NEW]
                </button>
                <button
                  onClick={() => setIsExpanded((v) => !v)}
                  className="px-1.5 py-1 text-[10px] font-mono text-on-surface-variant hover:text-primary hover:bg-surface-container-high transition-colors"
                  title={isExpanded ? "Compact" : "Expand"}
                >
                  {isExpanded ? "[MIN]" : "[MAX]"}
                </button>
                <button
                  onClick={() => setIsOpen(false)}
                  className="px-1.5 py-1 text-[10px] font-mono text-on-surface-variant hover:text-terminal-error transition-colors"
                  title="Close"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            </header>

            {/* ── History view ───────────────────────────────────────────── */}
            {showHistory ? (
              <div className="flex-1 overflow-y-auto">
                <div className="px-4 py-2 border-b border-outline-variant bg-surface-container text-[10px] font-extrabold tracking-[0.1em] text-on-surface uppercase">
                  ┌─ CHAT_HISTORY ─┐
                </div>
                <HistoryPanel
                  sessions={sessions}
                  onSelect={loadSession}
                  onDelete={deleteSession}
                  isLoading={isLoadingHistory}
                />
              </div>
            ) : (
              /* ── Chat view ─────────────────────────────────────────────── */
              <>
                <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
                  {/* System init banner */}
                  <div className="font-mono text-[10px] text-outline space-y-0.5">
                    <p>[ SYSTEM ] Kernel initialised — CodeGuardian v2.4.0-Archon</p>
                    <p>[ SYSTEM ] Handshaking with remote server... DONE</p>
                    <p>
                      [ SYSTEM ] Context: project <span className="text-primary">{projectId}</span>{" "}
                      {canChat
                        ? "· INDEXED_AND_READY"
                        : isIndexing
                        ? "· INDEXING_IN_PROGRESS"
                        : "· NOT_INDEXED"}
                    </p>
                  </div>

                  {messages.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-16 text-center font-mono">
                      <p className="text-[12px] text-on-surface-variant uppercase tracking-[0.12em]">
                        -- AWAITING_QUERY --
                      </p>
                      {!canChat && (
                        <p className="text-[10px] text-tertiary mt-3 max-w-[280px] leading-5">
                          {disabledReason}
                        </p>
                      )}
                    </div>
                  )}

                  {messages.map((message) =>
                    message.role === "user" ? (
                      /* user bubble */
                      <div key={message.id} className="flex flex-col items-end">
                        <div className="max-w-[80%]">
                          <div className="flex items-center gap-2 mb-1.5 justify-end text-[10px] font-extrabold tracking-[0.1em] text-primary">
                            OPERATOR_01
                          </div>
                          <div className="bg-surface-container-high border-r-2 border-primary px-3 py-2 text-[12px] leading-6">
                            <span className="text-primary font-bold mr-2">$</span>
                            {message.content}
                          </div>
                        </div>
                      </div>
                    ) : (
                      /* assistant bubble */
                      <AssistantBubble key={message.id} message={message} />
                    )
                  )}

                  {isSending && (
                    <div className="flex flex-col items-start">
                      <div className="w-[90%]">
                        <div className="flex items-center gap-2 mb-1.5 text-[10px] font-extrabold tracking-[0.1em] text-secondary">
                          CG_PILOT
                        </div>
                        <div className="tui-border bg-surface-container-low px-4 py-3">
                          <span className="tui-border-title text-primary">RESPONSE</span>
                          <div className="flex items-center gap-3 text-[12px] text-on-surface-variant">
                            <SpinChar />
                            <span>Processing query...</span>
                            <span className="inline-block w-2 h-4 bg-primary cursor-blink" />
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {error && (
                    <div className="border border-terminal-error/40 bg-terminal-error/5 px-3 py-2 font-mono text-[11px] text-terminal-error">
                      [ ERR ] {error}
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </div>

                {/* ── Input area ─────────────────────────────────────────── */}
                <form
                  onSubmit={handleSubmit}
                  className="shrink-0 border-t border-outline-variant bg-surface-container-lowest"
                >
                  {/* Attachment bar */}
                  {attachedFilePath && (
                    <div className="flex items-center gap-3 px-4 py-1.5 border-b border-outline-variant">
                      <span className="text-on-surface-variant text-[11px]">📎</span>
                      <span className="text-primary bg-primary/10 px-2 py-0.5 border border-primary/30 text-[10px] font-mono flex items-center gap-1.5">
                        {attachedFilePath}
                        <button
                          type="button"
                          onClick={handleDismissFile}
                          className="text-on-surface-variant hover:text-terminal-error transition-colors"
                        >
                          <X className="w-2.5 h-2.5" />
                        </button>
                      </span>
                      <span className="ml-auto text-[9px] font-extrabold tracking-[0.1em] text-outline">
                        FILE_CONTEXT_ACTIVE
                      </span>
                    </div>
                  )}

                  {/* Input row */}
                  <div className="flex items-center px-4 py-2">
                    <span className="text-primary font-bold text-[16px] mr-3 shrink-0">&gt;</span>
                    <textarea
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          handleSubmit(e);
                        }
                      }}
                      disabled={!canChat || isSending}
                      placeholder={canChat ? "Ask CG-Pilot..." : disabledReason}
                      rows={2}
                      className="flex-1 resize-none bg-transparent text-[12px] text-on-surface outline-none placeholder:text-outline disabled:cursor-not-allowed disabled:opacity-60 font-mono py-1 leading-5"
                    />
                    <button
                      type="submit"
                      disabled={!input.trim() || !canChat || isSending}
                      className="ml-3 bg-primary text-on-primary px-3 py-2 hover:bg-primary-container transition-colors disabled:opacity-30 disabled:cursor-not-allowed shrink-0 text-[11px] font-extrabold"
                      title="Send"
                    >
                      {isSending ? <SpinChar /> : "[›]"}
                    </button>
                  </div>

                  {/* Status bar */}
                  <div className="flex items-center justify-between px-4 py-1.5 border-t border-outline-variant/40 text-[9px] font-extrabold tracking-[0.08em] text-outline">
                    <div className="flex gap-3">
                      <span>L: {approxLines}</span>
                      <span>UTF-8</span>
                      <span>NORMAL</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-1.5 h-1.5 ${
                          canChat ? "bg-secondary animate-pulse" : "bg-outline-variant"
                        }`}
                      />
                      <span>
                        {canChat
                          ? "REMOTE_CONSOLE_CONNECTED"
                          : isIndexing
                          ? "INDEXING_IN_PROGRESS"
                          : "CONSOLE_STANDBY"}
                      </span>
                    </div>
                  </div>
                </form>
              </>
            )}
          </section>
        </>
      )}
    </>
  );
}
