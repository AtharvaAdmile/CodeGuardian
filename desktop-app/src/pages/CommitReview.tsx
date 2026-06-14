import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileText,
  Filter,
  GitBranch,
  RefreshCw,
} from "lucide-react";
import { useProjectContext } from "../App";
import { commitReviewedChanges, getCommitReviewStatus } from "../lib/api";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import type { CommitFileChange, CommitHistoryEntry, CommitReviewResponse } from "../lib/types";

const HISTORY_LIMIT = 10;

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return dateStr;
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  if (diffDays === 1) return "Yesterday";
  return `${diffDays}d ago`;
}

function changeScope(change: CommitFileChange) {
  if (change.untracked) return "UNTRACKED";
  if (change.staged && change.unstaged) return "STAGED+UNSTAGED";
  if (change.staged) return "STAGED";
  if (change.unstaged) return "UNSTAGED";
  return change.status?.toUpperCase() || "CHANGED";
}

function scopeColor(change: CommitFileChange) {
  if (change.untracked) return "border-primary/40 text-primary";
  if (change.staged && change.unstaged) return "border-tertiary/40 text-tertiary";
  if (change.staged) return "border-secondary/40 text-secondary";
  return "border-outline text-on-surface-variant";
}

function AsciiBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="h-1.5 w-full bg-surface-container-high">
      <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
    </div>
  );
}

function DiffBlock({ diff }: { diff: string }) {
  if (!diff) {
    return (
      <div className="px-4 py-3 text-[11px] text-outline font-mono">
        -- NO DIFF AVAILABLE --
      </div>
    );
  }
  return (
    <pre className="max-h-72 overflow-auto bg-surface-container-lowest px-4 py-3 text-[11px] leading-relaxed text-on-surface-variant font-mono whitespace-pre-wrap">
      {diff}
    </pre>
  );
}

function CurrentChangeRow({
  change,
  isExpanded,
  onToggle,
}: {
  change: CommitFileChange;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="border border-outline-variant bg-surface-container-lowest hover:border-secondary transition-colors group">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left"
      >
        <FileText className="w-3.5 h-3.5 shrink-0 text-on-surface-variant" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] text-on-surface font-mono">{change.file_path}</div>
          <span className={`inline-block mt-0.5 text-[10px] border px-1.5 uppercase tracking-wider ${scopeColor(change)}`}>
            {changeScope(change)}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-[12px] font-mono">
          <span className="text-secondary">+{change.additions}</span>
          <span className="text-terminal-error">-{change.deletions}</span>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-on-surface-variant" />
          ) : (
            <ChevronDown className="w-4 h-4 text-on-surface-variant group-hover:text-secondary transition-colors" />
          )}
        </div>
      </button>
      {isExpanded && (
        <div className="border-t border-outline-variant">
          <DiffBlock diff={change.diff} />
        </div>
      )}
    </div>
  );
}

function CommitHistoryRow({
  commit,
  isExpanded,
  onToggle,
}: {
  commit: CommitHistoryEntry;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="border border-outline-variant bg-surface-container-lowest hover:border-secondary transition-colors group cursor-pointer">
      <div
        className="p-3 border-b border-outline-variant flex justify-between items-center"
        onClick={onToggle}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-secondary font-bold text-[12px] shrink-0 font-mono">
            {commit.short_sha}
          </span>
          <div className="h-3 w-px bg-outline-variant shrink-0" />
          <span className="text-on-surface-variant text-[12px] font-mono shrink-0">
            {formatRelativeTime(commit.date)}
          </span>
        </div>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-on-surface-variant shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-on-surface-variant group-hover:text-secondary transition-colors shrink-0" />
        )}
      </div>
      <div className="p-3 space-y-2" onClick={onToggle}>
        <p className="text-[13px] font-bold text-on-surface">{commit.message}</p>
        <div className="flex items-center justify-between">
          <div className="flex gap-4 text-[12px] font-mono">
            <span className="text-on-surface-variant">{commit.author}</span>
            <span className="flex items-center gap-1 text-on-surface-variant">
              <FileText className="w-3 h-3" />
              {commit.files.length} file{commit.files.length !== 1 ? "s" : ""}
            </span>
          </div>
          <div className="flex gap-3 text-[12px] font-mono">
            <span className="text-secondary">+{commit.insertions}</span>
            <span className="text-terminal-error">-{commit.deletions}</span>
          </div>
        </div>
      </div>
      {isExpanded && (
        <div className="border-t border-outline-variant">
          <div className="grid gap-2 px-3 py-3 sm:grid-cols-2">
            {commit.files.map((file) => (
              <div
                key={`${commit.sha}-${file.file_path}`}
                className="bg-surface-container px-3 py-2 border border-outline-variant/50"
              >
                <div className="truncate text-[11px] text-on-surface font-mono">{file.file_path}</div>
                <div className="mt-1 flex items-center gap-3 text-[11px] font-mono">
                  <span className="text-on-surface-variant">{file.status}</span>
                  <span className="text-secondary">+{file.additions}</span>
                  <span className="text-terminal-error">-{file.deletions}</span>
                </div>
              </div>
            ))}
          </div>
          <DiffBlock diff={commit.diff} />
        </div>
      )}
    </div>
  );
}

export default function CommitReview() {
  const { projectPath, projectName } = useProjectContext();
  const [status, setStatus] = useState<CommitReviewResponse | null>(null);
  const [commitMessage, setCommitMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isCommitting, setIsCommitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [expandedFile, setExpandedFile] = useState<string | null>(null);
  const [expandedCommit, setExpandedCommit] = useState<string | null>(null);

  const loadStatus = async () => {
    if (!projectPath) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await getCommitReviewStatus(projectPath, HISTORY_LIMIT);
      setStatus(result);
      if (!commitMessage.trim()) {
        setCommitMessage(result.recommendation.suggested_message);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, [projectPath]);

  const totals = useMemo(() => {
    const files = status?.uncommitted_files ?? [];
    return {
      additions: files.reduce((sum, f) => sum + f.additions, 0),
      deletions: files.reduce((sum, f) => sum + f.deletions, 0),
    };
  }, [status]);

  const handleCommit = async () => {
    if (!projectPath || !commitMessage.trim()) return;
    setIsCommitting(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await commitReviewedChanges(projectPath, commitMessage.trim(), HISTORY_LIMIT);
      if (result.error) setError(result.error);
      if (result.status) setStatus(result.status);
      if (result.committed) {
        setSuccess(`[${result.commit_sha.slice(0, 7)}] ${result.message}`);
        setCommitMessage(result.status?.recommendation.suggested_message ?? "");
        setExpandedFile(null);
        setExpandedCommit(result.commit_sha);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsCommitting(false);
    }
  };

  const canCommit = Boolean(status?.has_changes && commitMessage.trim() && !isCommitting);
  const totalFiles = (status?.staged_files ?? 0) + (status?.unstaged_files ?? 0) + (status?.untracked_files ?? 0);
  const isClean = status ? !status.has_changes : false;

  return (
    <div className="flex h-full font-mono overflow-hidden">
      {/* ── Left Column: Commit Controls ── */}
      <section className="w-1/2 border-r border-outline-variant flex flex-col overflow-y-auto bg-surface">
        <div className="p-4 space-y-4">
          {/* Page header */}
          <div className="flex items-center gap-2 pt-2">
            <span className="text-secondary font-bold">$</span>
            <h2 className="text-[20px] font-bold text-on-surface tracking-tight">
              COMMIT_REVIEW_MGR
            </h2>
            <span className="cursor-blink text-secondary">█</span>
          </div>

          {/* Branch / HEAD info */}
          {status && (
            <div className="flex items-center gap-3 text-[11px] text-on-surface-variant">
              <GitBranch className="w-3 h-3 text-primary shrink-0" />
              <span className="text-primary font-mono">{status.branch}</span>
              <span className="text-outline-variant">·</span>
              <span className="font-mono text-outline">{status.head_sha.slice(0, 7)}</span>
              <span className="text-outline-variant">·</span>
              <span className="truncate text-on-surface-variant">{projectName}</span>
            </div>
          )}

          {/* Alerts */}
          {error && (
            <div className="border border-terminal-error/30 bg-terminal-error/5 px-3 py-2 text-[12px] text-terminal-error font-mono">
              [ERR] {error}
            </div>
          )}
          {success && (
            <div className="border border-secondary/30 bg-secondary/5 px-3 py-2 text-[12px] text-secondary font-mono">
              [OK] {success}
            </div>
          )}

          {/* Status card */}
          <div
            className={`tui-border p-4 mt-4 ${
              isClean
                ? "border-secondary/50 bg-secondary/5"
                : "border-tertiary/50 bg-tertiary/5"
            }`}
          >
            <span className={`tui-border-title ${isClean ? "text-secondary" : "text-tertiary"}`}>
              ┌─ STATUS ──┐
            </span>
            <div className="flex items-center gap-3 pt-1">
              {isClean ? (
                <CheckCircle2 className="w-7 h-7 text-secondary shrink-0" />
              ) : (
                <AlertTriangle className="w-7 h-7 text-tertiary shrink-0" />
              )}
              <div className="min-w-0">
                <p className={`font-bold text-[13px] ${isClean ? "text-secondary" : "text-tertiary"}`}>
                  {status?.recommendation.title ?? "Review status"}
                </p>
                <p className="text-[11px] text-on-surface-variant mt-0.5">
                  {status?.recommendation.reason ?? "Loading git status..."}
                </p>
              </div>
            </div>
            {Boolean(status?.recommendation.concerns.length) && (
              <div className="mt-3 space-y-1">
                {status?.recommendation.concerns.map((concern) => (
                  <div
                    key={concern}
                    className="text-[11px] text-tertiary border-l-2 border-tertiary/40 pl-2"
                  >
                    [WARN] {concern}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Summary Grid */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "STAGED",    value: status?.staged_files    ?? 0 },
              { label: "UNSTAGED",  value: status?.unstaged_files  ?? 0 },
              { label: "UNTRACKED", value: status?.untracked_files ?? 0 },
            ].map(({ label, value }) => (
              <div key={label} className="border border-outline-variant p-3 space-y-2">
                <p className="text-[11px] font-extrabold tracking-[0.1em] uppercase text-on-surface-variant opacity-60">
                  {label}
                </p>
                <p className="text-[24px] font-bold leading-tight text-on-surface">{value}</p>
                <AsciiBar value={value} max={Math.max(totalFiles, 1)} />
              </div>
            ))}
          </div>

          {/* Commit Form */}
          <div className="space-y-3 pt-2">
            <div className="border border-outline-variant bg-surface-container-lowest p-4 focus-within:border-primary transition-colors">
              <div className="flex items-center gap-2 mb-2 text-on-surface-variant text-[12px]">
                <span>&gt; git commit -m &quot;</span>
                <span className="cursor-blink text-secondary">█</span>
              </div>
              <textarea
                value={commitMessage}
                onChange={(e) => setCommitMessage(e.target.value)}
                placeholder="Enter commit message..."
                rows={3}
                className="w-full bg-transparent border-none outline-none text-on-surface text-[12px] font-mono placeholder:text-outline resize-none p-0"
              />
              <div className="text-right text-on-surface-variant text-[12px] opacity-40">&quot;</div>
            </div>
            <button
              onClick={handleCommit}
              disabled={!canCommit}
              className="w-full py-3 text-[12px] font-bold bg-secondary text-on-secondary hover:brightness-110 active:scale-[0.99] transition-all disabled:opacity-30 disabled:cursor-not-allowed uppercase tracking-wider"
            >
              {isCommitting ? "[ COMMITTING... ]" : "[ STAGE_AND_COMMIT ]"}
            </button>
          </div>

          {/* Uncommitted Files */}
          <div className="border-t border-outline-variant pt-4">
            <h3 className="text-[11px] font-extrabold tracking-[0.1em] uppercase text-on-surface-variant mb-3 flex items-center gap-2">
              <FileText className="w-3.5 h-3.5" />
              UNCOMMITTED_FILES
              {totals.additions > 0 && (
                <span className="ml-auto text-secondary font-mono">+{totals.additions}</span>
              )}
              {totals.deletions > 0 && (
                <span className="text-terminal-error font-mono">-{totals.deletions}</span>
              )}
            </h3>
            {isLoading && !status ? (
              <div className="flex items-center justify-center py-10">
                <LoadingSpinner size="lg" />
              </div>
            ) : status?.uncommitted_files.length === 0 ? (
              <div className="bg-surface-container-low p-8 border border-dashed border-outline-variant text-center">
                <p className="text-[12px] text-on-surface-variant italic">
                  # Working tree clean
                </p>
                <p className="text-[11px] text-outline mt-1">
                  No changes detected in monitored directories.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {status?.uncommitted_files.map((change) => (
                  <CurrentChangeRow
                    key={change.file_path}
                    change={change}
                    isExpanded={expandedFile === change.file_path}
                    onToggle={() =>
                      setExpandedFile(expandedFile === change.file_path ? null : change.file_path)
                    }
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── Right Column: Git History ── */}
      <section className="w-1/2 flex flex-col bg-surface overflow-hidden">
        <div className="px-4 py-3 border-b border-outline-variant flex justify-between items-center shrink-0">
          <h2 className="text-[11px] font-extrabold tracking-[0.1em] uppercase text-on-surface-variant flex items-center gap-2">
            <GitBranch className="w-3.5 h-3.5 text-secondary" />
            RECENT_GIT_HISTORY
          </h2>
          <div className="flex gap-2">
            <button
              onClick={loadStatus}
              disabled={isLoading}
              className="p-1 border border-outline-variant text-on-surface-variant hover:border-primary hover:text-primary transition-colors disabled:opacity-50"
              title="Refresh"
            >
              {isLoading ? (
                <LoadingSpinner size="sm" />
              ) : (
                <RefreshCw className="w-3.5 h-3.5" />
              )}
            </button>
            <button
              className="p-1 border border-outline-variant text-on-surface-variant hover:border-primary hover:text-primary transition-colors"
              title="Filter"
            >
              <Filter className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {!status && isLoading && (
            <div className="flex items-center justify-center py-10">
              <LoadingSpinner size="lg" />
            </div>
          )}
          {status?.recent_commits.map((commit) => (
            <CommitHistoryRow
              key={commit.sha}
              commit={commit}
              isExpanded={expandedCommit === commit.sha}
              onToggle={() =>
                setExpandedCommit(expandedCommit === commit.sha ? null : commit.sha)
              }
            />
          ))}
          {status && status.recent_commits.length === 0 && (
            <div className="border border-outline-variant bg-surface-container-lowest px-4 py-8 text-center">
              <p className="text-[12px] text-outline uppercase tracking-wider">
                -- NO COMMITS FOUND --
              </p>
            </div>
          )}
          {status && status.recent_commits.length >= HISTORY_LIMIT && (
            <div className="text-center py-2">
              <button
                onClick={loadStatus}
                className="text-[11px] font-extrabold tracking-[0.1em] text-on-surface-variant hover:text-secondary transition-colors uppercase"
              >
                -- LOAD_MORE_COMMITS --
              </button>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
