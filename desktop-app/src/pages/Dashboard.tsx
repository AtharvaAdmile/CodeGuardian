import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  FileText,
  Network,
  Clock,
  GitBranch,
  GitCommit,
  MessageSquare,
} from "lucide-react";
import { useProjectContext } from "../App";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import { getDashboardMetrics } from "../lib/api";
import type { DashboardResponse, RecentCommit, RecentQuestion } from "../lib/types";

interface MetricCardProps {
  title: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  onClick?: () => void;
}

function MetricCard({ title, value, icon: Icon, color, onClick }: MetricCardProps) {
  return (
    <div
      className={`tui-border p-5 ${onClick ? "cursor-pointer hover:bg-surface-container transition-colors" : ""}`}
      onClick={onClick}
    >
      <span className={`tui-border-title ${color}`}>{title}</span>
      <div className="flex items-end justify-between pt-3">
        <span className={`text-[20px] font-bold leading-tight ${color}`}>{value}</span>
        <Icon className={`w-5 h-5 ${color} opacity-30`} />
      </div>
    </div>
  );
}

function formatRelativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "NEVER";
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "UNKNOWN";
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  if (diffDays === 1) return "yesterday";
  if (diffDays < 30) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function lastIndexedColor(dateStr: string | null): string {
  if (!dateStr) return "text-on-surface-variant";
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "text-on-surface-variant";
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 86400000) return "text-secondary";
  return "text-tertiary";
}

function QueryItem({ question }: { question: RecentQuestion }) {
  return (
    <div
      className="py-3 px-4 border-b border-outline-variant/50 last:border-0 cursor-pointer hover:bg-surface-container transition-colors"
      onClick={() =>
        window.dispatchEvent(new CustomEvent("cg-open-session", { detail: question.session_id }))
      }
    >
      <div className="flex items-start gap-2">
        <span className="text-primary text-[12px] shrink-0 font-bold">$</span>
        <span className="text-on-surface text-[12px] flex-1 truncate">
          {question.title || question.preview}
        </span>
      </div>
      <div className="flex items-start gap-2 mt-1">
        <span className="text-outline text-[12px] shrink-0">&gt;&gt;</span>
        <span className="text-on-surface-variant text-[11px] flex-1 truncate">{question.preview}</span>
      </div>
      <div className="flex items-center gap-3 mt-2">
        <span className="text-[10px] px-1.5 py-0.5 bg-secondary-container text-on-secondary-container font-bold uppercase tracking-wider">
          COMPLETED
        </span>
        <span className="text-outline text-[11px]">
          {question.message_count} msg{question.message_count !== 1 ? "s" : ""}
        </span>
        <span className="text-outline text-[11px]">
          {formatRelativeTime(question.updated_at || question.created_at)}
        </span>
      </div>
    </div>
  );
}

function CommitLine({ commit }: { commit: RecentCommit }) {
  return (
    <div className="py-2.5 px-4 border-b border-outline-variant/50 last:border-0">
      <div className="flex items-baseline gap-2 text-[12px] min-w-0">
        <span className="text-outline shrink-0">*</span>
        <span className="text-tertiary shrink-0 font-bold">[{commit.sha.slice(0, 7)}]</span>
        <span className="text-on-surface truncate">{commit.message}</span>
      </div>
      <div className="flex items-center gap-2 ml-5 mt-0.5 text-[11px]">
        <span className="text-outline">|</span>
        <span className="text-outline">└─</span>
        <span className="text-on-surface-variant shrink-0">{commit.author}</span>
        <span className="text-outline">·</span>
        <span className="text-outline">{formatRelativeTime(commit.date)}</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { projectPath, projectName, indexStatus } = useProjectContext();
  const navigate = useNavigate();
  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!projectPath) {
      setIsLoading(false);
      return;
    }
    const loadDashboard = async () => {
      try {
        const result = await getDashboardMetrics(projectPath);
        setDashboardData(result);
      } catch (error) {
        console.error("Failed to load dashboard metrics:", error);
      } finally {
        setIsLoading(false);
      }
    };
    loadDashboard();
  }, [projectPath]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full bg-surface">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const isIndexing = dashboardData?.is_indexing || indexStatus?.status === "running";
  const filesIndexed = isIndexing
    ? (indexStatus?.files_processed ?? dashboardData?.files_indexed ?? 0)
    : (dashboardData?.files_indexed ?? 0);
  const graphNodes = dashboardData?.graph_nodes ?? 0;
  const graphEdges = dashboardData?.graph_edges ?? 0;
  const lastIndexedAt = dashboardData?.last_indexed_at ?? null;
  const recentCommits = dashboardData?.recent_commits ?? [];
  const recentQuestions = dashboardData?.recent_questions ?? [];

  return (
    <div className="h-full overflow-y-auto p-6 pt-8 pb-14 bg-surface font-mono space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-[11px] text-on-surface-variant">
        <span className="text-primary">/</span>
        <span className="uppercase tracking-wider">dashboard</span>
        {projectName && (
          <>
            <span className="text-outline-variant">/</span>
            <span className="text-on-surface uppercase truncate max-w-xs">{projectName}</span>
          </>
        )}
        {isIndexing && (
          <span className="ml-2 text-tertiary uppercase tracking-wider animate-pulseFast">
            · INDEXING
          </span>
        )}
      </div>

      {/* Row 1 — Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-2">
        <MetricCard
          title="TOTAL_FILES"
          value={filesIndexed}
          icon={FileText}
          color="text-primary"
          onClick={() => navigate("/files")}
        />
        <MetricCard
          title="GRAPH_NODES"
          value={graphNodes}
          icon={Network}
          color="text-secondary"
          onClick={() => navigate("/graph")}
        />
        <MetricCard
          title="LAST_INDEXED"
          value={formatRelativeTime(lastIndexedAt)}
          icon={Clock}
          color={lastIndexedColor(lastIndexedAt)}
          onClick={() => navigate("/indexing")}
        />
        <MetricCard
          title="GRAPH_EDGES"
          value={graphEdges}
          icon={GitBranch}
          color="text-on-surface-variant"
          onClick={() => navigate("/graph")}
        />
      </div>

      {/* Row 2 — Queries + Graph + Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 mt-2">
        {/* RECENT_QUERIES — 3 cols */}
        <div className="lg:col-span-3 tui-border">
          <span className="tui-border-title text-primary flex items-center gap-1.5">
            <MessageSquare className="w-3 h-3 inline-block" />
            RECENT_QUERIES
          </span>
          {recentQuestions.length === 0 ? (
            <div className="px-4 py-10 text-center">
              <p className="text-[11px] text-outline uppercase tracking-wider">-- NO QUERIES YET --</p>
              <p className="text-[11px] text-on-surface-variant mt-1">
                ask cg-pilot a question to get started
              </p>
            </div>
          ) : (
            <div>
              {recentQuestions.map((q: RecentQuestion) => (
                <QueryItem key={q.session_id} question={q} />
              ))}
            </div>
          )}
        </div>

        {/* Right column — 2 cols */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          {/* GRAPH_REPRESENTATION */}
          <div className="tui-border">
            <span className="tui-border-title text-secondary">GRAPH_REPRESENTATION</span>
            <div
              className="bg-surface-container-low m-3 flex flex-col items-center justify-center py-8 cursor-pointer group hover:bg-surface-container transition-colors"
              onClick={() => navigate("/graph")}
            >
              <pre className="text-[11px] text-outline-variant leading-snug select-none text-center">
{`  ●━━━━●━━━●
  ┃    ┃   ┃
  ●    ●━━━●
  ┃        ┃
  ●━━━━━━━━●`}
              </pre>
              <div className="mt-3 text-[11px] text-on-surface-variant group-hover:text-primary transition-colors uppercase tracking-wider">
                [ VIEW KNOWLEDGE GRAPH ]
              </div>
            </div>
          </div>

          {/* SYS_ACTIVITY_LOG */}
          <div className="tui-border">
            <span className="tui-border-title text-tertiary flex items-center gap-1.5">
              <GitCommit className="w-3 h-3 inline-block" />
              SYS_ACTIVITY_LOG
            </span>
            {recentCommits.length === 0 ? (
              <div className="px-4 py-6 text-center">
                <p className="text-[11px] text-outline uppercase tracking-wider">-- NO COMMITS --</p>
              </div>
            ) : (
              <div>
                {recentCommits.slice(0, 5).map((commit: RecentCommit) => (
                  <CommitLine key={commit.sha} commit={commit} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
