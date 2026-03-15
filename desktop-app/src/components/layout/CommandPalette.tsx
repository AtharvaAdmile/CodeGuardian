import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  MessageSquare,
  GitBranch,
  Zap,
  GraduationCap,
  ShieldCheck,
  FolderTree,
  Database,
  Settings,
  Search,
  Command,
} from "lucide-react";
import { useCommandPalette } from "../../hooks/useCommandPalette";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

const navigationItems = [
  { path: "/", icon: LayoutDashboard, label: "Go to Dashboard" },
  { path: "/ask", icon: MessageSquare, label: "Go to Q&A" },
  { path: "/graph", icon: GitBranch, label: "Go to Knowledge Graph" },
  { path: "/impact", icon: Zap, label: "Go to Impact Analyzer" },
  { path: "/onboard", icon: GraduationCap, label: "Go to Onboarding" },
  { path: "/review", icon: ShieldCheck, label: "Go to Code Review" },
  { path: "/files", icon: FolderTree, label: "Go to File Explorer" },
  { path: "/indexing", icon: Database, label: "Go to Indexing" },
  { path: "/settings", icon: Settings, label: "Go to Settings" },
];

export function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);

  const items = navigationItems.map((item) => ({
    id: item.path,
    label: item.label,
    category: "navigation" as const,
    action: () => navigate(item.path),
    icon: <item.icon className="w-4 h-4" />,
  }));

  const {
    searchQuery,
    setSearchQuery,
    filteredItems,
    selectedIndex,
    selectNext,
    selectPrev,
    executeSelected,
  } = useCommandPalette(items);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        selectNext();
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        selectPrev();
      }
      if (e.key === "Enter") {
        e.preventDefault();
        executeSelected();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, selectNext, selectPrev, executeSelected]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      
      <div className="relative w-full max-w-lg bg-bg-secondary border border-border rounded-xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Search className="w-5 h-5 text-text-muted" />
          <input
            ref={inputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search commands..."
            className="flex-1 bg-transparent text-text-primary placeholder-text-muted outline-none"
          />
          <kbd className="px-2 py-1 text-xs bg-bg-tertiary text-text-muted rounded">
            ESC
          </kbd>
        </div>

        <div className="max-h-80 overflow-y-auto py-2">
          {filteredItems.length === 0 ? (
            <div className="px-4 py-8 text-center text-text-muted">
              <Command className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No results found</p>
            </div>
          ) : (
            filteredItems.map((item, index) => (
              <button
                key={item.id}
                onClick={() => {
                  item.action();
                  onClose();
                }}
                className={`
                  w-full flex items-center gap-3 px-4 py-2 text-left
                  ${
                    index === selectedIndex
                      ? "bg-accent-blue/20 text-accent-blue"
                      : "text-text-primary hover:bg-bg-hover"
                  }
                `}
              >
                {item.icon}
                <span className="text-sm">{item.label}</span>
              </button>
            ))
          )}
        </div>

        <div className="px-4 py-2 border-t border-border text-xs text-text-muted">
          <span>↑↓ Navigate</span>
          <span className="mx-2">·</span>
          <span>↵ Select</span>
          <span className="mx-2">·</span>
          <span>ESC Close</span>
        </div>
      </div>
    </div>
  );
}
