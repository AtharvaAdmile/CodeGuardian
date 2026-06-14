import { useEffect, useRef } from "react";
// Note: keyboard navigation (ArrowUp/Down/Enter/Escape) is handled inside useCommandPalette
import { useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  GitBranch,
  GitCommit,
  FolderTree,
  Database,
  Settings,
} from "lucide-react";
import { useCommandPalette } from "../../hooks/useCommandPalette";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

const navigationItems = [
  { path: "/",           icon: LayoutDashboard, label: "Go to Dashboard" },
  { path: "/graph",      icon: GitBranch,       label: "Go to Knowledge Graph" },
  { path: "/review",     icon: GitCommit,       label: "Go to Commit Review" },
  { path: "/files",      icon: FolderTree,      label: "Go to File Explorer" },
  { path: "/indexing",   icon: Database,        label: "Go to Indexing" },
  { path: "/settings",   icon: Settings,        label: "Go to Settings" },
];

export function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);

  const items = navigationItems.map((item) => ({
    id: item.path,
    label: item.label,
    category: "navigation" as const,
    action: () => navigate(item.path),
    icon: <item.icon className="w-3.5 h-3.5" />,
  }));

  const {
    searchQuery,
    setSearchQuery,
    filteredItems,
    selectedIndex,
  } = useCommandPalette(items);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 font-mono">
      <div className="absolute inset-0 bg-black/75" onClick={onClose} />

      <div className="relative w-full max-w-lg bg-bg-primary border border-border shadow-[0_0_30px_rgba(51,255,0,0.1)]">
        {/* Title bar */}
        <div className="term-titlebar bg-bg-secondary">
          <span>COMMAND PALETTE</span>
        </div>

        {/* Search input */}
        <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border bg-bg-secondary/40">
          <span className="text-accent-green text-xs glow shrink-0">&gt;</span>
          <span className="text-text-muted text-[11px] shrink-0">search:</span>
          <input
            ref={inputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1 bg-transparent text-text-primary outline-none text-xs font-mono caret-transparent"
            placeholder=""
            autoComplete="off"
            spellCheck={false}
          />
          <span className="text-accent-green text-xs animate-blink glow">█</span>
        </div>

        {/* Results */}
        <div className="max-h-64 overflow-y-auto">
          {filteredItems.length === 0 ? (
            <div className="py-8 text-center">
              <p className="text-[11px] text-text-muted uppercase tracking-widest">-- NO RESULTS --</p>
            </div>
          ) : (
            filteredItems.map((item, index) => (
              <button
                key={item.id}
                onClick={() => { item.action(); onClose(); }}
                className={`
                  w-full flex items-center gap-3 px-3 py-2.5 text-left text-xs border-b border-border/40 transition-colors
                  ${index === selectedIndex
                    ? "bg-accent-green/10 text-accent-green border-l-2 border-l-accent-green"
                    : "text-text-muted hover:text-text-primary hover:bg-bg-hover"
                  }
                `}
              >
                <span className="text-text-muted/60 w-6 shrink-0 font-mono text-[10px]">
                  [{String(index + 1).padStart(2, "0")}]
                </span>
                <span className={index === selectedIndex ? "text-accent-green" : "text-text-muted"}>
                  {item.icon}
                </span>
                <span className="uppercase tracking-wide font-mono">{item.label}</span>
              </button>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="px-3 py-1.5 border-t border-border bg-bg-secondary flex items-center gap-4">
          <span className="text-[9px] text-text-muted uppercase tracking-widest">↑↓ navigate</span>
          <span className="text-[9px] text-text-muted uppercase tracking-widest">↵ select</span>
          <span className="text-[9px] text-text-muted uppercase tracking-widest">ESC close</span>
        </div>
      </div>
    </div>
  );
}
