import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  GitBranch,
  GitCommit,
  FolderTree,
  Database,
  Settings,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { StatusDot } from "../shared/Badge";
import type { HealthStatus } from "../../lib/types";

interface SidebarProps {
  healthStatus: HealthStatus | null;
}

const navItems = [
  { path: "/", icon: LayoutDashboard, label: "Dashboard" },
  { path: "/graph", icon: GitBranch, label: "Knowledge Graph" },
  { path: "/review", icon: GitCommit, label: "Commit Review" },
  { path: "/files", icon: FolderTree, label: "File Explorer" },
  { path: "/indexing", icon: Database, label: "Indexing" },
  { path: "/settings", icon: Settings, label: "Settings" },
];

export function Sidebar({ healthStatus }: SidebarProps) {
  const [isExpanded, setIsExpanded] = useState(() => {
    const saved = localStorage.getItem("sidebarExpanded");
    return saved ? JSON.parse(saved) : false;
  });

  const handleToggle = () => {
    const newValue = !isExpanded;
    setIsExpanded(newValue);
    localStorage.setItem("sidebarExpanded", JSON.stringify(newValue));
  };

  const serverStatus = healthStatus?.status || "unhealthy";

  return (
    <aside
      className={`
        flex flex-col bg-bg-secondary border-r border-border
        transition-all duration-200 ease-out
        ${isExpanded ? "w-56" : "w-16"}
      `}
    >
      <div className="flex-1 py-4">
        <nav className="space-y-1 px-2">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => `
                flex items-center gap-3 px-3 py-2 rounded-lg
                transition-all duration-150
                ${
                  isActive
                    ? "bg-accent-blue/10 text-accent-blue border-l-2 border-accent-blue"
                    : "text-text-secondary hover:bg-bg-hover hover:text-text-primary border-l-2 border-transparent"
                }
              `}
              title={!isExpanded ? item.label : undefined}
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              {isExpanded && <span className="text-sm font-medium">{item.label}</span>}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="p-2 border-t border-border">
        <button
          onClick={handleToggle}
          className="w-full flex items-center justify-center p-2 text-text-muted hover:text-text-primary hover:bg-bg-hover rounded-lg transition-colors"
        >
          {isExpanded ? (
            <ChevronLeft className="w-5 h-5" />
          ) : (
            <ChevronRight className="w-5 h-5" />
          )}
        </button>

        {isExpanded && (
          <div className="flex items-center gap-2 px-3 py-2 mt-2 text-sm text-text-secondary">
            <StatusDot status={serverStatus as "healthy" | "degraded" | "unhealthy"} />
            <span>Server</span>
            <span className="text-xs text-text-muted">
              {healthStatus ? `${Math.round(healthStatus.uptime_seconds / 60)}m` : "offline"}
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}
