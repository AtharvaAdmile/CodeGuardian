import { useState } from "react";
import { ShieldCheck, Shield, Code, ChevronDown, ChevronUp } from "lucide-react";
import { useProjectContext } from "../App";
import { reviewCode } from "../lib/api";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import { Badge } from "../components/shared/Badge";
import { SeverityBadge } from "../components/shared/Badge";
import { ConfidenceBar } from "../components/shared/ConfidenceBar";
import type { ReviewResponse } from "../lib/types";

export default function CodeReview() {
  const { projectPath, projectName } = useProjectContext();
  const [code, setCode] = useState("");
  const [report, setReport] = useState<ReviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);
  const [expandedFindings, setExpandedFindings] = useState<Set<number>>(new Set());

  const handleReview = async () => {
    if (!code.trim() || !projectName || !projectPath) return;

    setIsLoading(true);
    setError(null);

    try {
      const result = await reviewCode(projectName, projectPath, code);
      if (result.error) {
        setError(result.error);
      } else {
        setReport(result);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleFinding = (idx: number) => {
    setExpandedFindings((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const filteredFindings = report?.findings.filter((f) =>
    severityFilter ? f.severity === severityFilter : true
  ) || [];

  const severityCounts = report?.severity_counts || {};

  return (
    <div className="flex h-full">
      <div className="w-1/2 flex flex-col border-r border-border">
        <div className="p-4 border-b border-border">
          <h2 className="font-semibold flex items-center gap-2">
            <Code className="w-5 h-5" />
            Code Input
          </h2>
        </div>
        
        <div className="flex-1 p-4">
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Paste your code here for review..."
            className="w-full h-full bg-bg-secondary border border-border rounded-lg px-4 py-3 font-mono text-sm text-text-primary placeholder-text-muted resize-none focus:outline-none focus:border-accent-blue"
          />
        </div>

        <div className="p-4 border-t border-border">
          <button
            onClick={handleReview}
            disabled={!code.trim() || isLoading}
            className="w-full px-6 py-2.5 bg-accent-blue hover:bg-accent-blue/80 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <>
                <LoadingSpinner size="sm" />
                Running Review...
              </>
            ) : (
              <>
                <ShieldCheck className="w-4 h-4" />
                Run Review
              </>
            )}
          </button>
        </div>
      </div>

      <div className="w-1/2 flex flex-col overflow-hidden">
        <div className="p-4 border-b border-border">
          <h2 className="font-semibold flex items-center gap-2">
            <Shield className="w-5 h-5" />
            Review Findings
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div className="bg-accent-red/20 border border-accent-red/30 rounded-lg p-4 text-accent-red mb-4">
              {error}
            </div>
          )}

          {!report && !isLoading && (
            <div className="flex flex-col items-center justify-center h-full text-text-muted">
              <ShieldCheck className="w-12 h-12 mb-4 opacity-50" />
              <p>Run a review to see findings</p>
            </div>
          )}

          {report && (
            <div className="space-y-4">
              <div className="bg-bg-secondary border border-border rounded-xl p-4">
                <h3 className="font-semibold mb-3">Summary</h3>
                <p className="text-sm text-text-secondary mb-4">{report.summary}</p>
                
                <div className="flex gap-2">
                  {Object.entries(severityCounts).map(([severity, count]) => (
                    <button
                      key={severity}
                      onClick={() => setSeverityFilter(severityFilter === severity ? null : severity)}
                      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                        severityFilter === severity
                          ? severity === "critical"
                            ? "bg-accent-red text-white"
                            : severity === "high"
                            ? "bg-accent-amber text-white"
                            : "bg-bg-tertiary text-text-primary"
                          : "bg-bg-tertiary text-text-secondary hover:text-text-primary"
                      }`}
                    >
                      {severity}: {count}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-3">
                {filteredFindings.map((finding, idx) => (
                  <div
                    key={idx}
                    className="bg-bg-secondary border border-border rounded-xl overflow-hidden"
                  >
                    <button
                      onClick={() => toggleFinding(idx)}
                      className="w-full flex items-center gap-3 p-4 text-left hover:bg-bg-hover transition-colors"
                    >
                      <div
                        className={`w-1 h-12 rounded-full ${
                          finding.severity === "critical"
                            ? "bg-accent-red"
                            : finding.severity === "high"
                            ? "bg-accent-amber"
                            : "bg-accent-blue"
                        }`}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <SeverityBadge severity={finding.severity} />
                          <Badge variant="info" size="sm">
                            {finding.category.toUpperCase()}
                          </Badge>
                        </div>
                        <h4 className="font-medium text-text-primary">
                          {finding.message}
                        </h4>
                        {finding.file_path && (
                          <p className="text-xs text-text-muted mt-1 font-mono">
                            {finding.file_path}:{finding.line || "?"}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <ConfidenceBar score={finding.confidence} size="sm" />
                        {expandedFindings.has(idx) ? (
                          <ChevronUp className="w-5 h-5 text-text-muted" />
                        ) : (
                          <ChevronDown className="w-5 h-5 text-text-muted" />
                        )}
                      </div>
                    </button>

                    {expandedFindings.has(idx) && finding.suggestion && (
                      <div className="px-4 pb-4 pt-2 border-t border-border bg-bg-tertiary/50">
                        <h5 className="text-sm font-medium text-text-secondary mb-2">
                          Suggestion
                        </h5>
                        <pre className="text-sm font-mono text-text-primary whitespace-pre-wrap">
                          {finding.suggestion}
                        </pre>
                      </div>
                    )}
                  </div>
                ))}

                {filteredFindings.length === 0 && (
                  <p className="text-center text-text-muted py-8">
                    No findings match the current filter
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
