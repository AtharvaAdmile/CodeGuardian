/// <reference types="vite/client" />

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
        listFiles: (dirPath: string, extensions?: string[]) => Promise<{ path: string; name: string; size: number; type: 'file' | 'directory' }[]>;
        readFile: (filePath: string) => Promise<string>;
        // Test Generation & Execution
        generateTestCase: (projectPath: string, filePath: string, fileContent: string) => Promise<any>;
        saveTestFile: (projectPath: string, sourceFilePath: string, testCode: string) => Promise<any>;
        runLocalTest: (projectPath: string, testFilePath: string) => Promise<any>;
        testFileExists: (projectPath: string, sourceFilePath: string) => Promise<any>;
        updateApiKey: (projectPath: string, apiKey: string) => Promise<{ success: boolean; error?: string }>;
    };
}
