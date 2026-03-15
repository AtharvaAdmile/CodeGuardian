import { useState, useEffect } from "react";
import { Zap, Users, Layers, AlertTriangle } from "lucide-react";
import { useProjectContext } from "../App";
import { analyzeImpact } from "../lib/api";
import { FileTree } from "../components/shared/FileTree";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import { RiskBadge } from "../components/shared/RiskBadge";
import { Badge } from "../components/shared/Badge";
import { ConfidenceBar } from "../components/shared/ConfidenceBar";
import type { FileNode, ImpactAnalyzeResponse, AffectedFileSchema } from "../lib/types";

export default function ImpactAnalyzer() {
  const { projectPath } = useProjectContext();
  const [files, setFiles] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | undefined>(undefined);
  const [report, setReport] = useState<ImpactAnalyzeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    high: true,
    medium: true,
    low: true,
  });

  useEffect(() => {
    if (!projectPath) return;

    const loadFiles = async () => {
      try {
        const fileList = await window.cgctl.listFiles(projectPath);
        const fileNodes: FileNode[] = fileList
          .filter((f: any) => f.type === "file")
          .map((f: any) => ({
            id: f.path,
            name: f.name,
            path: f.path,
            size: f.size,
            type: "file" as const,
          }));
        setFiles(fileNodes);
      } catch (error) {
        console.error("Failed to load files:", error);
      }
    };

    loadFiles();
  }, [projectPath]);

  const handleAnalyze = async () => {
    if (!selectedFile || !projectPath) return;

    setIsLoading(true);
    try {
      const result = await analyzeImpact(projectPath, selectedFile);
      setReport(result);
    } catch (error) {
      console.error("Failed to analyze impact:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  const renderRiskList = (
    items: AffectedFileSchema[],
    section: "high" | "medium" | "low"
  ) => {
    if (items.length === 0) {
      return <p className="text-sm text-text-muted py-2">No files</p>;
    }

    return (
      <div className="space-y-2">
        {items.map((file, i) => (
          <div
            key={i}
            className="bg-bg-tertiary rounded-lg p-3 border border-border"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="font-mono text-sm text-text-primary">
                {file.file_path}
              </span>
              <RiskBadge risk={section} score={file.risk_score} />
            </div>
            <div className="text-xs text-text-muted mb-2">
              Distance: {file.distance} · {file.reason}
            </div>
            <ConfidenceBar score={file.risk_score} size="sm" />
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="flex h-full">
      <div className="w-64 border-r border-border bg-bg-secondary flex flex-col">
        <div className="p-4 border-b border-border">
          <h2 className="font-semibold">Select File</h2>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          <FileTree
            files={files.slice(0, 100)}
            onFileSelect={(file) => setSelectedFile(file.path)}
            selectedPath={selectedFile}
          />
        </div>
        <div className="p-4 border-t border-border">
          <button
            onClick={handleAnalyze}
            disabled={!selectedFile || isLoading}
            className="w-full px-4 py-2 bg-accent-blue hover:bg-accent-blue/80 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <LoadingSpinner size="sm" />
            ) : (
              <>
                <Zap className="w-4 h-4" />
                Analyze Impact
              </>
            )}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {!report ? (
          <div className="flex flex-col items-center justify-center h-full text-text-muted">
            <AlertTriangle className="w-12 h-12 mb-4 opacity-50" />
            <p>Select a file and analyze its impact</p>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="bg-bg-secondary border border-border rounded-xl p-6">
              <h2 className="text-xl font-semibold mb-2">
                Impact Analysis: {report.changed_file}
              </h2>
              <p className="text-text-secondary">
                This file affects <span className="text-accent-blue font-bold">{report.total_affected}</span> downstream files across{" "}
                <span className="text-accent-violet font-bold">{report.affected_modules.length}</span> modules
              </p>

              {report.suggested_reviewers.length > 0 && (
                <div className="mt-4 pt-4 border-t border-border">
                  <div className="flex items-center gap-2 mb-2">
                    <Users className="w-4 h-4 text-accent-cyan" />
                    <span className="font-medium">Suggested Reviewers</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {report.suggested_reviewers.map((reviewer, i) => (
                      <Badge key={i} variant="info">{reviewer}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {report.affected_modules.length > 0 && (
                <div className="mt-4 pt-4 border-t border-border">
                  <div className="flex items-center gap-2 mb-2">
                    <Layers className="w-4 h-4 text-accent-violet" />
                    <span className="font-medium">Affected Modules</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {report.affected_modules.map((mod, i) => (
                      <Badge key={i} variant="default">{mod}</Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div>
              <button
                onClick={() => toggleSection("high")}
                className="flex items-center gap-2 w-full text-left mb-2"
              >
                <span className="font-semibold text-accent-red">
                  High Risk ({report.high_risk.length})
                </span>
              </button>
              {expandedSections.high && renderRiskList(report.high_risk, "high")}
            </div>

            <div>
              <button
                onClick={() => toggleSection("medium")}
                className="flex items-center gap-2 w-full text-left mb-2"
              >
                <span className="font-semibold text-accent-amber">
                  Medium Risk ({report.medium_risk.length})
                </span>
              </button>
              {expandedSections.medium && renderRiskList(report.medium_risk, "medium")}
            </div>

            <div>
              <button
                onClick={() => toggleSection("low")}
                className="flex items-center gap-2 w-full text-left mb-2"
              >
                <span className="font-semibold text-accent-green">
                  Low Risk ({report.low_risk.length})
                </span>
              </button>
              {expandedSections.low && renderRiskList(report.low_risk, "low")}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
