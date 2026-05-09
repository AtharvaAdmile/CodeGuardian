import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  FileText,
  GitBranch,
  Activity,
  Network,
  AlertTriangle,
  TrendingUp,
} from "lucide-react";
import { useProjectContext } from "../App";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import { getDashboardMetrics } from "../lib/api";
import type { DashboardResponse, DashboardHotspot } from "../lib/types";

interface MetricCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: string;
  onClick?: () => void;
}

function MetricCard({ icon, label, value, color, onClick }: MetricCardProps) {
  return (
    <button
      onClick={onClick}
      className="bg-bg-secondary border border-border rounded-xl p-4 hover:border-text-muted transition-colors text-left w-full"
    >
      <div className="flex items-start justify-between mb-3">
        <div className={`p-2 rounded-lg ${color}`}>{icon}</div>
      </div>
      <div className="text-3xl font-bold" style={{ color }}>{value}</div>
      <div className="text-sm text-text-secondary mt-1">{label}</div>
    </button>
  );
}

export default function Dashboard() {
  const { projectPath, projectName, indexStatus } = useProjectContext();
  const navigate = useNavigate();
  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!projectPath) return;

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
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const isIndexing = dashboardData?.is_indexing || indexStatus?.status === "running";
  const filesIndexed = dashboardData?.files_indexed ?? indexStatus?.files_processed ?? 0;
  const graphNodes = dashboardData?.graph_nodes ?? 0;
  const avgHealth = dashboardData?.avg_health_score ?? 0;
  const graphEdges = dashboardData?.graph_edges ?? 0;
  const hotspots = dashboardData?.hotspots ?? [];

  return (
    <div className="flex flex-col h-full">
      <div className="p-6 border-b border-border">
        <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
        <p className="text-text-secondary mt-1">
          {projectName} — {isIndexing ? "Indexing in progress..." : "Ready"}
        </p>
      </div>
      <div className="flex-1 overflow-y-auto p-6">
      <div className="space-y-6">

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          icon={<FileText className="w-5 h-5" />}
          label="Total Files"
          value={filesIndexed}
          color="text-accent-blue"
          onClick={() => navigate("/files")}
        />
        <MetricCard
          icon={<Network className="w-5 h-5" />}
          label="Graph Nodes"
          value={graphNodes}
          color="text-accent-violet"
          onClick={() => navigate("/graph")}
        />
        <MetricCard
          icon={<Activity className="w-5 h-5" />}
          label="Avg Health Score"
          value={`${Math.round(avgHealth * 100)}%`}
          color={avgHealth >= 0.8 ? "text-accent-green" : avgHealth >= 0.5 ? "text-accent-amber" : "text-accent-red"}
          onClick={() => navigate("/graph")}
        />
        <MetricCard
          icon={<GitBranch className="w-5 h-5" />}
          label="Graph Edges"
          value={graphEdges}
          color="text-accent-cyan"
          onClick={() => navigate("/graph")}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-bg-secondary border border-border rounded-xl p-4">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-accent-blue" />
            Recent Questions
          </h2>
          <div className="space-y-3">
            <div className="text-center py-8 text-text-muted">
              <p className="text-sm">CG-pilot conversations will appear here</p>
            </div>
          </div>
        </div>

        <div className="bg-bg-secondary border border-border rounded-xl p-4">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-accent-amber" />
            Top Hotspots
          </h2>
          <div className="space-y-3">
            {hotspots.length === 0 ? (
              <div className="text-center py-8 text-text-muted">
                <p className="text-sm">No hotspots detected</p>
                <button
                  onClick={() => navigate("/files")}
                  className="text-accent-blue hover:underline text-sm mt-2"
                >
                  Explore files →
                </button>
              </div>
            ) : (
              hotspots.map((hotspot: DashboardHotspot, index: number) => (
                <div key={index} className="flex items-center justify-between p-3 bg-bg-primary rounded-lg border border-border">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">
                      {hotspot.file_path}
                    </p>
                    <p className="text-xs text-text-muted mt-1">{hotspot.reason}</p>
                  </div>
                  <div className="ml-3 flex items-center gap-2">
                    <span className="text-xs font-medium text-accent-red">
                      {Math.round(hotspot.health_score * 100)}%
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="bg-bg-secondary border border-border rounded-xl p-4">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <GitBranch className="w-5 h-5 text-accent-violet" />
          Dependency Overview
        </h2>
        <div className="h-64 flex items-center justify-center text-text-muted">
          <button
            onClick={() => navigate("/graph")}
            className="text-accent-blue hover:underline"
          >
            View full knowledge graph →
          </button>
        </div>
      </div>
      </div>
      </div>
    </div>
  );
}
