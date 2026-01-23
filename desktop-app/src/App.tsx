import { useState, createContext, useContext } from 'react';
import GraphDashboard from './views/GraphDashboard';

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

function App() {
    const [projectPath, setProjectPath] = useState<string | null>(null);
    const [projectName, setProjectName] = useState<string | null>(null);
    const [isValid, setIsValid] = useState(false);

    const setProject = (path: string, name: string, valid: boolean) => {
        setProjectPath(path);
        setProjectName(name);
        setIsValid(valid);

        // Auto-init logic if needed, but per requirements we just load it
        // If the project needs init (valid=false), we might want to prompt, 
        // but the prompt says "selecting which will automatically load and initialise that directory (via cgctl)"
        if (!valid) {
            // We should probably init it.
            window.cgctl.initProject(path, name).then((res) => {
                if (res.success) {
                    setIsValid(true);
                    // Indexing should happen too? Maybe let user do it or do it in background?
                    // Prompt says "load and initialise".
                    // Let's assume init makes it valid.
                }
            });
        }
    };

    const clearProject = () => {
        setProjectPath(null);
        setProjectName(null);
        setIsValid(false);
    };

    const handleSelectProject = async () => {
        try {
            const result = await window.cgctl.selectDirectory();
            if (result) {
                const name = result.path.split('/').pop() || 'Unknown';
                // We set it immediately, validation/init happens in background or we optimize
                setProject(result.path, name, result.isValid);
            }
        } catch (error) {
            console.error('Failed to select directory:', error);
        }
    };

    return (
        <ProjectContext.Provider value={{ projectPath, projectName, isValid, setProject, clearProject }}>
            <div className="app-container">
                {!projectPath ? (
                    <div className="landing-page">
                        <div className="landing-content">
                            <h1 className="logo-title">CodeGuardian</h1>
                            <p className="subtitle">Select a project directory to begin analysis</p>
                            <button className="select-btn" onClick={handleSelectProject}>
                                📂 Open Project
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="dashboard-container">
                        {/* We could have a floating back button or header if needed, but requirements say "purely the force directed animated graph" */}
                        <div className="floating-header">
                            <span className="project-name">{projectName}</span>
                            <button className="close-project-btn" onClick={clearProject}>×</button>
                        </div>
                        <GraphDashboard />
                    </div>
                )}
            </div>
        </ProjectContext.Provider>
    );
}

export default App;
