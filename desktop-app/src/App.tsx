import { useState, createContext, useContext } from 'react';
import GraphDashboard from './views/GraphDashboard';
import { SettingsProvider } from './context/SettingsContext';
import SettingsPane from './components/SettingsPane';

// Project Context
interface ProjectContextType {
    projectPath: string | null;
    projectName: string | null;
    isValid: boolean;
    setProject: (path: string, name: string, isValid: boolean) => void;
    clearProject: () => void;
}

export const ProjectContext = createContext<ProjectContextType>({
    projectPath: null,
    projectName: null,
    isValid: false,
    setProject: () => { },
    clearProject: () => { },
});

export const useProject = () => useContext(ProjectContext);

function AppContent() {
    const { projectPath, projectName, clearProject, setProject } = useProject();
    const [isSettingsOpen, setIsSettingsOpen] = useState(false);

    const onSelectClick = async () => {
        try {
            const result = await window.cgctl.selectDirectory();
            if (result) {
                const name = result.path.split('/').pop() || 'Unknown';
                setProject(result.path, name, result.isValid);
            }
        } catch (error) {
            console.error('Failed to select directory:', error);
        }
    };

    return (
        <div className="app-container">
            {!projectPath ? (
                <div className="landing-page">
                    <div className="landing-content">
                        <h1 className="logo-title">CodeGuardian</h1>
                        <p className="subtitle">Select a project directory to begin analysis</p>
                        <button className="select-btn" onClick={onSelectClick}>
                            📂 Open Project
                        </button>
                    </div>
                </div>
            ) : (
                <div className="dashboard-container">
                    <div className="floating-header">
                        <span className="project-name">{projectName}</span>
                        <button
                            className="config-btn"
                            onClick={() => setIsSettingsOpen(true)}
                            title="Settings"
                        >
                            ⚙️
                        </button>
                        <button className="close-project-btn" onClick={clearProject}>×</button>
                    </div>
                    <GraphDashboard />
                    <SettingsPane
                        isOpen={isSettingsOpen}
                        onClose={() => setIsSettingsOpen(false)}
                    />
                </div>
            )}
        </div>
    );
}

export default function App() {
    const [projectPath, setProjectPath] = useState<string | null>(null);
    const [projectName, setProjectName] = useState<string | null>(null);
    const [isValid, setIsValid] = useState(false);

    const setProject = (path: string, name: string, valid: boolean) => {
        setProjectPath(path);
        setProjectName(name);
        setIsValid(valid);

        if (!valid) {
            window.cgctl.initProject(path, name).then((res) => {
                if (res.success) {
                    setIsValid(true);
                }
            });
        }
    };

    const clearProject = () => {
        setProjectPath(null);
        setProjectName(null);
        setIsValid(false);
    };

    return (
        <ProjectContext.Provider value={{ projectPath, projectName, isValid, setProject, clearProject }}>
            <SettingsProvider>
                <AppContent />
            </SettingsProvider>
        </ProjectContext.Provider>
    );
}
