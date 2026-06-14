import { useState, useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { useProjectContext } from "../App";
import {
  analyzeHealth,
  analyzeImpact,
  getFileExpert,
  analyzeDependencies,
  getSavedImpactAnalysis,
} from "../lib/api";
import { FileTree } from "../components/shared/FileTree";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import type {
  DependencyResponse,
  ExpertResponse,
  FileNode,
  HealthResponse,
  ImpactAnalyzeResponse,
} from "../lib/types";

// ── sub-components ──────────────────────────────────────────────────────────

function HealthSegments({ score }: { score: number }) {
  const filled = Math.round(score * 10);
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: 10 }, (_, i) => (
        <div
          key={i}
          className={`h-2 flex-1 ${
            i < filled
              ? score >= 0.8
                ? "bg-secondary"
                : score >= 0.5
                ? "bg-tertiary"
                : "bg-error"
              : "bg-outline-variant opacity-50"
          }`}
        />
      ))}
    </div>
  );
}

function ownerInitials(name: string): string {
  return (
    name
      .split(/[\s._@/-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => (p[0] ?? "").toUpperCase())
      .join("") || "?"
  );
}

function OwnerChip({ name }: { name: string }) {
  return (
    <div
      title={name}
      className="w-7 h-7 bg-surface-container-highest border border-outline-variant flex items-center justify-center text-[10px] font-bold text-primary shrink-0"
    >
      {ownerInitials(name)}
    </div>
  );
}

function LiveMetrics({ lineCount }: { lineCount: number }) {
  const bars = Array.from({ length: 16 }, (_, i) => {
    const v = Math.abs(Math.sin(i * 2.1 + lineCount * 0.01)) * 75 + 10;
    return Math.round(v);
  });
  return (
    <div className="h-24 border-t border-outline-variant bg-surface-container-lowest flex flex-col px-4 pt-3 pb-2 shrink-0">
      <div className="flex justify-between items-center mb-2">
        <span className="text-[10px] font-extrabold tracking-[0.1em] text-primary uppercase">
          LIVE_METRICS
        </span>
        <span className="text-[10px] text-secondary font-mono">STABLE_NODE: 100%</span>
      </div>
      <div className="flex-1 flex items-end gap-px">
        {bars.map((h, i) => (
          <div
            key={i}
            className={`flex-1 ${i === bars.length - 1 ? "bg-secondary" : "bg-primary"}`}
            style={{ height: `${h}%`, opacity: 0.15 + (i / bars.length) * 0.85 }}
          />
        ))}
      </div>
    </div>
  );
}

// Filled header chip for context panels (bg-outline variation vs tui-border-title)
function PanelTitle({ label }: { label: string }) {
  return (
    <span className="absolute -top-2.5 left-2 bg-outline text-surface px-2 py-0.5 text-[10px] font-extrabold tracking-[0.1em] uppercase">
      {label}
    </span>
  );
}

// ── main page ────────────────────────────────────────────────────────────────

export default function FileExplorer() {
  const { projectPath, setSelectedFilePath } = useProjectContext();
  const [files, setFiles] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [expert, setExpert] = useState<ExpertResponse | null>(null);
  const [dependencies, setDependencies] = useState<DependencyResponse | null>(null);
  const [impact, setImpact] = useState<ImpactAnalyzeResponse | null>(null);
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [isLoadingAnalysis, setIsLoadingAnalysis] = useState(false);
  const [isLoadingImpact, setIsLoadingImpact] = useState(false);
  const [impactError, setImpactError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectPath) return;
    const loadFiles = async () => {
      try {
        const fileList: {
          path: string;
          name: string;
          size: number;
          type: "file" | "directory";
        }[] = await window.cgctl.listFiles(projectPath);

        const root: FileNode[] = [];
        const map = new Map<string, FileNode>();

        for (const f of fileList) {
          const node: FileNode = {
            id: f.path,
            name: f.name,
            path: f.path,
            size: f.size,
            type: f.type,
          };
          if (f.type === "directory") node.children = [];
          map.set(f.path, node);
        }

        for (const f of fileList) {
          const node = map.get(f.path)!;
          const parentDir = f.path.includes("/")
            ? f.path.substring(0, f.path.lastIndexOf("/"))
            : null;
          if (parentDir && map.has(parentDir)) {
            map.get(parentDir)!.children!.push(node);
          } else {
            root.push(node);
          }
        }

        setFiles(root);
      } catch (error) {
        console.error("Failed to load files:", error);
      }
    };
    loadFiles();
  }, [projectPath]);

  const handleFileSelect = async (file: FileNode) => {
    setSelectedFile(file);
    setSelectedFilePath(file.path);
    setIsLoadingFile(true);
    setIsLoadingAnalysis(true);
    setHealth(null);
    setExpert(null);
    setDependencies(null);
    setImpact(null);
    setImpactError(null);

    try {
      const absPath = `${projectPath}/${file.path}`;
      const content = await window.cgctl.readFile(absPath);
      setFileContent(content);

      const [healthResult, expertResult, depsResult, savedImpactResult] =
        await Promise.all([
          analyzeHealth(projectPath!, file.path).catch(() => null),
          getFileExpert(projectPath!, file.path).catch(() => null),
          analyzeDependencies(projectPath!, file.path).catch(() => null),
          getSavedImpactAnalysis(projectPath!, file.path).catch(() => null),
        ]);

      setHealth(healthResult);
      setExpert(expertResult);
      setDependencies(depsResult);
      setImpact(
        savedImpactResult && !savedImpactResult.error ? savedImpactResult : null
      );
    } catch (error) {
      console.error("Failed to load file:", error);
    } finally {
      setIsLoadingFile(false);
      setIsLoadingAnalysis(false);
    }
  };

  const handleImpactAnalysis = async () => {
    if (!projectPath || !selectedFile) return;
    setIsLoadingImpact(true);
    setImpactError(null);
    try {
      const result = await analyzeImpact(projectPath, selectedFile.path);
      if (result.error) {
        setImpactError(result.error);
      } else {
        setImpact(result);
      }
    } catch (error) {
      setImpactError((error as Error).message);
    } finally {
      setIsLoadingImpact(false);
    }
  };

  const lineCount = fileContent ? fileContent.split("\n").length : 0;
  const lines = fileContent ? fileContent.split("\n") : [];
  const healthPct = health ? Math.round(health.health_score * 100) : null;
  const healthColor =
    healthPct === null
      ? "text-on-surface-variant"
      : healthPct >= 80
      ? "text-secondary"
      : healthPct >= 50
      ? "text-tertiary"
      : "text-error";

  const allOwners: string[] = [];
  if (expert?.primary_expert) allOwners.push(expert.primary_expert);
  expert?.experts?.forEach((e) => {
    const name = ((e as { name?: string; author?: string }).name ||
      (e as { name?: string; author?: string }).author ||
      "").trim();
    if (name && !allOwners.includes(name)) allOwners.push(name);
  });

  return (
    <div className="flex h-full font-mono overflow-hidden">
      {/* ── LEFT: file tree ─────────────────────────────────────────── */}
      <div className="w-64 border-r border-outline bg-surface-container flex flex-col shrink-0">
        {/* Header */}
        <div className="px-4 pt-4 pb-3 border-b border-outline-variant">
          <div className="text-[13px] font-extrabold text-primary tracking-wide">
            GUARD_ADMIN
          </div>
          <div className="text-[10px] text-on-surface-variant mt-0.5 tracking-[0.06em]">
            V2.0.4-STABLE
          </div>
        </div>

        {/* Tree */}
        <div className="flex-1 overflow-y-auto px-3 pt-2 pb-2">
          <FileTree
            files={files.slice(0, 200)}
            onFileSelect={handleFileSelect}
            selectedPath={selectedFile?.path}
          />
        </div>

        {/* Actions */}
        <div className="border-t border-outline-variant px-3 py-3 shrink-0">
          <div className="text-[10px] font-extrabold tracking-[0.1em] text-outline uppercase mb-2">
            ACTIONS
          </div>
          <button
            onClick={() => window.history.back()}
            className="w-full text-left text-[11px] text-on-surface-variant hover:text-primary py-1 transition-colors"
          >
            $ cd ../
          </button>
          {selectedFile && (
            <button
              onClick={handleImpactAnalysis}
              disabled={isLoadingImpact}
              className="w-full text-left text-[11px] text-on-surface-variant hover:text-secondary py-1 transition-colors disabled:opacity-40"
            >
              $ run impact_scan
            </button>
          )}
        </div>
      </div>

      {/* ── CENTER: editor ──────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden bg-surface">
        {/* Tab bar */}
        <div className="border-b border-outline-variant bg-surface-container-low px-4 py-0 h-10 flex items-end shrink-0">
          {selectedFile ? (
            <div className="flex items-center gap-3 h-full">
              <div className="border-t-2 border-primary bg-surface px-4 h-full flex items-center gap-2 -mb-px">
                <span className="text-[12px] text-on-surface">{selectedFile.name}</span>
              </div>
            </div>
          ) : (
            <div className="flex items-center h-full px-4 border-t-2 border-outline-variant -mb-px">
              <span className="text-[12px] text-on-surface-variant">
                $ CODEGUARDIAN // TUI_IDE
              </span>
            </div>
          )}
        </div>

        {/* Code area */}
        <div className="flex-1 overflow-auto relative">
          {isLoadingFile ? (
            <div className="flex items-center justify-center h-full">
              <LoadingSpinner size="lg" />
            </div>
          ) : !selectedFile ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <pre className="text-[11px] text-outline-variant leading-tight select-none">
{`  ┌────────────────────────────────┐
  │  CODEGUARDIAN // TUI_IDE       │
  │  ──────────────────────────── │
  │                                │
  │  $ SELECT_FILE_FROM_TREE      │
  │  > awaiting input...█         │
  │                                │
  └────────────────────────────────┘`}
                </pre>
              </div>
            </div>
          ) : (
            <div className="flex min-h-full text-[13px] leading-6">
              {/* Line numbers */}
              <div className="w-12 shrink-0 text-right pr-3 pt-4 pb-4 text-outline-variant opacity-50 select-none bg-surface-container-lowest border-r border-outline-variant/30">
                {lines.map((_, i) => (
                  <div key={i}>{String(i + 1).padStart(2, "0")}</div>
                ))}
              </div>
              {/* Code content */}
              <pre className="flex-1 pt-4 px-4 pb-4 text-on-surface whitespace-pre overflow-x-auto">
                <code>{fileContent}</code>
              </pre>
            </div>
          )}
        </div>

        {/* LIVE_METRICS footer */}
        <LiveMetrics lineCount={lineCount} />
      </div>

      {/* ── RIGHT: context panel ────────────────────────────────────── */}
      <div className="w-72 border-l border-outline bg-surface-container-low flex flex-col overflow-y-auto shrink-0">
        <div className="px-0 pt-6 pb-4 space-y-6">
          {/* FILE_INFO */}
          <div className="border border-outline relative pt-5 mx-3 pb-4">
            <PanelTitle label="FILE_INFO" />

            {!selectedFile ? (
              <div className="px-3 text-[11px] text-outline">
                — select a file —
              </div>
            ) : isLoadingAnalysis ? (
              <div className="flex justify-center py-4">
                <LoadingSpinner size="sm" />
              </div>
            ) : (
              <div className="px-3 space-y-4">
                {/* Health */}
                <div>
                  <div className="flex justify-between items-baseline mb-1.5">
                    <span className="text-[10px] font-extrabold tracking-[0.1em] text-outline uppercase">
                      HEALTH
                    </span>
                    <span className={`text-[18px] font-bold ${healthColor}`}>
                      {healthPct !== null ? `${healthPct}%` : "—"}
                    </span>
                  </div>
                  {health && <HealthSegments score={health.health_score} />}
                  {health?.is_hotspot && (
                    <div className="mt-1 text-[10px] text-tertiary uppercase tracking-wider">
                      ▲ HOTSPOT DETECTED
                    </div>
                  )}
                </div>

                {/* Owners */}
                <div>
                  <div className="text-[10px] font-extrabold tracking-[0.1em] text-outline uppercase mb-2">
                    OWNERS
                  </div>
                  {allOwners.length > 0 ? (
                    <div className="flex items-center -space-x-1">
                      {allOwners.slice(0, 5).map((name) => (
                        <OwnerChip key={name} name={name} />
                      ))}
                      {allOwners.length > 5 && (
                        <div className="w-7 h-7 bg-surface-container-highest border border-outline-variant flex items-center justify-center text-[10px] text-on-surface-variant shrink-0">
                          +{allOwners.length - 5}
                        </div>
                      )}
                    </div>
                  ) : (
                    <span className="text-[11px] text-outline">no owners</span>
                  )}
                </div>

                {/* Dependencies */}
                <div>
                  <div className="text-[10px] font-extrabold tracking-[0.1em] text-outline uppercase mb-2">
                    DEPENDENCIES
                  </div>
                  {dependencies && dependencies.imports.length > 0 ? (
                    <div className="space-y-1">
                      {dependencies.imports.slice(0, 6).map((imp, i) => (
                        <div
                          key={i}
                          className="flex items-center gap-2 text-[11px]"
                        >
                          <span className="text-primary shrink-0">█</span>
                          <span className="text-on-surface-variant truncate">
                            {imp}
                          </span>
                        </div>
                      ))}
                      {dependencies.imports.length > 6 && (
                        <div className="text-[10px] text-outline mt-1">
                          +{dependencies.imports.length - 6} more
                        </div>
                      )}
                    </div>
                  ) : (
                    <span className="text-[11px] text-outline">none</span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* VISUAL_IMPACT */}
          <div className="border border-outline relative pt-5 mx-3 pb-4">
            <PanelTitle label="VISUAL_IMPACT" />

            {isLoadingImpact ? (
              <div className="flex justify-center py-6">
                <LoadingSpinner size="sm" />
              </div>
            ) : impactError ? (
              <div className="px-3 py-1">
                <div className="text-[11px] text-error flex items-start gap-1.5">
                  <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                  <span className="leading-5">{impactError}</span>
                </div>
              </div>
            ) : impact ? (
              <div className="px-3 space-y-3">
                <div className="flex justify-between items-baseline">
                  <span className="text-[12px] text-on-surface font-bold">
                    {impact.total_affected} affected
                  </span>
                  <span
                    className={`text-[10px] font-extrabold uppercase ${
                      impact.high_risk.length > 0
                        ? "text-error"
                        : "text-secondary"
                    }`}
                  >
                    {impact.high_risk.length > 0
                      ? `${impact.high_risk.length} HIGH`
                      : "LOW RISK"}
                  </span>
                </div>
                <p className="text-[11px] text-on-surface-variant leading-5">
                  {(impact.agent_summary || impact.risk_assessment || "").slice(
                    0,
                    140
                  )}
                  {(impact.agent_summary || impact.risk_assessment || "")
                    .length > 140 && "…"}
                </p>
                {impact.recommendations.length > 0 && (
                  <div>
                    <div className="text-[10px] text-outline uppercase tracking-wider mb-1">
                      RECOMMENDATIONS
                    </div>
                    {impact.recommendations.slice(0, 2).map((r, i) => (
                      <div
                        key={i}
                        className="text-[11px] text-on-surface-variant flex items-start gap-1.5 mb-1 leading-5"
                      >
                        <span className="text-primary shrink-0">›</span>
                        <span>{r}</span>
                      </div>
                    ))}
                  </div>
                )}
                {impact.persisted && (
                  <div className="text-[10px] text-secondary uppercase tracking-wider">
                    ✓ SAVED
                  </div>
                )}
              </div>
            ) : (
              <div className="px-3 py-3">
                <pre className="text-[10px] text-outline-variant leading-tight text-center select-none">
{`  ●━━━○━━━●
  ┃        ┃
  ○   ◇    ○
      ┃
      ●━━━○`}
                </pre>
                <div className="text-[10px] text-outline text-center mt-2 uppercase tracking-wider">
                  NO IMPACT DATA
                </div>
              </div>
            )}
          </div>

          {/* RE-ANALYZE button */}
          {selectedFile && (
            <div className="mx-3">
              <button
                onClick={handleImpactAnalysis}
                disabled={isLoadingImpact}
                className="w-full border border-primary text-primary hover:bg-primary hover:text-on-primary disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-[11px] font-extrabold tracking-[0.1em] uppercase py-2 flex items-center justify-center gap-2"
              >
                {isLoadingImpact ? (
                  <>
                    <LoadingSpinner size="sm" />
                    ANALYZING...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-3 h-3" />
                    {impact ? "[ RE-ANALYZE_IMPACT ]" : "[ RUN_IMPACT_SCAN ]"}
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
