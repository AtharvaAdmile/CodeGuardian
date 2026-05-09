import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  FileText,
  Loader2,
  Maximize2,
  MessageCircle,
  Minimize2,
  Send,
  User,
  Wrench,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { askCGPilot, getCGPilotStatus } from "../lib/api";
import type { CGPilotStatus, CGPilotToolUse, SourceRef } from "../lib/types";

interface CGPilotProps {
  projectId: string;
  projectPath: string;
  indexStatus?: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  tools?: CGPilotToolUse[];
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

function ToolList({ tools }: { tools: CGPilotToolUse[] }) {
  if (tools.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {tools.slice(0, 5).map((tool, index) => (
        <span
          key={`${tool.name}-${index}`}
          className="inline-flex items-center gap-1 rounded-md border border-border bg-bg-tertiary px-2 py-1 text-xs text-text-muted"
          title={tool.summary}
        >
          <Wrench className="h-3 w-3" />
          {tool.name}
        </span>
      ))}
    </div>
  );
}

export function CGPilot({ projectId, projectPath, indexStatus }: CGPilotProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [status, setStatus] = useState<CGPilotStatus | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

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
  }, [messages, isSending, isOpen, isExpanded]);

  const disabledReason = useMemo(() => {
    if (isIndexing) return "Indexing is still running.";
    if (!status) return "Checking project index.";
    if (!status.ready) return status.reason || "CG-pilot is not ready.";
    return "";
  }, [isIndexing, status]);

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
      const response = await askCGPilot(projectId, projectPath, text, history);
      setMessages((current) => [
        ...current,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          tools: response.tools_used,
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
                            <ToolList tools={message.tools || []} />
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

            <form onSubmit={handleSubmit} className="border-t border-border p-3">
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
          </section>
        </>
      )}
    </>
  );
}
