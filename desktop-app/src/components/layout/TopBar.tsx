import { useNavigate } from "react-router-dom";
import { Terminal, Settings, Power } from "lucide-react";
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
  indexStatus,
  onCommandPaletteOpen,
  onClearProject,
}: TopBarProps) {
  const navigate = useNavigate();
  const isIndexing = indexStatus?.status === "running";

  return (
    <header className="h-14 bg-surface-container-low border-b border-outline-variant flex items-center px-4 gap-4 shrink-0 font-mono">
      {/* Left: brand + project path */}
      <div className="shrink-0 min-w-[140px]">
        <div className="text-primary font-bold text-sm tracking-wide leading-tight">CODEGUARDIAN</div>
        <div className="text-[11px] text-on-surface-variant leading-tight mt-0.5">
          root@local:{projectName ? `/${projectName}` : "~"}
        </div>
      </div>

      {/* Center: fake command-palette trigger */}
      <div className="flex-1 max-w-lg mx-auto">
        <button
          onClick={onCommandPaletteOpen}
          className="w-full flex items-center gap-2 px-3 py-1.5 border border-outline-variant bg-surface-container text-on-surface-variant text-[12px] hover:border-outline transition-colors"
        >
          <span className="text-primary shrink-0 text-[11px]">&gt;</span>
          <span className="flex-1 text-left tracking-wider">QUERY_DB_</span>
          {isIndexing ? (
            <span className="text-tertiary text-[10px] animate-pulseFast shrink-0 uppercase">INDEXING...</span>
          ) : (
            <span className="text-primary cursor-blink shrink-0">█</span>
          )}
          <kbd className="hidden sm:inline text-[10px] text-outline border border-outline-variant px-1 ml-1 shrink-0">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Right: icon buttons + avatar */}
      <div className="shrink-0 flex items-center gap-1 ml-auto">
        <button
          className="p-1.5 text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors"
          title="Terminal"
        >
          <Terminal className="w-4 h-4" />
        </button>
        <button
          onClick={() => navigate("/settings")}
          className="p-1.5 text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors"
          title="Settings"
        >
          <Settings className="w-4 h-4" />
        </button>
        <button
          onClick={onClearProject}
          className="p-1.5 text-on-surface-variant hover:text-error hover:bg-surface-container-high transition-colors"
          title="Close project"
        >
          <Power className="w-4 h-4" />
        </button>
        <div className="w-7 h-7 rounded-full bg-primary text-on-primary flex items-center justify-center text-[11px] font-bold ml-1 shrink-0">
          AT
        </div>
      </div>
    </header>
  );
}
