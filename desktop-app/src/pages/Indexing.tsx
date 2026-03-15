import { useState, useEffect } from "react";
import { Database, Play, CheckCircle, XCircle, Clock, FolderOpen } from "lucide-react";
import { useProjectContext } from "../App";
import { indexProject } from "../lib/api";
import { Badge } from "../components/shared/Badge";
import type { IndexStatus } from "../lib/types";

export default function Indexing() {
  const { projectPath, projectName, indexStatus, setProject } = useProjectContext();
  const [isIndexing, setIsIndexing] = useState(false);
  const [localStatus, setLocalStatus] = useState<IndexStatus | null>(null);
  const [history] = useState<Array<{ date: string; files: number; chunks: number; status: string }>>([]);

  useEffect(() => {
    if (indexStatus) {
      setLocalStatus(indexStatus);
      setIsIndexing(indexStatus.status === "running");
    }
  }, [indexStatus]);

  const handleStartIndexing = async () => {
    if (!projectPath || !projectName) return;

    setIsIndexing(true);
    try {
      const result = await indexProject(projectName, projectPath, true);
      if (result.job_id) {
        setProject(projectPath, projectName, true);
      }
    } catch (error) {
      console.error("Failed to start indexing:", error);
    }
  };

  const progress = localStatus
    ? Math.round((localStatus.files_processed / Math.max(localStatus.files_total, 1)) * 100)
    : 0;

  return (
    <div className="flex flex-col h-full">
      <div className="p-6 border-b border-border">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Database className="w-6 h-6 text-accent-blue" />
          Indexing
        </h1>
        <p className="text-text-secondary mt-1">
          Manage project indexing and view history
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl mx-auto space-y-6">
          <div className="bg-bg-secondary border border-border rounded-xl p-6">
            <h2 className="text-lg font-semibold mb-4">Index Project</h2>
            
            {projectPath ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3 p-3 bg-bg-tertiary rounded-lg">
                  <FolderOpen className="w-5 h-5 text-text-muted" />
                  <span className="font-mono text-sm">{projectPath}</span>
                </div>

                {isIndexing && localStatus && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-text-secondary">Progress</span>
                      <span className="font-medium">{progress}%</span>
                    </div>
                    <div className="h-2 bg-bg-tertiary rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent-blue transition-all duration-300"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-xs text-text-muted">
                      <span>{localStatus.files_processed} / {localStatus.files_total} files</span>
                      <span>{localStatus.chunks_created} chunks</span>
                    </div>

                    <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border">
                      <div>
                        <div className="text-xs text-text-muted">Expertise</div>
                        <div className="text-sm font-medium">{localStatus.expertise_status}</div>
                      </div>
                      <div>
                        <div className="text-xs text-text-muted">Decisions</div>
                        <div className="text-sm font-medium">{localStatus.decision_status}</div>
                      </div>
                      <div>
                        <div className="text-xs text-text-muted">Graph Nodes</div>
                        <div className="text-sm font-medium">{localStatus.graph_nodes}</div>
                      </div>
                      <div>
                        <div className="text-xs text-text-muted">Graph Edges</div>
                        <div className="text-sm font-medium">{localStatus.graph_edges}</div>
                      </div>
                    </div>
                  </div>
                )}

                {!isIndexing && (
                  <button
                    onClick={handleStartIndexing}
                    className="w-full px-6 py-2.5 bg-accent-blue hover:bg-accent-blue/80 rounded-lg text-white font-medium transition-colors flex items-center justify-center gap-2"
                  >
                    <Play className="w-4 h-4" />
                    Start Indexing
                  </button>
                )}

                {localStatus?.errors.length ? (
                  <div className="mt-4 p-3 bg-accent-red/20 border border-accent-red/30 rounded-lg">
                    <div className="text-sm text-accent-red font-medium mb-2">
                      Errors ({localStatus.errors.length})
                    </div>
                    <div className="text-xs text-text-muted max-h-32 overflow-y-auto">
                      {localStatus.errors.map((err, i) => (
                        <div key={i} className="font-mono">{err}</div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="text-text-muted">No project selected</p>
            )}
          </div>

          <div className="bg-bg-secondary border border-border rounded-xl p-6">
            <h2 className="text-lg font-semibold mb-4">Index History</h2>
            
            {history.length === 0 ? (
              <div className="text-center py-8 text-text-muted">
                <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No indexing history yet</p>
              </div>
            ) : (
              <div className="space-y-2">
                {history.map((entry, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between p-3 bg-bg-tertiary rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      {entry.status === "completed" ? (
                        <CheckCircle className="w-5 h-5 text-accent-green" />
                      ) : (
                        <XCircle className="w-5 h-5 text-accent-red" />
                      )}
                      <div>
                        <div className="text-sm font-medium">{entry.date}</div>
                        <div className="text-xs text-text-muted">
                          {entry.files} files · {entry.chunks} chunks
                        </div>
                      </div>
                    </div>
                    <Badge
                      variant={entry.status === "completed" ? "success" : "error"}
                      size="sm"
                    >
                      {entry.status}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
