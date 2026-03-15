import { useState, useEffect } from "react";
import { FolderTree, File, Activity, Users, GitBranch } from "lucide-react";
import { useProjectContext } from "../App";
import { analyzeHealth, getFileExpert, analyzeDependencies } from "../lib/api";
import { FileTree } from "../components/shared/FileTree";
import { CodeBlock } from "../components/shared/CodeBlock";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import { ConfidenceBar } from "../components/shared/ConfidenceBar";
import { Badge } from "../components/shared/Badge";
import { getHealthColor } from "../lib/constants";
import type { FileNode, HealthResponse, ExpertResponse, DependencyResponse } from "../lib/types";

export default function FileExplorer() {
  const { projectPath } = useProjectContext();
  const [files, setFiles] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [expert, setExpert] = useState<ExpertResponse | null>(null);
  const [dependencies, setDependencies] = useState<DependencyResponse | null>(null);
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [isLoadingAnalysis, setIsLoadingAnalysis] = useState(false);

  useEffect(() => {
    if (!projectPath) return;

    const loadFiles = async () => {
      try {
        const fileList = await window.cgctl.listFiles(projectPath);
        const mapped: FileNode[] = fileList.map((f: any) => ({
          id: f.path,
          name: f.name,
          path: f.path,
          size: f.size,
          type: f.type,
        }));
        setFiles(mapped);
      } catch (error) {
        console.error("Failed to load files:", error);
      }
    };

    loadFiles();
  }, [projectPath]);

  const handleFileSelect = async (file: FileNode) => {
    setSelectedFile(file);
    setIsLoadingFile(true);
    setIsLoadingAnalysis(true);
    setHealth(null);
    setExpert(null);
    setDependencies(null);

    try {
      const absPath = `${projectPath}/${file.path}`;
      const content = await window.cgctl.readFile(absPath);
      setFileContent(content);

      const [healthResult, expertResult, depsResult] = await Promise.all([
        analyzeHealth(projectPath!, file.path).catch(() => null),
        getFileExpert(projectPath!, file.path).catch(() => null),
        analyzeDependencies(projectPath!, file.path).catch(() => null),
      ]);

      setHealth(healthResult);
      setExpert(expertResult);
      setDependencies(depsResult);
    } catch (error) {
      console.error("Failed to load file:", error);
    } finally {
      setIsLoadingFile(false);
      setIsLoadingAnalysis(false);
    }
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
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
