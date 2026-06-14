import { useState, useCallback, useEffect, createContext, useContext, Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useProject } from "./hooks/useProject";
import { Sidebar } from "./components/layout/Sidebar";
import { TopBar } from "./components/layout/TopBar";
import { StatusBar } from "./components/layout/StatusBar";
import { CommandPalette } from "./components/layout/CommandPalette";
import { LoadingSpinner } from "./components/shared/LoadingSpinner";
import { CGPilot } from "./components/CGPilot";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const KnowledgeGraph = lazy(() => import("./pages/KnowledgeGraph"));
const CommitReview = lazy(() => import("./pages/CommitReview"));
const FileExplorer = lazy(() => import("./pages/FileExplorer"));
const Indexing = lazy(() => import("./pages/Indexing"));
const Compliance = lazy(() => import("./pages/Compliance"));
const Settings = lazy(() => import("./pages/Settings"));

interface ProjectContextType {
  projectPath: string | null;
  projectName: string | null;
  isValid: boolean;
  indexJobId: string | null;
  indexStatus: import("./lib/types").IndexStatus | null;
  healthStatus: import("./lib/types").HealthStatus | null;
  isLoadingHealth: boolean;
  selectedFilePath: string | null;
  setProject: (path: string, name: string, isValid: boolean) => void;
  clearProject: () => void;
  setSelectedFilePath: (path: string | null) => void;
}

const ProjectContext = createContext<ProjectContextType>({
  projectPath: null,
  projectName: null,
  isValid: false,
  indexJobId: null,
  indexStatus: null,
  healthStatus: null,
  isLoadingHealth: false,
  selectedFilePath: null,
  setProject: () => {},
  clearProject: () => {},
  setSelectedFilePath: () => {},
});

export const useProjectContext = () => useContext(ProjectContext);

function LoadingPage() {
  return (
    <div className="flex items-center justify-center h-full">
      <LoadingSpinner size="lg" />
    </div>
  );
}

function LandingPage({ onSelectProject }: { onSelectProject: () => void }) {
  return (
    <div className="h-screen flex items-center justify-center bg-bg-primary">
      <div className="text-center space-y-6 px-8">
        <pre className="text-accent-green text-xs leading-tight glow-strong select-none">
{`  ██████╗ ██████╗  ██████╗ ███████╗
 ██╔════╝██╔════╝ ██╔════╝ ██╔════╝
 ██║     ██║  ███╗██║  ███╗███████╗
 ██║     ██║   ██║██║   ██║╚════██║
 ╚██████╗╚██████╔╝╚██████╔╝███████║
  ╚═════╝ ╚═════╝  ╚═════╝ ╚══════╝`}
        </pre>
        <div className="text-text-secondary text-xs uppercase tracking-widest">
          INSTITUTIONAL MEMORY SYSTEM v1.0.0
        </div>
        <div className="border border-border p-4 text-left text-sm space-y-1 max-w-sm mx-auto">
          <div className="text-text-muted">// SYSTEM READY</div>
          <div className="text-text-secondary">$ awaiting project path...</div>
          <div className="flex items-center gap-2 text-accent-green">
            <span>&gt;</span>
            <span className="cursor-block">SELECT DIRECTORY TO INITIALIZE</span>
          </div>
        </div>
        <button
          onClick={onSelectProject}
          className="px-6 py-2.5 border border-accent-green text-accent-green hover:bg-accent-green hover:text-bg-primary transition-colors text-sm uppercase tracking-widest hover-glitch"
        >
          [ OPEN PROJECT ]
        </button>
      </div>
    </div>
  );
}

function AppContent() {
  const {
    projectPath,
    projectName,
    isValid,
    indexJobId,
    indexStatus,
    healthStatus,
    isLoadingHealth,
    setProject,
    clearProject,
  } = useProject();

  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [pendingSessionId, setPendingSessionId] = useState<string | null>(null);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);

  useEffect(() => {
    function handler(event: CustomEvent) {
      setPendingSessionId(event.detail);
    }
    window.addEventListener("cg-open-session", handler as EventListener);
    return () => window.removeEventListener("cg-open-session", handler as EventListener);
  }, []);

  const handleSelectClick = useCallback(async () => {
    try {
      const result = await window.cgctl.selectDirectory();
      if (result) {
        const name = result.path.split("/").pop() || "Unknown";
        setProject(result.path, name, result.isValid);
      }
    } catch (error) {
      console.error("Failed to select directory:", error);
    }
  }, [setProject]);

  const handleCommandPaletteOpen = useCallback(() => {
    setIsCommandPaletteOpen(true);
  }, []);

  const handleClearProject = useCallback(() => {
    clearProject();
  }, [clearProject]);

  if (!projectPath) {
    return (
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <div id="crt-overlay" aria-hidden="true" />
        <LandingPage onSelectProject={handleSelectClick} />
      </BrowserRouter>
    );
  }

  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ProjectContext.Provider
        value={{
          projectPath,
          projectName,
          isValid,
          indexJobId,
          indexStatus,
          healthStatus,
          isLoadingHealth,
          selectedFilePath,
          setProject,
          clearProject,
          setSelectedFilePath,
        }}
      >
        <div id="crt-overlay" aria-hidden="true" />
        <div className="scanline-effect" aria-hidden="true" />
        <div className="flex h-screen bg-surface">
          <Sidebar healthStatus={healthStatus} onClearProject={handleClearProject} />
          <div className="flex-1 flex flex-col overflow-hidden">
            <TopBar
              projectName={projectName}
              healthStatus={healthStatus}
              indexStatus={indexStatus}
              onCommandPaletteOpen={handleCommandPaletteOpen}
              onClearProject={handleClearProject}
            />
            <main className="flex-1 overflow-auto pb-7">
              <Suspense fallback={<LoadingPage />}>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/graph" element={<KnowledgeGraph />} />
                  <Route path="/impact" element={<Navigate to="/files" replace />} />
                  <Route path="/review" element={<CommitReview />} />
                  <Route path="/files" element={<FileExplorer />} />
                  <Route path="/indexing" element={<Indexing />} />
                  <Route path="/compliance" element={<Compliance />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Suspense>
            </main>
          </div>
          <CommandPalette
            isOpen={isCommandPaletteOpen}
            onClose={() => setIsCommandPaletteOpen(false)}
          />
          {projectName && projectPath && (
            <CGPilot
              projectId={projectName}
              projectPath={projectPath}
              indexStatus={indexStatus?.status}
              pendingSessionId={pendingSessionId}
              onClearPendingSession={() => setPendingSessionId(null)}
            />
          )}
          <StatusBar
            projectName={projectName}
            isIndexing={indexStatus?.status === "running"}
          />
        </div>
      </ProjectContext.Provider>
    </BrowserRouter>
  );
}

export default function App() {
  return <AppContent />;
}
