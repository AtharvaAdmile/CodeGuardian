import { useState, useCallback, createContext, useContext, Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useProject } from "./hooks/useProject";
import { Sidebar } from "./components/layout/Sidebar";
import { TopBar } from "./components/layout/TopBar";
import { CommandPalette } from "./components/layout/CommandPalette";
import { LoadingSpinner } from "./components/shared/LoadingSpinner";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const QnA = lazy(() => import("./pages/QnA"));
const KnowledgeGraph = lazy(() => import("./pages/KnowledgeGraph"));
const ImpactAnalyzer = lazy(() => import("./pages/ImpactAnalyzer"));
const Onboarding = lazy(() => import("./pages/Onboarding"));
const CodeReview = lazy(() => import("./pages/CodeReview"));
const FileExplorer = lazy(() => import("./pages/FileExplorer"));
const Indexing = lazy(() => import("./pages/Indexing"));
const Settings = lazy(() => import("./pages/Settings"));

interface ProjectContextType {
  projectPath: string | null;
  projectName: string | null;
  isValid: boolean;
  indexJobId: string | null;
  indexStatus: import("./lib/types").IndexStatus | null;
  healthStatus: import("./lib/types").HealthStatus | null;
  isLoadingHealth: boolean;
  setProject: (path: string, name: string, isValid: boolean) => void;
  clearProject: () => void;
}

const ProjectContext = createContext<ProjectContextType>({
  projectPath: null,
  projectName: null,
  isValid: false,
  indexJobId: null,
  indexStatus: null,
  healthStatus: null,
  isLoadingHealth: false,
  setProject: () => {},
  clearProject: () => {},
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
    <div className="flex-1 flex items-center justify-center bg-bg-primary">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-accent-blue to-text-secondary bg-clip-text text-transparent">
          CodeGuardian
        </h1>
        <p className="text-text-secondary mb-8">Select a project directory to begin analysis</p>
        <button
          onClick={onSelectProject}
          className="px-6 py-3 bg-accent-blue hover:bg-accent-blue/80 text-white rounded-lg font-medium transition-colors"
        >
          Open Project
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

  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);

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
          setProject,
          clearProject,
        }}
      >
        <div className="flex h-screen bg-bg-primary">
          <Sidebar healthStatus={healthStatus} />
          <div className="flex-1 flex flex-col overflow-hidden">
            <TopBar
              projectName={projectName}
              healthStatus={healthStatus}
              indexStatus={indexStatus}
              onCommandPaletteOpen={handleCommandPaletteOpen}
              onClearProject={handleClearProject}
            />
            <main className="flex-1 overflow-auto">
              <Suspense fallback={<LoadingPage />}>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/ask" element={<QnA />} />
                  <Route path="/graph" element={<KnowledgeGraph />} />
                  <Route path="/impact" element={<ImpactAnalyzer />} />
                  <Route path="/onboard" element={<Onboarding />} />
                  <Route path="/review" element={<CodeReview />} />
                  <Route path="/files" element={<FileExplorer />} />
                  <Route path="/indexing" element={<Indexing />} />
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
        </div>
      </ProjectContext.Provider>
    </BrowserRouter>
  );
}

export default function App() {
  return <AppContent />;
}
