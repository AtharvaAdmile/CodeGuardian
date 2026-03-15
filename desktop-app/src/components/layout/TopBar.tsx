import { Search, X } from "lucide-react";
import { StatusDot } from "../shared/Badge";
import type { HealthStatus, IndexStatus } from "../../lib/types";

interface TopBarProps {
  projectName: string | null;
  healthStatus: HealthStatus | null;
  indexStatus: IndexStatus | null;
  onCommandPaletteOpen: () => void;
  onClearProject: () => void;
}

export function TopBar({
  projectName,
  healthStatus,
  indexStatus,
  onCommandPaletteOpen,
  onClearProject,
}: TopBarProps) {
  const serverStatus = healthStatus?.status || "unhealthy";
  const isIndexing = indexStatus?.status === "running";

  return (
    <header className="h-14 bg-bg-secondary border-b border-border flex items-center justify-between px-4">
      <div className="flex items-center gap-3">
        {projectName && (
          <>
            <div className="flex items-center gap-2">
              <span className="text-accent-blue font-semibold">CodeGuardian</span>
              <span className="text-text-muted">/</span>
              <span className="text-text-primary font-medium">{projectName}</span>
            </div>
            {isIndexing && (
              <div className="flex items-center gap-2 px-2 py-1 bg-accent-blue/10 rounded-full">
                <StatusDot status="running" size="sm" />
                <span className="text-xs text-accent-blue">
                  Indexing {indexStatus.files_processed}/{indexStatus.files_total} files
                </span>
              </div>
            )}
          </>
        )}
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={onCommandPaletteOpen}
          className="flex items-center gap-2 px-3 py-1.5 bg-bg-tertiary border border-border rounded-lg text-text-muted hover:text-text-primary hover:border-text-muted transition-colors"
        >
          <Search className="w-4 h-4" />
          <span className="text-sm">Search...</span>
          <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-xs bg-bg-hover rounded">
            ⌘K
          </kbd>
        </button>

        {projectName && (
          <button
            onClick={onClearProject}
            className="p-2 text-text-muted hover:text-text-primary hover:bg-bg-hover rounded-lg transition-colors"
            title="Close project"
          >
            <X className="w-5 h-5" />
          </button>
        )}

        <div className="flex items-center gap-2 px-2">
          <StatusDot status={serverStatus as "healthy" | "degraded" | "unhealthy"} />
        </div>
      </div>
    </header>
  );
}
