import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileText,
  GitBranch,
  GitCommit,
  History,
  Minus,
  Plus,
  RefreshCw,
  Send,
} from "lucide-react";
import { useProjectContext } from "../App";
import { commitReviewedChanges, getCommitReviewStatus } from "../lib/api";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import type { CommitFileChange, CommitHistoryEntry, CommitReviewResponse } from "../lib/types";

const HISTORY_LIMIT = 10;

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date);
}

function changeScope(change: CommitFileChange) {
  if (change.untracked) return "Untracked";
  if (change.staged && change.unstaged) return "Staged + unstaged";
  if (change.staged) return "Staged";
  if (change.unstaged) return "Unstaged";
  return change.status || "Changed";
}

function statusTone(change: CommitFileChange) {
  if (change.untracked) return "border-accent-cyan/30 text-accent-cyan bg-accent-cyan/10";
  if (change.staged && change.unstaged) return "border-accent-amber/30 text-accent-amber bg-accent-amber/10";
  if (change.staged) return "border-accent-green/30 text-accent-green bg-accent-green/10";
  return "border-accent-blue/30 text-accent-blue bg-accent-blue/10";
}

function DiffBlock({ diff }: { diff: string }) {
  if (!diff) {
    return <div className="px-4 py-3 text-sm text-text-muted">No textual diff available.</div>;
  }

  return (
    <pre className="max-h-80 overflow-auto bg-bg-primary px-4 py-3 text-xs leading-relaxed text-text-secondary">
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
    <div className="overflow-hidden rounded-lg border border-border bg-bg-secondary">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-bg-hover"
      >
        <FileText className="h-4 w-4 flex-shrink-0 text-text-muted" />
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-sm text-text-primary">{change.file_path}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
            <span className={`rounded-md border px-2 py-0.5 ${statusTone(change)}`}>
              {changeScope(change)}
            </span>
            <span className="text-text-muted">status {change.status}</span>
          </div>
        </div>
        <div className="flex flex-shrink-0 items-center gap-3 text-sm">
          <span className="flex items-center gap-1 text-accent-green">
            <Plus className="h-3.5 w-3.5" />
            {change.additions}
          </span>
          <span className="flex items-center gap-1 text-accent-red">
            <Minus className="h-3.5 w-3.5" />
            {change.deletions}
          </span>
          {isExpanded ? (
            <ChevronUp className="h-5 w-5 text-text-muted" />
          ) : (
            <ChevronDown className="h-5 w-5 text-text-muted" />
          )}
        </div>
      </button>
      {isExpanded && <DiffBlock diff={change.diff} />}
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
    <div className="overflow-hidden rounded-lg border border-border bg-bg-secondary">
      <button
        onClick={onToggle}
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-bg-hover"
      >
        <GitCommit className="mt-0.5 h-4 w-4 flex-shrink-0 text-accent-violet" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-accent-blue">{commit.short_sha}</span>
            <span className="text-xs text-text-muted">{formatDate(commit.date)}</span>
            <span className="text-xs text-text-muted">{commit.author}</span>
          </div>
          <div className="mt-1 text-sm font-medium text-text-primary">{commit.message}</div>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-text-muted">
            <span>{commit.files.length} file(s)</span>
            <span className="text-accent-green">+{commit.insertions}</span>
            <span className="text-accent-red">-{commit.deletions}</span>
          </div>
        </div>
        {isExpanded ? (
          <ChevronUp className="h-5 w-5 flex-shrink-0 text-text-muted" />
        ) : (
          <ChevronDown className="h-5 w-5 flex-shrink-0 text-text-muted" />
        )}
      </button>
      {isExpanded && (
        <div className="border-t border-border">
          <div className="grid gap-2 px-4 py-3 sm:grid-cols-2">
            {commit.files.map((file) => (
              <div key={`${commit.sha}-${file.file_path}`} className="min-w-0 rounded-md bg-bg-tertiary px-3 py-2">
                <div className="truncate font-mono text-xs text-text-primary">{file.file_path}</div>
                <div className="mt-1 flex items-center gap-3 text-xs">
                  <span className="text-text-muted">{file.status}</span>
                  <span className="text-accent-green">+{file.additions}</span>
                  <span className="text-accent-red">-{file.deletions}</span>
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
      additions: files.reduce((sum, file) => sum + file.additions, 0),
      deletions: files.reduce((sum, file) => sum + file.deletions, 0),
    };
  }, [status]);

  const handleCommit = async () => {
    if (!projectPath || !commitMessage.trim()) return;
    setIsCommitting(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await commitReviewedChanges(projectPath, commitMessage.trim(), HISTORY_LIMIT);
      if (result.error) {
        setError(result.error);
      }
      if (result.status) {
        setStatus(result.status);
      }
      if (result.committed) {
        setSuccess(`Committed ${result.commit_sha.slice(0, 7)}: ${result.message}`);
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

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-border px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="flex items-center gap-2 text-lg font-semibold">
              <GitCommit className="h-5 w-5 text-accent-blue" />
              Commit Review
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-text-muted">
              <span>{projectName ?? "Selected project"}</span>
              {status && (
                <>
                  <span className="flex items-center gap-1">
                    <GitBranch className="h-3.5 w-3.5" />
                    {status.branch}
                  </span>
                  <span className="font-mono">{status.head_sha.slice(0, 7) || "no HEAD"}</span>
                </>
              )}
            </div>
          </div>
          <button
            onClick={loadStatus}
            disabled={isLoading}
            className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? <LoadingSpinner size="sm" /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(360px,42%)_1fr]">
        <section className="min-h-0 overflow-y-auto border-r border-border p-5">
          {error && (
            <div className="mb-4 rounded-lg border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm text-accent-red">
              {error}
            </div>
          )}
          {success && (
            <div className="mb-4 rounded-lg border border-accent-green/30 bg-accent-green/10 px-4 py-3 text-sm text-accent-green">
              {success}
            </div>
          )}

          <div className="rounded-lg border border-border bg-bg-secondary p-4">
            <div className="flex items-start gap-3">
              {status?.recommendation.should_commit ? (
                <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-accent-green" />
              ) : (
                <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-accent-amber" />
              )}
              <div className="min-w-0 flex-1">
                <h2 className="font-semibold text-text-primary">
                  {status?.recommendation.title ?? "Review status"}
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {status?.recommendation.reason ?? "Loading git status."}
                </p>
              </div>
            </div>
            {Boolean(status?.recommendation.concerns.length) && (
              <div className="mt-3 space-y-2">
                {status?.recommendation.concerns.map((concern) => (
                  <div key={concern} className="rounded-md bg-bg-tertiary px-3 py-2 text-sm text-text-secondary">
                    {concern}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-4 grid grid-cols-3 gap-3">
            <div className="rounded-lg border border-border bg-bg-secondary p-3">
              <div className="text-2xl font-semibold text-text-primary">{status?.staged_files ?? 0}</div>
              <div className="text-xs text-text-muted">staged</div>
            </div>
            <div className="rounded-lg border border-border bg-bg-secondary p-3">
              <div className="text-2xl font-semibold text-text-primary">{status?.unstaged_files ?? 0}</div>
              <div className="text-xs text-text-muted">unstaged</div>
            </div>
            <div className="rounded-lg border border-border bg-bg-secondary p-3">
              <div className="text-2xl font-semibold text-text-primary">{status?.untracked_files ?? 0}</div>
              <div className="text-xs text-text-muted">untracked</div>
            </div>
          </div>

          <div className="mt-4 rounded-lg border border-border bg-bg-secondary p-4">
            <h2 className="mb-2 font-semibold text-text-primary">Current Summary</h2>
            <p className="text-sm leading-6 text-text-secondary">
              {status?.summary ?? "Loading current changes."}
            </p>
            <div className="mt-3 flex items-center gap-4 text-sm">
              <span className="flex items-center gap-1 text-accent-green">
                <Plus className="h-4 w-4" />
                {totals.additions}
              </span>
              <span className="flex items-center gap-1 text-accent-red">
                <Minus className="h-4 w-4" />
                {totals.deletions}
              </span>
            </div>
          </div>

          <div className="mt-4 rounded-lg border border-border bg-bg-secondary p-4">
            <label className="text-sm font-medium text-text-secondary" htmlFor="commit-message">
              Commit message
            </label>
            <input
              id="commit-message"
              value={commitMessage}
              onChange={(event) => setCommitMessage(event.target.value)}
              placeholder="Name this commit"
              className="mt-2 w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary outline-none placeholder:text-text-muted focus:border-accent-blue"
            />
            <button
              onClick={handleCommit}
              disabled={!canCommit}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-accent-blue px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent-blue/80 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isCommitting ? (
                <>
                  <LoadingSpinner size="sm" />
                  Committing...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  Stage and Commit
                </>
              )}
            </button>
          </div>

          <div className="mt-5">
            <h2 className="mb-3 flex items-center gap-2 font-semibold text-text-primary">
              <FileText className="h-4 w-4 text-accent-cyan" />
              Uncommitted Files
            </h2>
            <div className="space-y-3">
              {isLoading && !status && (
                <div className="flex items-center justify-center py-10">
                  <LoadingSpinner size="lg" />
                </div>
              )}
              {status?.uncommitted_files.map((change) => (
                <CurrentChangeRow
                  key={change.file_path}
                  change={change}
                  isExpanded={expandedFile === change.file_path}
                  onToggle={() => setExpandedFile(expandedFile === change.file_path ? null : change.file_path)}
                />
              ))}
              {status && status.uncommitted_files.length === 0 && (
                <div className="rounded-lg border border-border bg-bg-secondary px-4 py-8 text-center text-sm text-text-muted">
                  Working tree clean
                </div>
              )}
            </div>
          </div>
        </section>

        <section className="min-h-0 overflow-y-auto p-5">
          <h2 className="mb-3 flex items-center gap-2 font-semibold text-text-primary">
            <History className="h-4 w-4 text-accent-violet" />
            Recent Git History
          </h2>
          <div className="space-y-3">
            {status?.recent_commits.map((commit) => (
              <CommitHistoryRow
                key={commit.sha}
                commit={commit}
                isExpanded={expandedCommit === commit.sha}
                onToggle={() => setExpandedCommit(expandedCommit === commit.sha ? null : commit.sha)}
              />
            ))}
            {status && status.recent_commits.length === 0 && (
              <div className="rounded-lg border border-border bg-bg-secondary px-4 py-8 text-center text-sm text-text-muted">
                No commits found
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
