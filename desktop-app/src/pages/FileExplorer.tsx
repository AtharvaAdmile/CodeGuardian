import { useState, useEffect } from "react";
import { AlertTriangle, Activity, File, FolderTree, GitBranch, RefreshCw, Sparkles, Users, Zap } from "lucide-react";
import { useProjectContext } from "../App";
import { analyzeHealth, analyzeImpact, getFileExpert, analyzeDependencies, getSavedImpactAnalysis } from "../lib/api";
import { FileTree } from "../components/shared/FileTree";
import { CodeBlock } from "../components/shared/CodeBlock";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import { ConfidenceBar } from "../components/shared/ConfidenceBar";
import { Badge } from "../components/shared/Badge";
import { RiskBadge } from "../components/shared/RiskBadge";
import { getHealthColor } from "../lib/constants";
import type { AffectedFileSchema, DependencyResponse, ExpertResponse, FileNode, HealthResponse, ImpactAnalyzeResponse } from "../lib/types";

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
        const fileList: { path: string; name: string; size: number; type: "file" | "directory" }[] =
          await window.cgctl.listFiles(projectPath);

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
          if (f.type === "directory") {
            node.children = [];
          }
          map.set(f.path, node);
        }

        for (const f of fileList) {
          const node = map.get(f.path)!;
          const parentDir = f.path.includes("/") ? f.path.substring(0, f.path.lastIndexOf("/")) : null;
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

      const [healthResult, expertResult, depsResult, savedImpactResult] = await Promise.all([
        analyzeHealth(projectPath!, file.path).catch(() => null),
        getFileExpert(projectPath!, file.path).catch(() => null),
        analyzeDependencies(projectPath!, file.path).catch(() => null),
        getSavedImpactAnalysis(projectPath!, file.path).catch(() => null),
      ]);

      setHealth(healthResult);
      setExpert(expertResult);
      setDependencies(depsResult);
      setImpact(savedImpactResult && !savedImpactResult.error ? savedImpactResult : null);
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

  const renderRiskItems = (items: AffectedFileSchema[], risk: "high" | "medium" | "low") => {
    if (items.length === 0) return null;

    return (
      <div className="space-y-2">
        {items.slice(0, 4).map((item) => (
          <div key={`${risk}-${item.file_path}`} className="rounded-lg border border-border bg-bg-tertiary p-2">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="truncate font-mono text-xs text-text-primary">{item.file_path}</div>
                <div className="mt-1 text-xs text-text-muted">{item.reason}</div>
              </div>
              <RiskBadge risk={risk} score={item.risk_score} />
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="flex h-full">
      <div className="w-64 border-r border-border bg-bg-secondary flex flex-col">
        <div className="p-4 border-b border-border">
          <h2 className="font-semibold flex items-center gap-2">
            <FolderTree className="w-5 h-5" />
            Files
          </h2>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          <FileTree
            files={files.slice(0, 200)}
            onFileSelect={handleFileSelect}
            selectedPath={selectedFile?.path}
          />
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4">
          {isLoadingFile ? (
            <div className="flex items-center justify-center h-full">
              <LoadingSpinner size="lg" />
            </div>
          ) : !selectedFile ? (
            <div className="flex flex-col items-center justify-center h-full text-text-muted">
              <File className="w-12 h-12 mb-4 opacity-50" />
              <p>Select a file to view</p>
            </div>
          ) : (
            <CodeBlock
              code={fileContent}
              language={selectedFile.name.split(".").pop() || "text"}
              maxHeight="none"
            />
          )}
        </div>
      </div>

      <div className="w-72 border-l border-border bg-bg-secondary overflow-y-auto">
        <div className="p-4 border-b border-border">
          <h2 className="font-semibold">File Context</h2>
        </div>
        <div className="p-4">
          {!selectedFile ? (
            <p className="text-sm text-text-muted">Select a file to see context</p>
          ) : isLoadingAnalysis ? (
            <div className="flex items-center justify-center py-8">
              <LoadingSpinner size="md" />
            </div>
          ) : (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-medium text-text-secondary mb-2 flex items-center gap-2">
                  <Activity className="w-4 h-4" />
                  Health
                </h3>
                {health ? (
                  <div className="bg-bg-tertiary rounded-lg p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-2xl font-bold" style={{ color: getHealthColor(health.health_score) }}>
                        {Math.round(health.health_score * 100)}%
                      </span>
                      {health.is_hotspot && (
                        <Badge variant="error" size="sm">Hotspot</Badge>
                      )}
                    </div>
                    <ConfidenceBar score={health.health_score} size="sm" />
                    {health.complexity && (health.complexity as any).score !== undefined && (
                      <div className="mt-2 text-xs text-text-muted">
                        Complexity: {(health.complexity as any).score} ({(health.complexity as any).rank})
                      </div>
                    )}
                    {health.churn && (health.churn as any).value !== undefined && (
                      <div className="mt-1 text-xs text-text-muted">
                        Churn: {(health.churn as any).value} ({(health.churn as any).rank})
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-text-muted">No health data</p>
                )}
              </div>

              <div>
                <h3 className="text-sm font-medium text-text-secondary mb-2 flex items-center gap-2">
                  <Users className="w-4 h-4" />
                  Owners
                </h3>
                {expert ? (
                  <div className="space-y-2">
                    {expert.primary_expert && (
                      <div className="bg-bg-tertiary rounded-lg p-3">
                        <div className="font-medium text-text-primary">
                          {expert.primary_expert}
                        </div>
                        <div className="text-xs text-text-muted">Primary</div>
                      </div>
                    )}
                    {expert.experts?.map((e, i) => (
                      <div key={i} className="bg-bg-tertiary rounded-lg p-2 text-sm">
                        <span className="text-text-primary">{e.name || e.author}</span>
                        {e.score && (
                          <ConfidenceBar score={e.score} size="sm" />
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-text-muted">No experts found</p>
                )}
              </div>

              <div>
                <h3 className="text-sm font-medium text-text-secondary mb-2 flex items-center gap-2">
                  <GitBranch className="w-4 h-4" />
                  Dependencies
                </h3>
                {dependencies ? (
                  <div className="space-y-2">
                    {dependencies.imports.length > 0 && (
                      <div>
                        <div className="text-xs text-text-muted mb-1">Imports</div>
                        <div className="flex flex-wrap gap-1">
                          {dependencies.imports.slice(0, 10).map((imp, i) => (
                            <Badge key={i} variant="default" size="sm">{imp}</Badge>
                          ))}
                        </div>
                      </div>
                    )}
                    {dependencies.function_calls.length > 0 && (
                      <div>
                        <div className="text-xs text-text-muted mb-1">Calls</div>
                        <div className="flex flex-wrap gap-1">
                          {dependencies.function_calls.slice(0, 10).map((fc, i) => (
                            <Badge key={i} variant="info" size="sm">{fc}</Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-text-muted">No dependencies</p>
                )}
              </div>

              <div>
                <h3 className="text-sm font-medium text-text-secondary mb-2 flex items-center gap-2">
                  <Zap className="w-4 h-4" />
                  Impact
                </h3>
                <button
                  onClick={handleImpactAnalysis}
                  disabled={isLoadingImpact}
                  className="w-full px-3 py-2 bg-accent-blue hover:bg-accent-blue/80 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white text-sm font-medium transition-colors flex items-center justify-center gap-2"
                >
                  {isLoadingImpact ? (
                    <>
                      <LoadingSpinner size="sm" />
                      Analyzing...
                    </>
                  ) : impact ? (
                    <>
                      <RefreshCw className="w-4 h-4" />
                      Re-analyze Impact
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      Analyze Impact
                    </>
                  )}
                </button>

                {impactError && (
                  <div className="mt-3 rounded-lg border border-accent-red/30 bg-accent-red/10 p-3 text-sm text-accent-red">
                    {impactError}
                  </div>
                )}

                {impact ? (
                  <div className="mt-3 space-y-3">
                    <div className="rounded-lg border border-border bg-bg-tertiary p-3">
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-text-primary">
                          {impact.total_affected} affected file(s)
                        </span>
                        {impact.persisted && <Badge variant="success" size="sm">Saved</Badge>}
                      </div>
                      <p className="text-sm leading-5 text-text-secondary">
                        {impact.agent_summary || impact.risk_assessment}
                      </p>
                      {impact.generated_at && (
                        <div className="mt-2 text-xs text-text-muted">
                          Generated {new Date(impact.generated_at).toLocaleString()}
                        </div>
                      )}
                    </div>

                    {impact.suggested_reviewers.length > 0 && (
                      <div>
                        <div className="text-xs text-text-muted mb-1">Reviewers</div>
                        <div className="flex flex-wrap gap-1">
                          {impact.suggested_reviewers.slice(0, 6).map((reviewer) => (
                            <Badge key={reviewer} variant="info" size="sm">{reviewer}</Badge>
                          ))}
                        </div>
                      </div>
                    )}

                    {impact.recommendations.length > 0 && (
                      <div>
                        <div className="text-xs text-text-muted mb-1">Recommendations</div>
                        <ul className="space-y-1">
                          {impact.recommendations.slice(0, 4).map((item) => (
                            <li key={item} className="text-sm leading-5 text-text-secondary">
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {impact.high_risk.length > 0 && (
                      <div>
                        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-accent-red">
                          <AlertTriangle className="w-4 h-4" />
                          High Risk
                        </div>
                        {renderRiskItems(impact.high_risk, "high")}
                      </div>
                    )}

                    {impact.medium_risk.length > 0 && (
                      <div>
                        <div className="mb-2 text-sm font-medium text-accent-amber">Medium Risk</div>
                        {renderRiskItems(impact.medium_risk, "medium")}
                      </div>
                    )}

                    {impact.validation_steps.length > 0 && (
                      <div>
                        <div className="text-xs text-text-muted mb-1">Validation</div>
                        <ul className="space-y-1">
                          {impact.validation_steps.slice(0, 4).map((item) => (
                            <li key={item} className="text-sm leading-5 text-text-secondary">
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-text-muted">
                    No saved impact analysis for this file.
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
