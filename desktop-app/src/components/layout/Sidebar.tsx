import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  GitBranch,
  GitCommit,
  FolderTree,
  Database,
  ShieldCheck,
  Settings,
} from "lucide-react";
import type { HealthStatus } from "../../lib/types";

interface SidebarProps {
  healthStatus: HealthStatus | null;
  onClearProject?: () => void;
}

const navItems = [
  { path: "/",           icon: LayoutDashboard, label: "DASHBOARD" },
  { path: "/graph",      icon: GitBranch,        label: "GRAPH" },
  { path: "/indexing",   icon: Database,         label: "INDEXER" },
  { path: "/compliance", icon: ShieldCheck,      label: "COMPLIANCE" },
  { path: "/files",      icon: FolderTree,       label: "REPOS" },
  { path: "/review",     icon: GitCommit,        label: "REVIEW" },
  { path: "/settings",   icon: Settings,         label: "CONFIG" },
];

export function Sidebar({ healthStatus, onClearProject }: SidebarProps) {
  const navigate = useNavigate();
  const isHealthy = healthStatus?.status === "healthy";

  return (
    <aside className="w-64 shrink-0 flex flex-col bg-surface-container-low border-r border-outline-variant font-mono">
      {/* Brand header */}
      <div className="px-4 py-3.5 border-b border-outline-variant">
        <div className="text-primary font-bold text-sm tracking-wide">GUARD_SYS_v1.0</div>
        <div className="flex items-center gap-1.5 mt-1">
          <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${isHealthy ? "bg-secondary" : "bg-error"}`} />
          <span className="text-[11px] text-on-surface-variant">
            STATUS: {isHealthy ? "SECURE" : "OFFLINE"}
          </span>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex-1 px-3 py-4">
        <div className="text-[11px] font-extrabold tracking-[0.1em] uppercase text-outline-variant mb-3 px-1">
          NAVIGATION
        </div>
        <nav className="space-y-0.5">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 text-[12px] transition-colors ${
                  isActive
                    ? "bg-primary text-on-primary"
                    : "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon className="w-3.5 h-3.5 shrink-0" strokeWidth={1.5} />
                  <span className="uppercase tracking-wider flex-1">{item.label}</span>
                  {isActive && <span className="text-[9px] text-on-primary/60">●</span>}
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </div>

      {/* Run Scan button */}
      <div className="px-3 pb-3">
        <button
          onClick={() => navigate("/compliance")}
          className="w-full py-2 text-[12px] font-bold text-on-secondary-container bg-secondary-container hover:opacity-90 transition-opacity uppercase tracking-wider"
        >
          [ RUN SCAN ]
        </button>
      </div>

      {/* System links */}
      <div className="px-3 pb-4 pt-3 border-t border-outline-variant">
        <div className="text-[11px] font-extrabold tracking-[0.1em] uppercase text-outline-variant mb-2">
          SYSTEM
        </div>
        <div className="flex gap-4 text-[12px] text-on-surface-variant">
          <NavLink to="/settings" className="hover:text-on-surface transition-colors uppercase">
            Config
          </NavLink>
          <a
            href="https://github.com/anthropics/claude-code/issues"
            target="_blank"
            rel="noreferrer"
            className="hover:text-on-surface transition-colors uppercase"
          >
            Help
          </a>
          {onClearProject && (
            <button
              onClick={onClearProject}
              className="hover:text-error transition-colors uppercase"
            >
              Logout
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
