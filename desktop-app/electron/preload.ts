import { contextBridge, ipcRenderer } from 'electron';

// Expose protected methods to renderer process
contextBridge.exposeInMainWorld('cgctl', {
    // Dialog
    selectDirectory: () => ipcRenderer.invoke('dialog:selectDirectory'),

    // Project management
    initProject: (projectPath: string, projectName?: string) =>
        ipcRenderer.invoke('cgctl:init', projectPath, projectName),

    indexProject: (projectPath: string, force?: boolean) =>
        ipcRenderer.invoke('cgctl:index', projectPath, force),

    // Analysis tools
    analyzeStructure: (projectPath: string) =>
        ipcRenderer.invoke('cgctl:analyzeStructure', projectPath),

    getRuntimeStats: (projectPath: string, filePath: string) =>
        ipcRenderer.invoke('cgctl:getRuntimeStats', projectPath, filePath),

    getFileHealth: (projectPath: string, filePath: string) =>
        ipcRenderer.invoke('cgctl:getFileHealth', projectPath, filePath),

    checkCompliance: (projectPath: string, codeSnippet: string) =>
        ipcRenderer.invoke('cgctl:checkCompliance', projectPath, codeSnippet),

    checkRegulatoryCompliance: (projectPath: string, filePath: string, fileContent: string) =>
        ipcRenderer.invoke('cgctl:checkRegulatoryCompliance', projectPath, filePath, fileContent),

    getFileExpert: (projectPath: string, filePath: string) =>
        ipcRenderer.invoke('cgctl:getFileExpert', projectPath, filePath),

    getFileHistory: (projectPath: string, filePath: string, lineStart?: number, lineEnd?: number) =>
        ipcRenderer.invoke('cgctl:getFileHistory', projectPath, filePath, lineStart, lineEnd),

    findDependencies: (projectPath: string, filePath: string) =>
        ipcRenderer.invoke('cgctl:findDependencies', projectPath, filePath),

    analyzeProjectDependencies: (projectPath: string) =>
        ipcRenderer.invoke('cgctl:analyzeProjectDependencies', projectPath),

    detectDocumentationGaps: (projectPath: string, filePath: string) =>
        ipcRenderer.invoke('cgctl:detectDocumentationGaps', projectPath, filePath),

    analyzeTestability: (projectPath: string, filePath: string) =>
        ipcRenderer.invoke('cgctl:analyzeTestability', projectPath, filePath),

    queryCodebase: (projectPath: string, query: string, nResults?: number) =>
        ipcRenderer.invoke('cgctl:queryCodebase', projectPath, query, nResults),

    runTests: (projectPath: string, filePath?: string, testDir?: string) =>
        ipcRenderer.invoke('cgctl:runTests', projectPath, filePath, testDir),

    // File system
    listFiles: (dirPath: string, extensions?: string[]) =>
        ipcRenderer.invoke('fs:listFiles', dirPath, extensions),

    readFile: (filePath: string) =>
        ipcRenderer.invoke('fs:readFile', filePath),

    // Test Generation & Execution
    generateTestCase: (projectPath: string, filePath: string, fileContent: string) =>
        ipcRenderer.invoke('cgctl:generateTestCase', projectPath, filePath, fileContent),

    saveTestFile: (projectPath: string, sourceFilePath: string, testCode: string) =>
        ipcRenderer.invoke('fs:saveTestFile', projectPath, sourceFilePath, testCode),

    runLocalTest: (projectPath: string, testFilePath: string) =>
        ipcRenderer.invoke('cgctl:runLocalTest', projectPath, testFilePath),

    testFileExists: (projectPath: string, sourceFilePath: string) =>
        ipcRenderer.invoke('fs:testFileExists', projectPath, sourceFilePath),

    updateApiKey: (projectPath: string, apiKey: string) =>
        ipcRenderer.invoke('cgctl:updateApiKey', projectPath, apiKey),
});

// Type definitions for the exposed API
declare global {
    interface Window {
        cgctl: {
            selectDirectory: () => Promise<{ path: string; isValid: boolean } | null>;
            initProject: (projectPath: string, projectName?: string) => Promise<{ success: boolean; output?: string; error?: string }>;
            indexProject: (projectPath: string, force?: boolean) => Promise<{ success: boolean; output?: string; error?: string }>;
            analyzeStructure: (projectPath: string) => Promise<any>;
            getRuntimeStats: (projectPath: string, filePath: string) => Promise<any>;
            getFileHealth: (projectPath: string, filePath: string) => Promise<any>;
            checkCompliance: (projectPath: string, codeSnippet: string) => Promise<any>;
            checkRegulatoryCompliance: (projectPath: string, filePath: string, fileContent: string) => Promise<any>;
            getFileExpert: (projectPath: string, filePath: string) => Promise<any>;
            getFileHistory: (projectPath: string, filePath: string, lineStart?: number, lineEnd?: number) => Promise<any>;
            findDependencies: (projectPath: string, filePath: string) => Promise<any>;
            analyzeProjectDependencies: (projectPath: string) => Promise<any>;
            detectDocumentationGaps: (projectPath: string, filePath: string) => Promise<any>;
            analyzeTestability: (projectPath: string, filePath: string) => Promise<any>;
            queryCodebase: (projectPath: string, query: string, nResults?: number) => Promise<any>;
            runTests: (projectPath: string, filePath?: string, testDir?: string) => Promise<any>;
            listFiles: (dirPath: string, extensions?: string[]) => Promise<any>;
            readFile: (filePath: string) => Promise<string>;
            // Test Generation & Execution
            generateTestCase: (projectPath: string, filePath: string, fileContent: string) => Promise<any>;
            saveTestFile: (projectPath: string, sourceFilePath: string, testCode: string) => Promise<any>;
            runLocalTest: (projectPath: string, testFilePath: string) => Promise<any>;
            testFileExists: (projectPath: string, sourceFilePath: string) => Promise<any>;
            updateApiKey: (projectPath: string, apiKey: string) => Promise<{ success: boolean; error?: string }>;
        };
    }
}
