import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";

function TriStateCheckbox({ checked, indeterminate, onChange, disabled }: {
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
      className="w-4 h-4 rounded border-border accent-accent-blue"
    />
  );
}
import {
  Play,
  CheckCircle,
  XCircle,
  FolderOpen,
  FileCode,
  Network,
  Zap,
  RefreshCw,
  Trash2,
  ChevronDown,
  ChevronUp,
  FileSearch,
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
} from "../lib/api";
import type {
  IndexStatus,
  IndexEstimateResponse,
  IndexHistoryEntry,
  GitCleanlinessResponse,
  IndexDiffResponse,
} from "../lib/types";

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
          const share = d.estimated_chunks > 0 && estimate.estimated_total_chunks > 0
            ? e.estimated_chunks * (d.estimated_chunks / estimate.estimated_total_chunks)
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

function PhaseCard({
  label,
  value,
  subtext,
  icon: Icon,
  color,
  isActive
}: {
  label: string;
  value: string | number;
  subtext: string;
  icon: React.ElementType;
  color: "blue" | "green" | "amber" | "red" | "muted";
  isActive: boolean;
}) {
  const colorMap = {
    blue: "text-accent-blue bg-accent-blue/10 border-accent-blue/20",
    green: "text-accent-green bg-accent-green/10 border-accent-green/20",
    amber: "text-accent-amber bg-accent-amber/10 border-accent-amber/20",
    red: "text-accent-red bg-accent-red/10 border-accent-red/20",
    muted: "text-text-muted bg-bg-tertiary border-border",
  };
  const activeShadow = isActive && color === "blue" ? "shadow-[0_0_15px_rgba(59,130,246,0.1)] border-accent-blue/30" : "border-border shadow-sm";

  return (
    <div className={`bg-bg-secondary rounded-xl p-4 flex items-center justify-between border ${activeShadow}`}>
      <div>
        <h3 className="text-sm font-medium text-text-primary mb-1">{label}</h3>
        <div className={`text-2xl font-bold mb-1 ${colorMap[color].split(' ')[0]}`}>{value}</div>
        <p className="text-xs text-text-muted">{subtext}</p>
      </div>
      <div className={`w-10 h-10 rounded-full flex items-center justify-center border ${colorMap[color].split(' ').slice(1).join(' ')}`}>
        <Icon className={`w-5 h-5 ${colorMap[color].split(' ')[0]} ${isActive ? "animate-pulseFast" : ""}`} />
      </div>
    </div>
  );
}

export default function Indexing() {
  const { projectPath, projectName, indexStatus, setProject } = useProjectContext();
  const [isIndexing, setIsIndexing] = useState(false);
  const [localStatus, setLocalStatus] = useState<IndexStatus | null>(null);
  const [history, setHistory] = useState<IndexHistoryEntry[]>([]);
  const [currentFile, setCurrentFile] = useState<string | null>(null);
  const [startTime, setStartTime] = useState<number | null>(null);
  const [recentFiles, setRecentFiles] = useState<{file: string, status: string}[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const fileListRef = useRef<{file: string, status: string}[]>([]);

  const [checkLoading, setCheckLoading] = useState(true);
  const [isAlreadyIndexed, setIsAlreadyIndexed] = useState(false);
  const [chunksCount, setChunksCount] = useState(0);

  const [estimate, setEstimate] = useState<IndexEstimateResponse | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [selectedExtensions, setSelectedExtensions] = useState<Set<string>>(new Set());
  const [selectedDirs, setSelectedDirs] = useState<Set<string>>(new Set());
  const [activeGroupTab, setActiveGroupTab] = useState<"filetype" | "extension" | "directory">("filetype");
  const [deleting, setDeleting] = useState(false);

  const navigate = useNavigate();
  const [gitStatus, setGitStatus] = useState<GitCleanlinessResponse | null>(null);
  const [gitStatusLoading, setGitStatusLoading] = useState(true);
  const [dismissDirtyWarning, setDismissDirtyWarning] = useState(false);
  const [diffPreview, setDiffPreview] = useState<IndexDiffResponse | null>(null);
  const [diffPreviewLoading, setDiffPreviewLoading] = useState(false);

  const loadHistory = useCallback(async (pid: string) => {
    try {
      const entries = await getIndexHistory(pid);
      setHistory(entries.reverse());
    } catch {
      console.warn("Failed to load index history");
    }
  }, []);

  const loadEstimate = useCallback(async (pid: string, ppath: string) => {
    setEstimateLoading(true);
    try {
      const est = await getIndexEstimate(pid, ppath);
      setEstimate(est);
      setSelectedExtensions(new Set(
        est.by_extension
          .filter(e => SUPPORTED_EXTENSIONS.has(e.extension))
          .map(e => e.extension)
      ));
      setSelectedDirs(new Set(est.by_directory.map(d => d.path)));
    } catch {
      console.warn("Failed to load index estimate");
      setEstimate(null);
    } finally {
      setEstimateLoading(false);
    }
  }, []);

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
    ]).then(([status, _, __, git]) => {
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
    }).catch(() => {
      setIsAlreadyIndexed(false);
      setChunksCount(0);
      setGitStatus(null);
      setDiffPreview(null);
    }).finally(() => {
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
          if (status.current_file) setCurrentFile(status.current_file);

          if (status.status === "completed") {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
            setIsIndexing(false);
            setCurrentFile(null);
            setStartTime(null);
            setIsAlreadyIndexed(true);
            setChunksCount(status.chunks_created);
            if (projectName) loadHistory(projectName);
          } else if (status.status === "failed") {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
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

    setIsIndexing(true);
    setIsAlreadyIndexed(false);
    setLocalStatus(null);
    setCurrentFile(null);
    setRecentFiles([]);
    fileListRef.current = [];
    setStartTime(Date.now());

    try {
      const includeExtensions = Array.from(selectedExtensions).filter(e => SUPPORTED_EXTENSIONS.has(e));
      const includeDirs = Array.from(selectedDirs);
      const result = await indexProject(projectName, projectPath, false, includeExtensions.length > 0 ? includeExtensions : undefined, includeDirs.length > 0 ? includeDirs : undefined);
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
      }
    } catch (error) {
      const msg = (error as Error).message;
      if (msg.includes("409") || msg.toLowerCase().includes("uncommitted")) {
        setIsIndexing(false);
        setStartTime(null);
        try {
          const git = await checkGitWorkingTree(projectPath);
          setGitStatus(git);
        } catch { /* ignore */ }
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
    setSelectedExtensions(prev => {
      const next = new Set(prev);
      if (next.has(ext)) next.delete(ext); else next.add(ext);
      return next;
    });
  };

  const toggleDirectory = (path: string) => {
    setSelectedDirs(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  };

  const toggleGroup = (groupName: string) => {
    const group = FILE_TYPE_GROUPS.find(g => g.name === groupName);
    if (!group) return;
    const exts = group.extensions.filter(e => estimate?.by_extension.some(be => be.extension === e));
    if (exts.length === 0) return;
    const allSelected = exts.every(e => selectedExtensions.has(e));
    setSelectedExtensions(prev => {
      const next = new Set(prev);
      for (const e of exts) {
        if (allSelected) next.delete(e); else next.add(e);
      }
      return next;
    });
  };

  const isGroupFullySelected = (groupName: string) => {
    const group = FILE_TYPE_GROUPS.find(g => g.name === groupName);
    if (!group) return false;
    const exts = group.extensions.filter(e => estimate?.by_extension.some(be => be.extension === e));
    if (exts.length === 0) return false;
    return exts.every(e => selectedExtensions.has(e));
  };

  const isGroupPartiallySelected = (groupName: string) => {
    const group = FILE_TYPE_GROUPS.find(g => g.name === groupName);
    if (!group) return false;
    const exts = group.extensions.filter(e => estimate?.by_extension.some(be => be.extension === e));
    if (exts.length === 0) return false;
    const selected = exts.filter(e => selectedExtensions.has(e)).length;
    return selected > 0 && selected < exts.length;
  };

  const groupFileCount = (groupName: string) => {
    const group = FILE_TYPE_GROUPS.find(g => g.name === groupName);
    if (!group || !estimate) return 0;
    return estimate.by_extension
      .filter(e => group.extensions.includes(e.extension))
      .reduce((s, e) => s + e.count, 0);
  };

  const groupChunkCount = (groupName: string) => {
    const group = FILE_TYPE_GROUPS.find(g => g.name === groupName);
    if (!group || !estimate) return 0;
    return estimate.by_extension
      .filter(e => group.extensions.includes(e.extension))
      .reduce((s, e) => s + e.estimated_chunks, 0);
  };

  const otherExts = estimate
    ? estimate.by_extension.filter(e => !FILE_TYPE_GROUPS.some(g => g.extensions.includes(e.extension)))
    : [];
  const otherFiles = otherExts.reduce((s, e) => s + e.count, 0);

  const selectedCounts = useMemo(
    () => sumEstimate(estimate, selectedExtensions, selectedDirs),
    [estimate, selectedExtensions, selectedDirs]
  );

  const allDirsSelected = !!(estimate && selectedDirs.size === estimate.by_directory.length);

  const overallProgress = useMemo(() => {
    if (!localStatus) return 0;
    const phase1 = localStatus.files_total > 0
      ? (localStatus.files_processed / localStatus.files_total) * 50
      : 0;
    const phase2 = localStatus.graph_status === "completed"
      ? 50
      : localStatus.graph_status === "running"
        ? 25
        : 0;
    return Math.min(Math.round(phase1 + phase2), 100);
  }, [localStatus]);

  const estimatedTimeRemaining = useMemo(() => {
    if (!localStatus || !startTime || localStatus.files_processed === 0) return "--:--";
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
    return (localStatus.files_processed / elapsed).toFixed(1);
  }, [localStatus, startTime]);

  const getPhaseStatus = (current: number, total: number, phaseStatus: string) => {
    if (phaseStatus === "completed" || (total > 0 && current >= total)) return "completed";
    if (phaseStatus === "running" || (current > 0 && current < total)) return "running";
    if (phaseStatus === "failed") return "failed";
    return "pending";
  };

  const getPhaseColor = (status: string): "blue" | "green" | "amber" | "red" | "muted" => {
    if (status === "completed") return "green";
    if (status === "running") return "blue";
    if (status === "failed") return "red";
    return "muted";
  };

  if (!projectPath) {
    return (
      <div className="flex-1 overflow-y-auto p-6 flex flex-col items-center justify-center text-text-muted">
        <FolderOpen className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <p>No project selected</p>
        <p className="text-sm mt-1">Select a project to start indexing</p>
      </div>
    );
  }

  if (isIndexing || localStatus?.status === "running" || localStatus?.status === "queued") {
    return (
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        <section className="space-y-4">
          <div className="flex justify-between items-end mb-2">
            <div className="flex items-center space-x-2 text-sm text-text-muted">
              <Zap className={`w-4 h-4 text-accent-blue animate-pulseFast`} />
              <span>Processing Rate: {fileProcessingRate} files/s</span>
              {localStatus?.incremental && (
                <span className="text-xs bg-accent-blue/10 text-accent-blue border border-accent-blue/20 px-2 py-0.5 rounded">
                  Incremental
                </span>
              )}
            </div>
          </div>
          <div className="relative h-6 bg-bg-tertiary/60 border border-border/80 rounded-full overflow-hidden shadow-inner">
            <div
              className="absolute top-0 left-0 h-full rounded-full transition-all duration-500 progress-bar-shimmer animate-shimmer"
              style={{ width: `${overallProgress}%` }}
            ></div>
          </div>
          <div className="flex justify-between items-center text-sm">
            <span className="text-text-primary font-medium">Overall Progress: {overallProgress}%</span>
            <span className="text-text-muted">{estimatedTimeRemaining} remaining</span>
          </div>
        </section>

        <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <PhaseCard
            label="Code Indexing"
            value={localStatus ? `${Math.min(Math.round((localStatus.files_processed / Math.max(localStatus.files_total, 1)) * 100), 100)}%` : "0%"}
            subtext={`${localStatus?.files_processed || 0} / ${localStatus?.files_total || 0} files`}
            icon={FileCode}
            color={getPhaseColor(getPhaseStatus(localStatus?.files_processed || 0, localStatus?.files_total || 0, ""))}
            isActive={true}
          />
          <PhaseCard
            label="Knowledge Graph"
            value={localStatus?.graph_status === "completed" ? "100%" : localStatus?.graph_status === "running" ? "Running..." : "Pending"}
            subtext={`${localStatus?.graph_nodes || 0} nodes, ${localStatus?.graph_edges || 0} edges`}
            icon={Network}
            color={getPhaseColor(localStatus?.graph_status || "pending")}
            isActive={localStatus?.graph_status === "running"}
          />
        </section>

        {isIndexing && (
          <section className="bg-bg-secondary border border-border rounded-xl p-5">
            <h3 className="text-sm font-medium text-text-primary mb-3">Currently Processing</h3>
            <div className="flex items-center justify-between bg-bg-tertiary rounded-lg p-3 border border-border">
              <code className="text-sm text-text-secondary truncate w-full pr-4 font-mono">{currentFile || "Preparing..."}</code>
              <div className="w-5 h-5 spinner shrink-0"></div>
            </div>
          </section>
        )}

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-bg-secondary border border-border rounded-xl p-5 flex flex-col">
            <h3 className="text-sm font-medium text-text-primary mb-4 border-b border-border pb-2">Last Processed Files</h3>
            <ul className="space-y-3 flex-1 overflow-y-auto pr-2">
              {recentFiles.length > 0 ? recentFiles.map((file, i) => {
                const parts = file.file.split('/');
                const name = parts.length > 2 ? '.../' + parts.slice(-2).join('/') : file.file;
                return (
                  <li key={i} className="flex justify-between items-center text-sm">
                    <span className="text-text-secondary truncate font-mono text-xs pr-4">{name}</span>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      file.status === "Success"
                        ? "bg-accent-green/10 text-accent-green border border-accent-green/20"
                        : "bg-accent-red/10 text-accent-red border border-accent-red/20"
                    }`}>
                      {file.status}
                    </span>
                  </li>
                )
              }) : (
                <li className="text-sm text-text-muted italic">No files processed yet.</li>
              )}
            </ul>
          </div>

          <div className="bg-bg-secondary border border-border rounded-xl p-5 flex flex-col">
            <h3 className="text-sm font-medium text-text-primary mb-4 border-b border-border pb-2">
              Stats
              {localStatus?.incremental && <span className="ml-2 text-xs text-accent-blue font-normal">(incremental)</span>}
            </h3>
            <div className="grid grid-cols-2 gap-y-6 gap-x-4 flex-1">
              <div>
                <p className="text-xs text-text-muted mb-1">Total Files</p>
                <p className="text-lg font-semibold text-text-primary">{localStatus?.files_total || 0}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted mb-1">Chunks Created</p>
                <p className="text-lg font-semibold text-text-primary">{localStatus?.chunks_created || 0}</p>
              </div>
              {localStatus?.incremental && (
                <>
                  <div>
                    <p className="text-xs text-text-muted mb-1">Added Files</p>
                    <p className="text-lg font-semibold text-accent-green">{localStatus?.added_files || 0}</p>
                  </div>
                  <div>
                    <p className="text-xs text-text-muted mb-1">Modified Files</p>
                    <p className="text-lg font-semibold text-accent-blue">{localStatus?.modified_files || 0}</p>
                  </div>
                </>
              )}
              <div>
                <p className="text-xs text-text-muted mb-1">Graph Nodes</p>
                <p className="text-lg font-semibold text-text-primary">{localStatus?.graph_nodes || 0}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted mb-1">Graph Edges</p>
                <p className="text-lg font-semibold text-text-primary">{localStatus?.graph_edges || 0}</p>
              </div>
            </div>
          </div>
        </section>

        <section className="flex justify-end items-center space-x-4 pt-2">
          <button
            onClick={() => { setIsIndexing(false); setLocalStatus(null); }}
            className="px-4 py-2 bg-accent-red/10 hover:bg-accent-red/20 text-accent-red border border-accent-red/30 rounded-md text-sm font-medium transition-colors"
          >
            Cancel Indexing
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* ── Dirty working tree warning banner ────────────────────────────── */}
      {gitStatus?.has_changes && !dismissDirtyWarning && (
        <div className="bg-accent-amber/10 border border-accent-amber/30 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-accent-amber shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-semibold text-accent-amber">Working Tree Not Clean</h3>
              <p className="text-sm text-text-secondary mt-1">{gitStatus.summary}</p>
              <p className="text-xs text-text-muted mt-1">
                Indexing requires a clean working tree to keep the index in sync with git history.
                Please commit or stash your changes first.
              </p>
              <div className="flex items-center gap-3 mt-3">
                <button
                  onClick={() => navigate('/review')}
                  className="px-4 py-2 bg-accent-amber hover:bg-accent-amber/80 rounded-lg text-sm font-medium text-white transition-colors flex items-center gap-2"
                >
                  <GitCommit className="w-4 h-4" />
                  Go to Commit Review
                </button>
              </div>
            </div>
            <button
              onClick={() => setDismissDirtyWarning(true)}
              className="p-1 hover:bg-bg-tertiary rounded transition-colors shrink-0"
              title="Dismiss"
            >
              <X className="w-4 h-4 text-text-muted" />
            </button>
          </div>
        </div>
      )}

      {/* ── Main content (grayed out when dirty) ─────────────────────────── */}
      <div className={gitStatus?.has_changes && !dismissDirtyWarning ? 'pointer-events-none opacity-40 select-none' : ''}>
      <section>
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-text-primary">Code Indexing</h2>
            <p className="text-sm text-text-muted mt-1">{projectName}</p>
          </div>
        </div>

        {checkLoading || gitStatusLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-8 h-8 spinner"></div>
          </div>
        ) : isAlreadyIndexed ? (
          diffPreviewLoading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-8 h-8 spinner"></div>
            </div>
          ) : diffPreview?.incremental_possible ? (
            <div className="bg-bg-secondary border border-accent-blue/30 rounded-xl p-8 text-center space-y-4">
              <div className="w-16 h-16 rounded-full bg-accent-blue/10 flex items-center justify-center mx-auto">
                <RefreshCw className="w-8 h-8 text-accent-blue" />
              </div>
              <h3 className="text-lg font-semibold text-text-primary">Incremental Update Available</h3>
              <p className="text-text-muted text-sm max-w-md mx-auto">
                {diffPreview.message}
              </p>
              <div className="flex items-center justify-center gap-4 text-sm">
                {diffPreview.added.length > 0 && <span className="text-accent-green">+{diffPreview.added.length} added</span>}
                {diffPreview.modified.length > 0 && <span className="text-accent-blue">~{diffPreview.modified.length} modified</span>}
                {diffPreview.deleted.length > 0 && <span className="text-accent-red">-{diffPreview.deleted.length} deleted</span>}
              </div>
              <div className="flex items-center justify-center gap-3 pt-2">
                <button
                  onClick={handleStartIndexing}
                  className="px-6 py-3 bg-accent-blue hover:bg-accent-blue/80 rounded-xl text-white font-semibold transition-all flex items-center gap-2 shadow-lg shadow-accent-blue/25 hover:shadow-accent-blue/40"
                >
                  <RefreshCw className="w-4 h-4" />
                  Update Index
                </button>
                <button
                  onClick={handleDeleteIndex}
                  disabled={deleting}
                  className="px-6 py-3 bg-accent-red/10 hover:bg-accent-red/20 text-accent-red border border-accent-red/30 rounded-xl font-semibold transition-all flex items-center gap-2 disabled:opacity-50"
                >
                  <Trash2 className="w-4 h-4" />
                  {deleting ? "Deleting..." : "Delete Index"}
                </button>
              </div>
            </div>
          ) : (
            <div className="bg-bg-secondary border border-accent-green/30 rounded-xl p-8 text-center space-y-4">
              <div className="w-16 h-16 rounded-full bg-accent-green/10 flex items-center justify-center mx-auto">
                <CheckCircle className="w-8 h-8 text-accent-green" />
              </div>
              <h3 className="text-lg font-semibold text-text-primary">Project Already Indexed</h3>
              <p className="text-text-muted text-sm max-w-md mx-auto">
                {diffPreview?.message || (
                  <>This project has <strong>{chunksCount.toLocaleString()}</strong> chunks stored in the vector index.</>
                )}
              </p>
              <div className="flex items-center justify-center gap-3 pt-2">
                <button
                  onClick={handleStartIndexing}
                  className="px-6 py-3 bg-accent-blue hover:bg-accent-blue/80 rounded-xl text-white font-semibold transition-all flex items-center gap-2 shadow-lg shadow-accent-blue/25 hover:shadow-accent-blue/40"
                >
                  <RefreshCw className="w-4 h-4" />
                  Force Reindex
                </button>
                <button
                  onClick={handleDeleteIndex}
                  disabled={deleting}
                  className="px-6 py-3 bg-accent-red/10 hover:bg-accent-red/20 text-accent-red border border-accent-red/30 rounded-xl font-semibold transition-all flex items-center gap-2 disabled:opacity-50"
                >
                  <Trash2 className="w-4 h-4" />
                  {deleting ? "Deleting..." : "Delete Index"}
                </button>
              </div>
            </div>
          )
        ) : localStatus?.status === "failed" ? (
          <div className="bg-bg-secondary border border-accent-red/30 rounded-xl p-8 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-accent-red/10 flex items-center justify-center mx-auto">
              <XCircle className="w-8 h-8 text-accent-red" />
            </div>
            <h3 className="text-lg font-semibold text-text-primary">Indexing Failed</h3>
            <p className="text-text-muted text-sm max-w-md mx-auto">
              {localStatus.error_message || "The indexing job encountered an error. Please try again."}
            </p>
            <button
              onClick={handleStartIndexing}
              className="px-6 py-3 bg-accent-blue hover:bg-accent-blue/80 rounded-xl text-white font-semibold transition-all flex items-center gap-2 mx-auto shadow-lg shadow-accent-blue/25"
            >
              <RefreshCw className="w-4 h-4" />
              Retry Indexing
            </button>
          </div>
        ) : estimateLoading || !estimate ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-8 h-8 spinner"></div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Estimate summary */}
            <div className="bg-bg-secondary border border-border rounded-xl p-6">
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-full bg-accent-blue/10 flex items-center justify-center shrink-0">
                  <FileSearch className="w-6 h-6 text-accent-blue" />
                </div>
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-text-primary">Not Indexed Yet</h3>
                  <p className="text-text-muted text-sm mt-1">
                    Estimated <strong>{estimate.estimated_total_chunks.toLocaleString()}</strong> chunks from{" "}
                    <strong>{estimate.total_files.toLocaleString()}</strong> files found in the project.
                    {estimate.total_files !== estimate.by_extension.filter(e => SUPPORTED_EXTENSIONS.has(e.extension)).reduce((s, e) => s + e.count, 0) && (
                      <span className="block text-xs mt-1">
                        {estimate.by_extension.filter(e => !SUPPORTED_EXTENSIONS.has(e.extension)).length} unsupported file type(s) detected (will be skipped).
                      </span>
                    )}
                  </p>
                </div>
              </div>
            </div>

            {/* File Selection */}
            <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden">
              <div className="px-5 pt-4 pb-2">
                <h3 className="text-sm font-medium text-text-primary">File Selection</h3>
              </div>

              {/* Tab bar */}
              <div className="flex border-b border-border px-5">
                {(["filetype", "extension", "directory"] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => setActiveGroupTab(tab)}
                    className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                      activeGroupTab === tab
                        ? "text-accent-blue border-accent-blue"
                        : "text-text-muted border-transparent hover:text-text-primary"
                    }`}
                  >
                    {tab === "filetype" ? "By File Type" : tab === "extension" ? "By Extension" : "By Directory"}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <div className="p-5 max-h-72 overflow-y-auto space-y-1">
                {activeGroupTab === "filetype" && (
                  <>
                    {FILE_TYPE_GROUPS.map(group => {
                      const count = groupFileCount(group.name);
                      if (count === 0) return null;
                      const chk = groupChunkCount(group.name);
                      const checked = isGroupFullySelected(group.name);
                      const partial = isGroupPartiallySelected(group.name);
                      return (
                        <label key={group.name} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-bg-tertiary cursor-pointer group">
                          <div className="flex items-center gap-3">
                            <TriStateCheckbox
                              checked={checked}
                              indeterminate={partial}
                              onChange={() => toggleGroup(group.name)}
                            />
                            <span className="text-sm text-text-primary">{group.name}</span>
                          </div>
                          <span className="text-xs text-text-muted">{count} files{chk > 0 ? ` ~${chk} chunks` : ""}</span>
                        </label>
                      );
                    })}
                    {otherFiles > 0 && (
                      <label className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-bg-tertiary cursor-pointer opacity-60">
                        <div className="flex items-center gap-3">
                          <input type="checkbox" disabled className="w-4 h-4 rounded border-border" />
                          <span className="text-sm text-text-muted">Other</span>
                        </div>
                        <span className="text-xs text-text-muted">{otherFiles} files</span>
                      </label>
                    )}
                  </>
                )}

                {activeGroupTab === "extension" && (
                  estimate.by_extension.map(ext => {
                    const supported = SUPPORTED_EXTENSIONS.has(ext.extension);
                    return (
                      <label key={ext.extension} className={`flex items-center justify-between py-2 px-3 rounded-lg hover:bg-bg-tertiary cursor-pointer ${!supported ? "opacity-50" : ""}`}>
                        <div className="flex items-center gap-3">
                          <input
                            type="checkbox"
                            checked={selectedExtensions.has(ext.extension)}
                            onChange={() => supported && toggleExtension(ext.extension)}
                            disabled={!supported}
                            className="w-4 h-4 rounded border-border accent-accent-blue"
                          />
                          <span className="text-sm font-mono text-text-primary">{ext.extension}</span>
                          {!supported && <span className="text-xs text-text-muted italic">(unsupported)</span>}
                        </div>
                        <span className="text-xs text-text-muted">{ext.count} files ~{ext.estimated_chunks} chunks</span>
                      </label>
                    );
                  })
                )}

                {activeGroupTab === "directory" && (
                  <>
                    <label className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-bg-tertiary cursor-pointer border-b border-border mb-1">
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          checked={allDirsSelected}
                          onChange={() => {
                            if (allDirsSelected) setSelectedDirs(new Set());
                            else setSelectedDirs(new Set(estimate.by_directory.map(d => d.path)));
                          }}
                          className="w-4 h-4 rounded border-border accent-accent-blue"
                        />
                        <span className="text-sm font-medium text-text-primary">All Directories</span>
                      </div>
                      <span className="text-xs text-text-muted">{estimate.total_files} files</span>
                    </label>
                    {estimate.by_directory.map(dir => (
                      <label key={dir.path} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-bg-tertiary cursor-pointer">
                        <div className="flex items-center gap-3">
                          <input
                            type="checkbox"
                            checked={selectedDirs.has(dir.path)}
                            onChange={() => toggleDirectory(dir.path)}
                            className="w-4 h-4 rounded border-border accent-accent-blue"
                          />
                          <span className="text-sm text-text-primary truncate max-w-[200px]">{dir.path}/</span>
                        </div>
                        <span className="text-xs text-text-muted">{dir.count} files ~{dir.estimated_chunks} chunks</span>
                      </label>
                    ))}
                  </>
                )}
              </div>

              {/* Estimate bar */}
              <div className="px-5 py-3 border-t border-border bg-bg-tertiary/30 flex items-center justify-between">
                <span className="text-sm text-text-primary font-medium">
                  {selectedExtensions.size === 0 || selectedDirs.size === 0
                    ? "No files selected"
                    : `${selectedCounts.files} files, ~${selectedCounts.chunks} chunks selected`}
                </span>
                <span className="text-xs text-text-muted">
                  {estimate.by_extension.filter(e => SUPPORTED_EXTENSIONS.has(e.extension)).length} indexable types
                </span>
              </div>
            </div>

            <div className="flex justify-center pt-2">
              <button
                onClick={handleStartIndexing}
                disabled={selectedExtensions.size === 0 || selectedDirs.size === 0}
                className="px-8 py-3 bg-accent-blue hover:bg-accent-blue/80 rounded-xl text-white font-semibold transition-all flex items-center gap-2 shadow-lg shadow-accent-blue/25 hover:shadow-accent-blue/40 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Play className="w-5 h-5" />
                Start Indexing
              </button>
            </div>
          </div>
        )}
      </section>

      {/* History Accordion */}
      <section className="bg-bg-secondary border border-border rounded-xl">
        <button
          onClick={() => setShowHistory(!showHistory)}
          className="w-full px-5 py-4 flex justify-between items-center focus:outline-none hover:bg-bg-tertiary transition-colors rounded-xl"
        >
          <span className="text-sm font-medium text-text-primary">Indexing History ({history.length})</span>
          <div className="flex items-center gap-3">
            {history.length > 0 && (
              <button
                onClick={async (e) => {
                  e.stopPropagation();
                  if (!projectName) return;
                  try {
                    await clearIndexHistory(projectName);
                    setHistory([]);
                  } catch { /* ignore */ }
                }}
                className="text-xs text-text-muted hover:text-accent-red transition-colors px-2 py-1 rounded hover:bg-accent-red/10"
              >
                Clear
              </button>
            )}
            {showHistory ? <ChevronUp className="w-5 h-5 text-text-muted" /> : <ChevronDown className="w-5 h-5 text-text-muted" />}
          </div>
        </button>
        {showHistory && (
          <div className="p-5 border-t border-border">
            {history.length > 0 ? (
              <div className="space-y-2 max-h-64 overflow-y-auto pr-2">
                {history.map((entry) => (
                  <div key={entry.id} className="flex items-center justify-between p-3 bg-bg-tertiary rounded-lg">
                    <div className="flex items-center gap-3">
                      {entry.status === "completed" ? (
                        <CheckCircle className="w-5 h-5 text-accent-green" />
                      ) : (
                        <XCircle className="w-5 h-5 text-accent-red" />
                      )}
                      <div>
                        <div className="text-sm font-medium text-text-primary">{new Date(entry.date).toLocaleString()}</div>
                        <div className="text-xs text-text-muted flex items-center gap-2">
                          <span>{entry.files} files</span>
                          <span>·</span>
                          <span>{entry.chunks} chunks</span>
                          <span>·</span>
                          <span>{entry.duration}</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-xs text-text-muted flex gap-2">
                        <span title="Graph Nodes">{entry.nodes} <Network className="w-3 h-3 inline" /></span>
                      </div>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        entry.status === 'completed' ? 'bg-accent-green/10 text-accent-green border border-accent-green/20' :
                        'bg-accent-red/10 text-accent-red border border-accent-red/20'
                      }`}>
                        {entry.status.charAt(0).toUpperCase() + entry.status.slice(1)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-text-muted text-center py-4">No history available.</p>
            )}
          </div>
        )}
      </section>
      </div>{/* end gray-out wrapper */}
    </div>
  );
}
