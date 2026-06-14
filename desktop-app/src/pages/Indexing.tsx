import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Play,
  FolderOpen,
  RefreshCw,
  Trash2,
  AlertTriangle,
  X,
  GitCommit,
} from "lucide-react";
import { useProjectContext } from "../App";
import {
  indexProject,
  getIndexStatus,
  checkIndexStatus,
  deleteProjectIndex,
  getIndexEstimate,
  getIndexHistory,
  clearIndexHistory,
  checkGitWorkingTree,
  getIndexDiffStatus,
  cancelIndex,
} from "../lib/api";
import type {
  IndexStatus,
  IndexEstimateResponse,
  IndexHistoryEntry,
  GitCleanlinessResponse,
  IndexDiffResponse,
} from "../lib/types";

// ── constants ────────────────────────────────────────────────────────────────

const SUPPORTED_EXTENSIONS = new Set([".py", ".js", ".ts", ".jsx", ".tsx"]);

const FILE_TYPE_GROUPS = [
  { name: "Python", extensions: [".py"] },
  { name: "JavaScript / TypeScript", extensions: [".js", ".ts", ".jsx", ".tsx"] },
  { name: "Configuration", extensions: [".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"] },
  { name: "Styles", extensions: [".css", ".scss", ".less", ".sass"] },
  { name: "Markdown / Docs", extensions: [".md", ".mdx", ".rst", ".txt"] },
  { name: "Data / Serialization", extensions: [".xml", ".csv", ".sql", ".graphql"] },
  { name: "Images", extensions: [".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp"] },
];

// ── helpers ──────────────────────────────────────────────────────────────────

function sumEstimate(
  estimate: IndexEstimateResponse | null,
  extFilter: Set<string>,
  dirFilter: Set<string>
): { files: number; chunks: number } {
  if (!estimate) return { files: 0, chunks: 0 };
  let files = 0;
  let chunks = 0;
  for (const e of estimate.by_extension) {
    if (!extFilter.has(e.extension)) continue;
    if (dirFilter.size > 0) {
      let matchedAny = false;
      for (const d of estimate.by_directory) {
        if (dirFilter.has(d.path)) {
          const share =
            d.estimated_chunks > 0 && estimate.estimated_total_chunks > 0
              ? e.estimated_chunks *
                (d.estimated_chunks / estimate.estimated_total_chunks)
              : 0;
          if (share > 0) matchedAny = true;
        }
      }
      if (!matchedAny) continue;
    }
    files += e.count;
    chunks += e.estimated_chunks;
  }
  return { files, chunks };
}

function fmtLogTime(d: Date): string {
  return d.toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// ── sub-components ───────────────────────────────────────────────────────────

function TriStateCheckbox({
  checked,
  indeterminate,
  onChange,
  disabled,
}: {
  checked: boolean;
  indeterminate: boolean;
  onChange: () => void;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate && !checked;
  }, [checked, indeterminate]);
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      onChange={onChange}
      disabled={disabled}
      className="w-3.5 h-3.5 accent-primary border-outline-variant"
    />
  );
}

function AsciiBar({ pct, width = 36 }: { pct: number; width?: number }) {
  const filled = Math.round((Math.min(pct, 100) / 100) * width);
  return (
    <span className="font-mono text-primary text-[13px] tracking-[0.12em] select-none">
      [{"█".repeat(filled)}{"░".repeat(width - filled)}]
    </span>
  );
}

// Spinner character cycle
const SPIN = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"];

function Spinner() {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setFrame((f) => (f + 1) % SPIN.length), 120);
    return () => clearInterval(t);
  }, []);
  return (
    <span className="text-primary text-base select-none">{SPIN[frame]}</span>
  );
}

// ── main page ────────────────────────────────────────────────────────────────

export default function Indexing() {
  const { projectPath, projectName, indexStatus, setProject } =
    useProjectContext();
  const [isIndexing, setIsIndexing] = useState(false);
  const [localStatus, setLocalStatus] = useState<IndexStatus | null>(null);
  const [history, setHistory] = useState<IndexHistoryEntry[]>([]);
  const [currentFile, setCurrentFile] = useState<string | null>(null);
  const [startTime, setStartTime] = useState<number | null>(null);
  const [recentFiles, setRecentFiles] = useState<
    { file: string; status: string }[]
  >([]);
  const [showHistory, setShowHistory] = useState(false);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const fileListRef = useRef<{ file: string; status: string }[]>([]);
  const logRef = useRef<HTMLDivElement>(null);

  const [checkLoading, setCheckLoading] = useState(true);
  const [isAlreadyIndexed, setIsAlreadyIndexed] = useState(false);
  const [chunksCount, setChunksCount] = useState(0);

  const [estimate, setEstimate] = useState<IndexEstimateResponse | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [selectedExtensions, setSelectedExtensions] = useState<Set<string>>(
    new Set()
  );
  const [selectedDirs, setSelectedDirs] = useState<Set<string>>(new Set());
  const [activeGroupTab, setActiveGroupTab] = useState<
    "filetype" | "extension" | "directory"
  >("filetype");
  const [deleting, setDeleting] = useState(false);

  const navigate = useNavigate();
  const [gitStatus, setGitStatus] = useState<GitCleanlinessResponse | null>(
    null
  );
  const [gitStatusLoading, setGitStatusLoading] = useState(true);
  const [dismissDirtyWarning, setDismissDirtyWarning] = useState(false);
  const [diffPreview, setDiffPreview] = useState<IndexDiffResponse | null>(
    null
  );
  const [diffPreviewLoading, setDiffPreviewLoading] = useState(false);

  // Auto-scroll log when new entries arrive
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [recentFiles]);

  const loadHistory = useCallback(async (pid: string) => {
    try {
      const entries = await getIndexHistory(pid);
      setHistory(entries.reverse());
    } catch {
      console.warn("Failed to load index history");
    }
  }, []);

  const loadEstimate = useCallback(
    async (pid: string, ppath: string) => {
      setEstimateLoading(true);
      try {
        const est = await getIndexEstimate(pid, ppath);
        setEstimate(est);
        setSelectedExtensions(
          new Set(
            est.by_extension
              .filter((e) => SUPPORTED_EXTENSIONS.has(e.extension))
              .map((e) => e.extension)
          )
        );
        setSelectedDirs(new Set(est.by_directory.map((d) => d.path)));
      } catch {
        console.warn("Failed to load index estimate");
        setEstimate(null);
      } finally {
        setEstimateLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!projectName || !projectPath) return;
    setCheckLoading(true);
    setEstimate(null);
    setDiffPreview(null);
    setGitStatus(null);
    setDismissDirtyWarning(false);

    Promise.all([
      checkIndexStatus(projectName),
      loadHistory(projectName),
      loadEstimate(projectName, projectPath),
      checkGitWorkingTree(projectPath),
    ])
      .then(([status, _, __, git]) => {
        setIsAlreadyIndexed(status.is_indexed);
        setChunksCount(status.chunks_count);
        setGitStatus(git);

        if (status.is_indexed && git.clean) {
          setDiffPreviewLoading(true);
          getIndexDiffStatus(projectName, projectPath)
            .then(setDiffPreview)
            .catch(() => setDiffPreview(null))
            .finally(() => setDiffPreviewLoading(false));
        }
      })
      .catch(() => {
        setIsAlreadyIndexed(false);
        setChunksCount(0);
        setGitStatus(null);
        setDiffPreview(null);
      })
      .finally(() => {
        setCheckLoading(false);
        setGitStatusLoading(false);
      });
  }, [projectName, projectPath, loadHistory, loadEstimate]);

  useEffect(() => {
    if (indexStatus && indexStatus.job_id && !localStatus?.job_id) {
      setLocalStatus(indexStatus);
    }
  }, [indexStatus, localStatus?.job_id]);

  useEffect(() => {
    if (isIndexing && localStatus?.job_id) {
      pollIntervalRef.current = setInterval(async () => {
        try {
          const status = await getIndexStatus(localStatus.job_id);
          setLocalStatus(status);
          if (status.current_file) {
            setCurrentFile(status.current_file);
            const last = fileListRef.current[fileListRef.current.length - 1];
            if (!last || last.file !== status.current_file) {
              const entry = { file: status.current_file, status: "Success" };
              fileListRef.current = [
                ...fileListRef.current.slice(-19),
                entry,
              ];
              setRecentFiles([...fileListRef.current]);
            }
          }

          if (status.status === "completed") {
            if (pollIntervalRef.current)
              clearInterval(pollIntervalRef.current);
            setIsIndexing(false);
            setCurrentFile(null);
            setStartTime(null);
            setIsAlreadyIndexed(true);
            setChunksCount(status.chunks_created);
            if (projectName) loadHistory(projectName);
          } else if (status.status === "failed") {
            if (pollIntervalRef.current)
              clearInterval(pollIntervalRef.current);
          }
        } catch (error) {
          console.error("Failed to poll index status:", error);
        }
      }, 2000);

      return () => {
        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      };
    }
  }, [isIndexing, localStatus?.job_id, projectName, loadHistory]);

  const handleDeleteIndex = async () => {
    if (!projectName || deleting) return;
    setDeleting(true);
    try {
      await deleteProjectIndex(projectName);
      setIsAlreadyIndexed(false);
      setChunksCount(0);
    } catch (error) {
      console.error("Failed to delete index:", error);
    } finally {
      setDeleting(false);
    }
  };

  const handleStartIndexing = async () => {
    if (!projectPath || !projectName) return;

    try {
      const git = await checkGitWorkingTree(projectPath);
      if (git.has_changes) {
        setGitStatus(git);
        setDismissDirtyWarning(false);
        return;
      }
    } catch {
      /* backend will validate too */
    }

    setIsIndexing(true);
    setIsAlreadyIndexed(false);
    setLocalStatus(null);
    setCurrentFile(null);
    setRecentFiles([]);
    fileListRef.current = [];
    setStartTime(Date.now());

    try {
      const includeExtensions = Array.from(selectedExtensions).filter((e) =>
        SUPPORTED_EXTENSIONS.has(e)
      );
      const includeDirs = Array.from(selectedDirs);
      const result = await indexProject(
        projectName,
        projectPath,
        false,
        includeExtensions.length > 0 ? includeExtensions : undefined,
        includeDirs.length > 0 ? includeDirs : undefined
      );
      if (result.job_id) {
        setLocalStatus({
          job_id: result.job_id,
          status: "queued",
          files_processed: 0,
          files_total: 0,
          chunks_created: 0,
          graph_nodes: 0,
          graph_edges: 0,
          graph_status: "pending",
          errors: [],
        } as IndexStatus);
        setProject(projectPath, projectName, true);
      } else {
        setIsIndexing(false);
        setStartTime(null);
        setLocalStatus({
          status: "failed",
          error_message: "Server did not return a job ID.",
          files_total: 0,
          files_processed: 0,
          chunks_created: 0,
          graph_nodes: 0,
          graph_edges: 0,
          graph_status: "pending",
          job_id: "",
          errors: [],
        } as IndexStatus);
      }
    } catch (error) {
      const msg = (error as Error).message;
      if (msg.toLowerCase().includes("uncommitted")) {
        setIsIndexing(false);
        setStartTime(null);
        try {
          const git = await checkGitWorkingTree(projectPath);
          setGitStatus(git);
        } catch {
          /* ignore */
        }
        setDismissDirtyWarning(false);
        return;
      }
      console.error("Failed to start indexing:", error);
      setIsIndexing(false);
      setStartTime(null);
      setLocalStatus({
        status: "failed",
        error_message: "Failed to communicate with indexing service.",
        files_total: 0,
        files_processed: 0,
        chunks_created: 0,
        graph_nodes: 0,
        graph_edges: 0,
        graph_status: "pending",
        job_id: "",
        errors: [],
      } as IndexStatus);
    }
  };

  const toggleExtension = (ext: string) => {
    setSelectedExtensions((prev) => {
      const next = new Set(prev);
      if (next.has(ext)) next.delete(ext);
      else next.add(ext);
      return next;
    });
  };

  const toggleDirectory = (path: string) => {
    setSelectedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const toggleGroup = (groupName: string) => {
    const group = FILE_TYPE_GROUPS.find((g) => g.name === groupName);
    if (!group) return;
    const exts = group.extensions.filter((e) =>
      estimate?.by_extension.some((be) => be.extension === e)
    );
    if (exts.length === 0) return;
    const allSelected = exts.every((e) => selectedExtensions.has(e));
    setSelectedExtensions((prev) => {
      const next = new Set(prev);
      for (const e of exts) {
        if (allSelected) next.delete(e);
        else next.add(e);
      }
      return next;
    });
  };

  const isGroupFullySelected = (groupName: string) => {
    const group = FILE_TYPE_GROUPS.find((g) => g.name === groupName);
    if (!group) return false;
    const exts = group.extensions.filter((e) =>
      estimate?.by_extension.some((be) => be.extension === e)
    );
    if (exts.length === 0) return false;
    return exts.every((e) => selectedExtensions.has(e));
  };

  const isGroupPartiallySelected = (groupName: string) => {
    const group = FILE_TYPE_GROUPS.find((g) => g.name === groupName);
    if (!group) return false;
    const exts = group.extensions.filter((e) =>
      estimate?.by_extension.some((be) => be.extension === e)
    );
    if (exts.length === 0) return false;
    const selected = exts.filter((e) => selectedExtensions.has(e)).length;
    return selected > 0 && selected < exts.length;
  };

  const groupFileCount = (groupName: string) => {
    const group = FILE_TYPE_GROUPS.find((g) => g.name === groupName);
    if (!group || !estimate) return 0;
    return estimate.by_extension
      .filter((e) => group.extensions.includes(e.extension))
      .reduce((s, e) => s + e.count, 0);
  };

  const groupChunkCount = (groupName: string) => {
    const group = FILE_TYPE_GROUPS.find((g) => g.name === groupName);
    if (!group || !estimate) return 0;
    return estimate.by_extension
      .filter((e) => group.extensions.includes(e.extension))
      .reduce((s, e) => s + e.estimated_chunks, 0);
  };

  const otherExts = estimate
    ? estimate.by_extension.filter(
        (e) => !FILE_TYPE_GROUPS.some((g) => g.extensions.includes(e.extension))
      )
    : [];
  const otherFiles = otherExts.reduce((s, e) => s + e.count, 0);

  const selectedCounts = useMemo(
    () => sumEstimate(estimate, selectedExtensions, selectedDirs),
    [estimate, selectedExtensions, selectedDirs]
  );

  const allDirsSelected = !!(
    estimate && selectedDirs.size === estimate.by_directory.length
  );

  const overallProgress = useMemo(() => {
    if (!localStatus) return 0;
    const phase1 =
      localStatus.files_total > 0
        ? (localStatus.files_processed / localStatus.files_total) * 50
        : 0;
    const phase2 =
      localStatus.graph_status === "completed"
        ? 50
        : localStatus.graph_status === "running"
        ? 25
        : 0;
    return Math.min(Math.round(phase1 + phase2), 100);
  }, [localStatus]);

  const estimatedTimeRemaining = useMemo(() => {
    if (!localStatus || !startTime || localStatus.files_processed === 0)
      return "--:--";
    const elapsed = (Date.now() - startTime) / 1000;
    const rate = localStatus.files_processed / elapsed;
    const remaining = localStatus.files_total - localStatus.files_processed;
    if (rate <= 0) return "--:--";
    const seconds = Math.ceil(remaining / rate);
    if (seconds > 60) return `~${Math.ceil(seconds / 60)}m`;
    return `~${seconds}s`;
  }, [localStatus, startTime]);

  const fileProcessingRate = useMemo(() => {
    if (!localStatus || !startTime) return 0;
    const elapsed = (Date.now() - startTime) / 1000;
    if (elapsed < 1) return 0;
    return Number((localStatus.files_processed / elapsed).toFixed(1));
  }, [localStatus, startTime]);

  // Derive log entries with approximate timestamps
  const logEntries = useMemo(() => {
    const elapsed = startTime ? Date.now() - startTime : 0;
    return recentFiles.map((f, i) => {
      const fraction =
        recentFiles.length > 1 ? i / (recentFiles.length - 1) : 1;
      const ts = startTime
        ? new Date(startTime + elapsed * fraction)
        : new Date();
      return { ...f, timestamp: ts };
    });
  }, [recentFiles, startTime]);

  // ── No project ────────────────────────────────────────────────────────────

  if (!projectPath) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center h-full font-mono text-on-surface-variant">
        <FolderOpen className="w-10 h-10 mb-4 opacity-20" />
        <p className="text-[11px] uppercase tracking-[0.1em]">
          -- NO_PROJECT_SELECTED --
        </p>
        <p className="text-[10px] mt-2 text-outline">
          select a project to start indexing
        </p>
      </div>
    );
  }

  // ── In-progress view ─────────────────────────────────────────────────────

  if (
    isIndexing ||
    localStatus?.status === "running" ||
    localStatus?.status === "queued"
  ) {
    const jobSuffix = localStatus?.job_id?.slice(0, 6).toUpperCase() || "------";
    const errCount = localStatus?.errors?.length ?? 0;
    const cpuActive = overallProgress > 0 ? Math.max(1, Math.ceil((overallProgress / 100) * 5)) : 1;

    return (
      <div className="h-full overflow-y-auto p-4 pb-14 font-mono">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1 text-[11px] text-on-surface-variant mb-5">
          <span>ROOT</span>
          <span className="text-outline-variant mx-1">/</span>
          <span>INDEXER</span>
          <span className="text-outline-variant mx-1">/</span>
          <span className="text-primary">PROCESSING_TASK_{jobSuffix}</span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          {/* ── Left col ── */}
          <div className="lg:col-span-8 space-y-4">
            {/* Progress panel */}
            <div className="tui-border bg-surface-container-low p-4">
              <span className="tui-border-title text-primary">
                FILE_INDEXING_IN_PROGRESS
                {localStatus?.incremental && (
                  <span className="ml-2 text-tertiary">:: INCREMENTAL</span>
                )}
              </span>

              {/* Progress bar */}
              <div className="mb-4">
                <div className="flex justify-between text-[11px] mb-2">
                  <span className="text-primary font-extrabold tracking-[0.1em]">
                    OVERALL_PROGRESS
                  </span>
                  <span className="text-secondary font-bold">
                    {overallProgress}%
                    {fileProcessingRate > 0 && (
                      <span className="text-on-surface-variant font-normal ml-3">
                        {fileProcessingRate} f/s · {estimatedTimeRemaining} remaining
                      </span>
                    )}
                  </span>
                </div>
                <AsciiBar pct={overallProgress} width={36} />
              </div>

              {/* Currently processing */}
              <div className="space-y-1.5">
                <div className="text-[10px] font-extrabold tracking-[0.1em] text-on-surface-variant uppercase">
                  CURRENTLY_PROCESSING:
                </div>
                <div className="bg-surface-container-lowest border border-outline-variant px-3 py-2 flex items-center gap-2 overflow-hidden">
                  <span className="text-secondary font-bold shrink-0">&gt;</span>
                  <span className="text-[12px] text-on-surface truncate flex-1 font-mono">
                    {currentFile || "preparing..."}
                  </span>
                  <span className="w-1.5 h-3 bg-secondary cursor-blink shrink-0" />
                </div>
              </div>
            </div>

            {/* Log panel */}
            <div className="tui-border bg-surface-container-low overflow-hidden">
              <span className="tui-border-title text-primary">SYSTEM_LOG_OUTPUT</span>
              <div
                ref={logRef}
                className="h-56 overflow-y-auto p-3 space-y-1"
              >
                {logEntries.length === 0 ? (
                  <div className="text-[11px] text-outline uppercase tracking-[0.08em]">
                    -- INITIALIZING --
                  </div>
                ) : (
                  logEntries.map((entry, i) => {
                    const parts = entry.file.split("/");
                    const shortPath =
                      parts.length > 2
                        ? ".../" + parts.slice(-2).join("/")
                        : entry.file;
                    const ok = entry.status === "Success";
                    return (
                      <div
                        key={i}
                        className="flex gap-3 text-[11px] text-on-surface-variant"
                      >
                        <span className="opacity-40 shrink-0 tabular-nums">
                          {fmtLogTime(entry.timestamp)}
                        </span>
                        <span
                          className={`shrink-0 font-bold ${
                            ok ? "text-secondary" : "text-terminal-error"
                          }`}
                        >
                          [{ok ? "SUCCESS" : "FAILED_"}]
                        </span>
                        <span className="truncate">Indexed {shortPath}</span>
                      </div>
                    );
                  })
                )}
                {(localStatus?.errors ?? []).map((err, i) => (
                  <div key={`err-${i}`} className="flex gap-3 text-[11px]">
                    <span className="opacity-40 shrink-0">--:--:--</span>
                    <span className="text-terminal-error shrink-0 font-bold">
                      [FAILED_]
                    </span>
                    <span className="text-terminal-error truncate">{err}</span>
                  </div>
                ))}
              </div>
              <div className="border-t border-outline-variant px-3 py-2 flex justify-between text-[10px] bg-surface-container">
                <span className="text-on-surface-variant">
                  LOGS_AUTO_SCROLLING: ON
                </span>
                <span className="text-primary">END_OF_STREAM</span>
              </div>
            </div>
          </div>

          {/* ── Right col ── */}
          <div className="lg:col-span-4 space-y-4">
            {/* Session metrics */}
            <div className="tui-border bg-surface-container-low p-4">
              <span className="tui-border-title text-primary">SESSION_METRICS</span>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-[10px] text-on-surface-variant uppercase tracking-[0.08em]">
                    FILES_TOTAL
                  </div>
                  <div className="text-[20px] font-bold text-primary leading-tight mt-0.5">
                    {localStatus?.files_total
                      ? localStatus.files_total.toLocaleString()
                      : "—"}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-on-surface-variant uppercase tracking-[0.08em]">
                    PROCESSED
                  </div>
                  <div className="text-[20px] font-bold text-secondary leading-tight mt-0.5">
                    {(localStatus?.files_processed ?? 0).toLocaleString()}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-on-surface-variant uppercase tracking-[0.08em]">
                    ERRORS
                  </div>
                  <div
                    className={`text-[20px] font-bold leading-tight mt-0.5 ${
                      errCount > 0
                        ? "text-terminal-error"
                        : "text-on-surface-variant"
                    }`}
                  >
                    {String(errCount).padStart(2, "0")}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-on-surface-variant uppercase tracking-[0.08em]">
                    EST_TIME
                  </div>
                  <div className="text-[20px] font-bold text-tertiary leading-tight mt-0.5">
                    {estimatedTimeRemaining}
                  </div>
                </div>
              </div>

              {/* CPU allocation */}
              <div className="mt-4 pt-4 border-t border-outline-variant">
                <div className="text-[10px] text-on-surface-variant uppercase tracking-[0.08em] mb-2">
                  CPU_ALLOCATION
                </div>
                <div className="flex gap-1">
                  {Array.from({ length: 5 }, (_, i) => (
                    <div
                      key={i}
                      className={`h-2 flex-1 bg-secondary ${
                        i >= cpuActive ? "opacity-20" : ""
                      }`}
                    />
                  ))}
                </div>
              </div>
            </div>

            {/* Action buttons */}
            <div className="space-y-2">
              <button
                onClick={() => {
                  if (pollIntervalRef.current)
                    clearInterval(pollIntervalRef.current);
                  setIsIndexing(false);
                }}
                className="w-full bg-surface-container border border-primary text-primary px-4 py-3 hover:bg-primary hover:text-on-primary transition-colors flex justify-between items-center text-[11px] font-extrabold tracking-[0.1em] uppercase"
              >
                <span>PAUSE_PROCESS</span>
                <span className="opacity-40 font-normal">[ SPACE ]</span>
              </button>
              <button
                onClick={async () => {
                  if (pollIntervalRef.current)
                    clearInterval(pollIntervalRef.current);
                  if (localStatus?.job_id)
                    cancelIndex(localStatus.job_id).catch(() => {});
                  setIsIndexing(false);
                  setLocalStatus(null);
                }}
                className="w-full bg-surface-container border border-terminal-error text-terminal-error px-4 py-3 hover:bg-terminal-error hover:text-surface transition-colors flex justify-between items-center text-[11px] font-extrabold tracking-[0.1em] uppercase"
              >
                <span>CANCEL_PROCESS</span>
                <span className="opacity-40 font-normal group-hover:opacity-100">
                  [ ESC ]
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Setup view ───────────────────────────────────────────────────────────

  const supportedFileCount = estimate
    ? estimate.by_extension
        .filter((e) => SUPPORTED_EXTENSIONS.has(e.extension))
        .reduce((s, e) => s + e.count, 0)
    : 0;

  return (
    <div className="h-full overflow-y-auto p-4 pb-14 font-mono">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1 text-[11px] text-on-surface-variant mb-5">
        <span>ROOT</span>
        <span className="text-outline-variant mx-1">/</span>
        <span>INDEXER</span>
        <span className="text-outline-variant mx-1">/</span>
        <span className="text-primary">
          CONFIG_{(projectName ?? "UNKNOWN").toUpperCase()}
        </span>
      </div>

      {/* Git dirty warning */}
      {gitStatus?.has_changes && !dismissDirtyWarning && (
        <div className="tui-border border-tertiary bg-surface-container-low p-4 mb-4">
          <span className="tui-border-title text-tertiary flex items-center gap-1.5">
            <AlertTriangle className="w-3 h-3" />
            WARNING_DIRTY_TREE
          </span>
          <div className="flex items-start gap-3 pt-1">
            <div className="flex-1 min-w-0 space-y-1">
              <p className="text-[11px] text-on-surface">{gitStatus.summary}</p>
              <p className="text-[10px] text-on-surface-variant">
                commit or stash changes before indexing
              </p>
              <button
                onClick={() => navigate("/review")}
                className="mt-2 border border-tertiary text-tertiary text-[10px] px-3 py-1.5 uppercase hover:bg-tertiary hover:text-on-tertiary-container transition-colors flex items-center gap-1.5"
              >
                <GitCommit className="w-3 h-3" />
                [ GO_TO_COMMIT_REVIEW ]
              </button>
            </div>
            <button
              onClick={() => setDismissDirtyWarning(true)}
              className="p-1 text-outline hover:text-terminal-error transition-colors shrink-0"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      <div
        className={
          gitStatus?.has_changes && !dismissDirtyWarning
            ? "pointer-events-none opacity-40 select-none"
            : ""
        }
      >
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          {/* ── Left col ── */}
          <div className="lg:col-span-8 space-y-4">
            {/* Main config / status panel */}
            <div className="tui-border bg-surface-container-low p-4 min-h-[180px]">
              <span className="tui-border-title text-primary">
                TASK_CONFIGURATION
              </span>

              {checkLoading || gitStatusLoading ? (
                <div className="flex items-center gap-3 py-10 justify-center text-[12px] text-on-surface-variant">
                  <Spinner />
                  <span>LOADING_SYSTEM_STATE...</span>
                </div>
              ) : isAlreadyIndexed ? (
                diffPreviewLoading ? (
                  <div className="flex items-center gap-3 py-10 justify-center text-[12px] text-on-surface-variant">
                    <Spinner />
                    <span>CHECKING_DIFF...</span>
                  </div>
                ) : diffPreview?.incremental_possible ? (
                  /* Incremental available */
                  <div className="space-y-4 pt-2">
                    <div className="flex items-center gap-3">
                      <span className="text-tertiary font-bold text-[12px]">
                        [UPDATE_AVAILABLE]
                      </span>
                      <span className="text-on-surface-variant text-[11px]">
                        INCREMENTAL_INDEX_READY
                      </span>
                    </div>
                    <p className="text-[11px] text-on-surface-variant">
                      {diffPreview.message}
                    </p>
                    <div className="flex items-center gap-4 text-[11px] font-mono">
                      {diffPreview.added.length > 0 && (
                        <span className="text-secondary">
                          +{diffPreview.added.length} added
                        </span>
                      )}
                      {diffPreview.modified.length > 0 && (
                        <span className="text-tertiary">
                          ~{diffPreview.modified.length} modified
                        </span>
                      )}
                      {diffPreview.deleted.length > 0 && (
                        <span className="text-terminal-error">
                          -{diffPreview.deleted.length} deleted
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={handleStartIndexing}
                        className="border border-primary text-primary text-[11px] px-4 py-2 uppercase hover:bg-primary hover:text-on-primary transition-colors flex items-center gap-1.5 font-extrabold tracking-[0.08em]"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        [ UPDATE_INDEX ]
                      </button>
                      <button
                        onClick={handleDeleteIndex}
                        disabled={deleting}
                        className="border border-terminal-error text-terminal-error text-[11px] px-4 py-2 uppercase hover:bg-terminal-error hover:text-surface transition-colors disabled:opacity-40 flex items-center gap-1.5 font-extrabold tracking-[0.08em]"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        {deleting ? "[ DELETING... ]" : "[ DELETE_INDEX ]"}
                      </button>
                    </div>
                  </div>
                ) : (
                  /* Already indexed, up to date */
                  <div className="space-y-4 pt-2">
                    <div className="flex items-center gap-3">
                      <span className="text-secondary font-bold text-[12px]">
                        [OK]
                      </span>
                      <span className="text-on-surface-variant text-[11px]">
                        PROJECT_INDEXED · UP_TO_DATE
                      </span>
                    </div>
                    <p className="text-[11px] text-on-surface-variant">
                      {diffPreview?.message || (
                        <>
                          vector index:{" "}
                          <strong className="text-primary">
                            {chunksCount.toLocaleString()}
                          </strong>{" "}
                          chunks stored
                        </>
                      )}
                    </p>
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={handleStartIndexing}
                        className="border border-primary text-primary text-[11px] px-4 py-2 uppercase hover:bg-primary hover:text-on-primary transition-colors flex items-center gap-1.5 font-extrabold tracking-[0.08em]"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        [ FORCE_REINDEX ]
                      </button>
                      <button
                        onClick={handleDeleteIndex}
                        disabled={deleting}
                        className="border border-terminal-error text-terminal-error text-[11px] px-4 py-2 uppercase hover:bg-terminal-error hover:text-surface transition-colors disabled:opacity-40 flex items-center gap-1.5 font-extrabold tracking-[0.08em]"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        {deleting ? "[ DELETING... ]" : "[ DELETE_INDEX ]"}
                      </button>
                    </div>
                  </div>
                )
              ) : localStatus?.status === "failed" ? (
                /* Failed */
                <div className="space-y-4 pt-2">
                  <span className="text-terminal-error font-bold text-[12px]">
                    [ERR] INDEXING_FAILED
                  </span>
                  <p className="text-[11px] text-on-surface-variant max-w-sm">
                    {localStatus.error_message ||
                      "The indexing job encountered an error."}
                  </p>
                  <button
                    onClick={handleStartIndexing}
                    className="border border-primary text-primary text-[11px] px-4 py-2 uppercase hover:bg-primary hover:text-on-primary transition-colors flex items-center gap-1.5 font-extrabold tracking-[0.08em]"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    [ RETRY ]
                  </button>
                </div>
              ) : estimateLoading || !estimate ? (
                <div className="flex items-center gap-3 py-10 justify-center text-[12px] text-on-surface-variant">
                  <Spinner />
                  <span>SCANNING_FILES...</span>
                </div>
              ) : (
                /* File selection */
                <div className="space-y-3 pt-2">
                  {/* Estimate summary */}
                  <div className="text-[11px] text-on-surface-variant">
                    <span className="text-primary font-bold">
                      {estimate.estimated_total_chunks.toLocaleString()}
                    </span>{" "}
                    chunks from{" "}
                    <span className="text-primary font-bold">
                      {estimate.total_files.toLocaleString()}
                    </span>{" "}
                    files found
                    {estimate.total_files !== supportedFileCount && (
                      <span className="text-outline ml-2">
                        ({estimate.total_files - supportedFileCount} unsupported
                        types skipped)
                      </span>
                    )}
                  </div>

                  {/* Tab bar */}
                  <div className="flex gap-1 border-b border-outline-variant pb-2">
                    {(
                      ["filetype", "extension", "directory"] as const
                    ).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setActiveGroupTab(tab)}
                        className={`px-3 py-1 text-[10px] font-extrabold tracking-[0.1em] uppercase border transition-colors ${
                          activeGroupTab === tab
                            ? "border-primary bg-primary text-on-primary"
                            : "border-outline-variant text-on-surface-variant hover:border-outline hover:text-on-surface"
                        }`}
                      >
                        {tab === "filetype"
                          ? "BY_TYPE"
                          : tab === "extension"
                          ? "BY_EXT"
                          : "BY_DIR"}
                      </button>
                    ))}
                  </div>

                  {/* Tab content */}
                  <div className="max-h-52 overflow-y-auto space-y-0.5">
                    {activeGroupTab === "filetype" && (
                      <>
                        {FILE_TYPE_GROUPS.map((group) => {
                          const count = groupFileCount(group.name);
                          if (count === 0) return null;
                          const chk = groupChunkCount(group.name);
                          const checked = isGroupFullySelected(group.name);
                          const partial = isGroupPartiallySelected(
                            group.name
                          );
                          return (
                            <label
                              key={group.name}
                              className="flex items-center justify-between py-1.5 px-2 hover:bg-surface-container-high cursor-pointer"
                            >
                              <div className="flex items-center gap-2.5">
                                <TriStateCheckbox
                                  checked={checked}
                                  indeterminate={partial}
                                  onChange={() => toggleGroup(group.name)}
                                />
                                <span className="text-[12px] text-on-surface">
                                  {group.name}
                                </span>
                              </div>
                              <span className="text-[10px] text-on-surface-variant font-mono">
                                {count}f{chk > 0 ? ` ~${chk}c` : ""}
                              </span>
                            </label>
                          );
                        })}
                        {otherFiles > 0 && (
                          <label className="flex items-center justify-between py-1.5 px-2 opacity-40 cursor-not-allowed">
                            <div className="flex items-center gap-2.5">
                              <input
                                type="checkbox"
                                disabled
                                className="w-3.5 h-3.5"
                              />
                              <span className="text-[12px] text-on-surface-variant">
                                Other (unsupported)
                              </span>
                            </div>
                            <span className="text-[10px] text-on-surface-variant font-mono">
                              {otherFiles}f
                            </span>
                          </label>
                        )}
                      </>
                    )}

                    {activeGroupTab === "extension" &&
                      estimate.by_extension.map((ext) => {
                        const supported = SUPPORTED_EXTENSIONS.has(
                          ext.extension
                        );
                        return (
                          <label
                            key={ext.extension}
                            className={`flex items-center justify-between py-1.5 px-2 hover:bg-surface-container-high cursor-pointer ${
                              !supported ? "opacity-40" : ""
                            }`}
                          >
                            <div className="flex items-center gap-2.5">
                              <input
                                type="checkbox"
                                checked={selectedExtensions.has(ext.extension)}
                                onChange={() =>
                                  supported && toggleExtension(ext.extension)
                                }
                                disabled={!supported}
                                className="w-3.5 h-3.5 accent-primary"
                              />
                              <span className="text-[12px] font-mono text-on-surface">
                                {ext.extension}
                              </span>
                              {!supported && (
                                <span className="text-[10px] text-outline italic">
                                  (unsupported)
                                </span>
                              )}
                            </div>
                            <span className="text-[10px] text-on-surface-variant font-mono">
                              {ext.count}f ~{ext.estimated_chunks}c
                            </span>
                          </label>
                        );
                      })}

                    {activeGroupTab === "directory" && (
                      <>
                        <label className="flex items-center justify-between py-1.5 px-2 hover:bg-surface-container-high cursor-pointer border-b border-outline-variant mb-1">
                          <div className="flex items-center gap-2.5">
                            <input
                              type="checkbox"
                              checked={allDirsSelected}
                              onChange={() => {
                                if (allDirsSelected) setSelectedDirs(new Set());
                                else
                                  setSelectedDirs(
                                    new Set(
                                      estimate.by_directory.map((d) => d.path)
                                    )
                                  );
                              }}
                              className="w-3.5 h-3.5 accent-primary"
                            />
                            <span className="text-[12px] text-on-surface font-bold">
                              All Directories
                            </span>
                          </div>
                          <span className="text-[10px] text-on-surface-variant font-mono">
                            {estimate.total_files}f
                          </span>
                        </label>
                        {estimate.by_directory.map((dir) => (
                          <label
                            key={dir.path}
                            className="flex items-center justify-between py-1.5 px-2 hover:bg-surface-container-high cursor-pointer"
                          >
                            <div className="flex items-center gap-2.5">
                              <input
                                type="checkbox"
                                checked={selectedDirs.has(dir.path)}
                                onChange={() => toggleDirectory(dir.path)}
                                className="w-3.5 h-3.5 accent-primary"
                              />
                              <span className="text-[12px] text-on-surface truncate max-w-[180px] font-mono">
                                {dir.path}/
                              </span>
                            </div>
                            <span className="text-[10px] text-on-surface-variant font-mono">
                              {dir.count}f ~{dir.estimated_chunks}c
                            </span>
                          </label>
                        ))}
                      </>
                    )}
                  </div>

                  {/* Selection summary */}
                  <div className="border-t border-outline-variant pt-2 flex items-center justify-between text-[10px] font-mono">
                    <span
                      className={
                        selectedExtensions.size === 0 ||
                        selectedDirs.size === 0
                          ? "text-outline"
                          : "text-on-surface"
                      }
                    >
                      {selectedExtensions.size === 0 ||
                      selectedDirs.size === 0
                        ? "-- no files selected --"
                        : `${selectedCounts.files.toLocaleString()} files · ~${selectedCounts.chunks.toLocaleString()} chunks`}
                    </span>
                    <span className="text-outline">
                      {
                        estimate.by_extension.filter((e) =>
                          SUPPORTED_EXTENSIONS.has(e.extension)
                        ).length
                      }{" "}
                      indexable types
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* History accordion */}
            <div className="tui-border bg-surface-container-low overflow-hidden">
              <span className="tui-border-title text-on-surface-variant">
                INDEX_HISTORY
              </span>
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="w-full px-4 py-2.5 flex justify-between items-center hover:bg-surface-container-high transition-colors"
              >
                <span className="text-[11px] text-on-surface-variant uppercase tracking-[0.08em]">
                  &gt; {history.length} RECORD{history.length !== 1 ? "S" : ""}
                </span>
                <div className="flex items-center gap-3">
                  {history.length > 0 && (
                    <span
                      onClick={async (e) => {
                        e.stopPropagation();
                        if (!projectName) return;
                        try {
                          await clearIndexHistory(projectName);
                          setHistory([]);
                        } catch {
                          /* ignore */
                        }
                      }}
                      className="text-[10px] text-outline hover:text-terminal-error transition-colors cursor-pointer"
                    >
                      [CLEAR]
                    </span>
                  )}
                  <span className="text-primary text-[11px] font-mono">
                    {showHistory ? "[-]" : "[+]"}
                  </span>
                </div>
              </button>

              {showHistory && (
                <div className="border-t border-outline-variant">
                  {history.length > 0 ? (
                    <div className="divide-y divide-outline-variant/30 max-h-52 overflow-y-auto">
                      {history.map((entry) => (
                        <div
                          key={entry.id}
                          className="flex items-center justify-between px-4 py-2.5 text-[11px] font-mono"
                        >
                          <div className="flex items-center gap-3">
                            {entry.status === "completed" ? (
                              <span className="text-secondary font-bold text-[10px]">
                                [OK]
                              </span>
                            ) : (
                              <span className="text-terminal-error font-bold text-[10px]">
                                [ERR]
                              </span>
                            )}
                            <div>
                              <div className="text-on-surface">
                                {new Date(entry.date).toLocaleString()}
                              </div>
                              <div className="text-[10px] text-on-surface-variant">
                                {entry.files}f · {entry.chunks}c ·{" "}
                                {entry.duration}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-3 text-[10px] text-on-surface-variant">
                            <span>{entry.nodes} nodes</span>
                            <span
                              className={
                                entry.status === "completed"
                                  ? "text-secondary"
                                  : "text-terminal-error"
                              }
                            >
                              [{entry.status.toUpperCase()}]
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[11px] text-outline text-center py-5 uppercase tracking-[0.08em]">
                      -- NO HISTORY --
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* ── Right col ── */}
          <div className="lg:col-span-4 space-y-4">
            {/* Estimate metrics */}
            <div className="tui-border bg-surface-container-low p-4">
              <span className="tui-border-title text-primary">
                ESTIMATE_METRICS
              </span>
              {estimate ? (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-[10px] text-on-surface-variant uppercase tracking-[0.08em]">
                      TOTAL_FILES
                    </div>
                    <div className="text-[20px] font-bold text-primary leading-tight mt-0.5">
                      {estimate.total_files.toLocaleString()}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-on-surface-variant uppercase tracking-[0.08em]">
                      EST_CHUNKS
                    </div>
                    <div className="text-[20px] font-bold text-secondary leading-tight mt-0.5">
                      ~{estimate.estimated_total_chunks.toLocaleString()}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-on-surface-variant uppercase tracking-[0.08em]">
                      SUPPORTED
                    </div>
                    <div className="text-[20px] font-bold text-tertiary leading-tight mt-0.5">
                      {
                        estimate.by_extension.filter((e) =>
                          SUPPORTED_EXTENSIONS.has(e.extension)
                        ).length
                      }{" "}
                      <span className="text-[11px] font-normal text-on-surface-variant">
                        types
                      </span>
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-on-surface-variant uppercase tracking-[0.08em]">
                      DIRS
                    </div>
                    <div className="text-[20px] font-bold text-on-surface leading-tight mt-0.5">
                      {estimate.by_directory.length}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="py-6 text-center text-[11px] text-outline uppercase tracking-[0.08em]">
                  — SCANNING —
                </div>
              )}
              {isAlreadyIndexed && (
                <div className="mt-4 pt-4 border-t border-outline-variant">
                  <div className="text-[10px] text-on-surface-variant uppercase tracking-[0.08em] mb-1">
                    INDEXED_CHUNKS
                  </div>
                  <div className="text-[16px] font-bold text-secondary">
                    {chunksCount.toLocaleString()}
                  </div>
                </div>
              )}
            </div>

            {/* Run button */}
            {!isAlreadyIndexed && !checkLoading && !gitStatusLoading && (
              <div className="tui-border bg-surface-container-low p-4 space-y-3">
                <span className="tui-border-title text-primary">
                  RUN_OPERATION
                </span>
                <div className="text-[11px] text-on-surface-variant pt-1">
                  {selectedExtensions.size === 0 || selectedDirs.size === 0 ? (
                    <span className="text-outline">no files selected</span>
                  ) : (
                    <>
                      <span className="text-primary font-bold">
                        {selectedCounts.files.toLocaleString()}
                      </span>{" "}
                      files selected
                      <br />
                      <span className="text-primary font-bold">
                        ~{selectedCounts.chunks.toLocaleString()}
                      </span>{" "}
                      estimated chunks
                    </>
                  )}
                </div>
                <button
                  onClick={handleStartIndexing}
                  disabled={
                    selectedExtensions.size === 0 || selectedDirs.size === 0
                  }
                  className="w-full border border-primary text-primary px-4 py-3 hover:bg-primary hover:text-on-primary transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex justify-between items-center text-[11px] font-extrabold tracking-[0.1em] uppercase"
                >
                  <span className="flex items-center gap-2">
                    <Play className="w-3.5 h-3.5" />
                    START_INDEX
                  </span>
                  <span className="opacity-40 font-normal">[ ENTER ]</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
