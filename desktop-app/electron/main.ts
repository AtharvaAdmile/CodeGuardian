import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import { spawn, exec } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

// Path to cgctl - try global first, fallback to project venv
const CGCTL_PATH = process.env.CGCTL_PATH || 'cgctl';

let mainWindow: BrowserWindow | null = null;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        minWidth: 1000,
        minHeight: 700,
        backgroundColor: '#0d1117',
        titleBarStyle: 'hiddenInset',
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js'),
        },
    });

    // In development, load from Vite dev server
    if (process.env.NODE_ENV === 'development' || !app.isPackaged) {
        mainWindow.loadURL('http://localhost:5173');
        mainWindow.webContents.openDevTools();
    } else {
        mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
    }

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// Execute cgctl command and return JSON output
function executeCgctl(command: string, args: string[], cwd?: string): Promise<any> {
    return new Promise((resolve, reject) => {
        const fullArgs = [command, ...args];

        // Add --json flag if command supports it
        if (['ask'].includes(command)) {
            fullArgs.push('--json');
        }

        console.log(`Executing: ${CGCTL_PATH} ${fullArgs.join(' ')}`);

        const proc = spawn(CGCTL_PATH, fullArgs, {
            cwd: cwd || process.cwd(),
            env: { ...process.env },
            shell: true,
        });

        let stdout = '';
        let stderr = '';

        proc.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        proc.stderr.on('data', (data) => {
            stderr += data.toString();
        });

        proc.on('close', (code) => {
            if (code === 0) {
                // Try to parse as JSON, otherwise return raw output
                try {
                    resolve(JSON.parse(stdout));
                } catch {
                    resolve({ output: stdout, raw: true });
                }
            } else {
                reject(new Error(stderr || `Command failed with code ${code}`));
            }
        });

        proc.on('error', (err) => {
            reject(err);
        });
    });
}

// Execute Python MCP tool directly for commands not in CLI
function executeMcpTool(toolName: string, args: Record<string, any>, projectPath: string): Promise<any> {
    return new Promise((resolve, reject) => {
        const pythonScript = `
import sys
import os
import json

# Set project path
os.chdir('${projectPath}')

# Import the tool
from src.mcp_server import ${toolName}

# Execute with args
result = ${toolName}(${Object.entries(args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})
print(json.dumps(result))
`;

        const backendPath = path.resolve(__dirname, '../../');
        const proc = spawn('python3', ['-c', pythonScript], {
            cwd: projectPath,
            env: { ...process.env, PYTHONPATH: backendPath },
        });

        let stdout = '';
        let stderr = '';

        proc.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        proc.stderr.on('data', (data) => {
            stderr += data.toString();
        });

        proc.on('close', (code) => {
            if (code === 0) {
                try {
                    resolve(JSON.parse(stdout));
                } catch {
                    resolve({ output: stdout, raw: true });
                }
            } else {
                reject(new Error(stderr || `Tool failed with code ${code}`));
            }
        });

        proc.on('error', (err) => {
            reject(err);
        });
    });
}

// IPC Handlers
app.whenReady().then(() => {
    createWindow();

    // Select project directory
    ipcMain.handle('dialog:selectDirectory', async () => {
        const result = await dialog.showOpenDialog(mainWindow!, {
            properties: ['openDirectory'],
            title: 'Select CodeGuardian Project',
        });

        if (!result.canceled && result.filePaths.length > 0) {
            const projectPath = result.filePaths[0];
            // Check if it's a valid CodeGuardian project
            const configPath = path.join(projectPath, '.codeguardian');
            const isValid = fs.existsSync(configPath);
            return { path: projectPath, isValid };
        }
        return null;
    });

    // Initialize project with cgctl init
    ipcMain.handle('cgctl:init', async (_, projectPath: string, projectName?: string) => {
        return new Promise((resolve, reject) => {
            const args = [projectPath];
            if (projectName) {
                args.push('--name', projectName);
            }

            console.log(`Executing: cgctl init ${args.join(' ')}`);

            const proc = spawn('cgctl', ['init', ...args], {
                cwd: projectPath,
                env: { ...process.env },
                shell: true,
            });

            let stdout = '';
            let stderr = '';

            proc.stdout.on('data', (data) => {
                stdout += data.toString();
            });

            proc.stderr.on('data', (data) => {
                stderr += data.toString();
            });

            proc.on('close', (code) => {
                if (code === 0) {
                    resolve({ success: true, output: stdout });
                } else {
                    resolve({ success: false, error: stderr || stdout });
                }
            });

            proc.on('error', (err) => {
                resolve({ success: false, error: err.message });
            });
        });
    });

    // Index project with cgctl index
    ipcMain.handle('cgctl:index', async (_, projectPath: string, force?: boolean) => {
        return new Promise((resolve, reject) => {
            const args = [projectPath];
            if (force) {
                args.push('--force');
            }

            console.log(`Executing: cgctl index ${args.join(' ')}`);

            const proc = spawn('cgctl', ['index', ...args], {
                cwd: projectPath,
                env: { ...process.env },
                shell: true,
            });

            let stdout = '';
            let stderr = '';

            proc.stdout.on('data', (data) => {
                stdout += data.toString();
            });

            proc.stderr.on('data', (data) => {
                stderr += data.toString();
            });

            proc.on('close', (code) => {
                if (code === 0) {
                    resolve({ success: true, output: stdout });
                } else {
                    resolve({ success: false, error: stderr || stdout });
                }
            });

            proc.on('error', (err) => {
                resolve({ success: false, error: err.message });
            });
        });
    });

    // Analyze structure
    ipcMain.handle('cgctl:analyzeStructure', async (_, projectPath: string) => {
        return executeMcpTool('analyze_structure', { project_path: projectPath }, projectPath);
    });

    // Get runtime stats
    ipcMain.handle('cgctl:getRuntimeStats', async (_, projectPath: string, filePath: string) => {
        return executeMcpTool('get_runtime_stats', { file_path: filePath }, projectPath);
    });

    // Get file health
    ipcMain.handle('cgctl:getFileHealth', async (_, projectPath: string, filePath: string) => {
        return executeMcpTool('get_file_health', { file_path: filePath }, projectPath);
    });

    // Check compliance (Standard)
    ipcMain.handle('cgctl:checkCompliance', async (_, projectPath: string, codeSnippet: string) => {
        return executeMcpTool('check_compliance', { code_snippet: codeSnippet }, projectPath);
    });

    // Check compliance (Regulatory/Medical)
    ipcMain.handle('cgctl:checkRegulatoryCompliance', async (_, projectPath: string, filePath: string, fileContent: string) => {
        return executeMcpTool('check_regulatory_compliance', { file_path: filePath, file_content: fileContent }, projectPath);
    });

    // Get file expert
    ipcMain.handle('cgctl:getFileExpert', async (_, projectPath: string, filePath: string) => {
        return executeMcpTool('get_file_expert', { file_path: filePath }, projectPath);
    });

    // Get file history
    ipcMain.handle('cgctl:getFileHistory', async (_, projectPath: string, filePath: string, lineStart?: number, lineEnd?: number) => {
        const args: Record<string, any> = { file_path: filePath };
        if (lineStart) args.line_start = lineStart;
        if (lineEnd) args.line_end = lineEnd;
        return executeMcpTool('get_file_history', args, projectPath);
    });

    // Find dependencies
    ipcMain.handle('cgctl:findDependencies', async (_, projectPath: string, filePath: string) => {
        return executeMcpTool('find_dependencies', { file_path: filePath }, projectPath);
    });

    // Analyze project dependencies (Bulk)
    ipcMain.handle('cgctl:analyzeProjectDependencies', async (_, projectPath: string) => {
        return executeMcpTool('analyze_project_dependencies', { project_path: projectPath }, projectPath);
    });

    // Detect documentation gaps
    ipcMain.handle('cgctl:detectDocumentationGaps', async (_, projectPath: string, filePath: string) => {
        return executeMcpTool('detect_documentation_gaps', { file_path: filePath }, projectPath);
    });

    // Analyze testability
    ipcMain.handle('cgctl:analyzeTestability', async (_, projectPath: string, filePath: string) => {
        return executeMcpTool('analyze_testability', { file_path: filePath }, projectPath);
    });

    // Query codebase
    ipcMain.handle('cgctl:queryCodebase', async (_, projectPath: string, query: string, nResults: number = 5) => {
        return executeMcpTool('query_codebase', { query, n_results: nResults }, projectPath);
    });

    // Run tests
    ipcMain.handle('cgctl:runTests', async (_, projectPath: string, filePath?: string, testDir?: string) => {
        const args: Record<string, any> = {};
        if (filePath) args.file_path = filePath;
        if (testDir) args.test_dir = testDir;
        return executeMcpTool('run_tests', args, projectPath);
    });

    // List files in directory
    ipcMain.handle('fs:listFiles', async (_, dirPath: string, extensions: string[] | null = null) => {
        const files: { path: string; name: string; size: number; type: 'file' | 'directory' }[] = [];

        function walkDir(dir: string) {
            try {
                const items = fs.readdirSync(dir);
                for (const item of items) {
                    if (item.startsWith('.') || item === 'node_modules' || item === 'venv' || item === '__pycache__' || item === 'dist' || item === 'build' || item === 'coverage') continue;

                    const fullPath = path.join(dir, item);
                    const stat = fs.statSync(fullPath);
                    const relativePath = path.relative(dirPath, fullPath);

                    if (stat.isDirectory()) {
                        files.push({
                            path: relativePath,
                            name: item,
                            size: 0,
                            type: 'directory'
                        });
                        walkDir(fullPath);
                    } else {
                        if (extensions && extensions.length > 0) {
                            if (!extensions.some(ext => item.endsWith(ext))) continue;
                        }

                        files.push({
                            path: relativePath,
                            name: item,
                            size: stat.size,
                            type: 'file'
                        });
                    }
                }
            } catch (e) {
                // Ignore permission errors
            }
        }

        walkDir(dirPath);
        return files;
    });

    // Read file content
    ipcMain.handle('fs:readFile', async (_, filePath: string) => {
        return fs.readFileSync(filePath, 'utf-8');
    });

    // Generate test case using AI
    ipcMain.handle('cgctl:generateTestCase', async (_, projectPath: string, filePath: string, fileContent: string) => {
        return executeMcpTool('generate_unit_test', {
            file_path: filePath,
            file_content: fileContent
        }, projectPath);
    });

    // Save test file to generated_test_cases directory
    ipcMain.handle('fs:saveTestFile', async (_, projectPath: string, sourceFilePath: string, testCode: string) => {
        try {
            const sourcePath = path.parse(sourceFilePath);
            const sourceExt = sourcePath.ext.toLowerCase();

            // Determine test file name based on language
            let testFileName: string;
            if (sourceExt === '.py') {
                testFileName = `test_${sourcePath.name}.py`;
            } else {
                // JS/TS uses .test.ext format
                testFileName = `${sourcePath.name}.test${sourceExt}`;
            }

            // Build the mirrored path structure
            const testDir = path.join(projectPath, 'generated_test_cases', sourcePath.dir);
            const testFilePath = path.join(testDir, testFileName);

            // Create directory if it doesn't exist
            if (!fs.existsSync(testDir)) {
                fs.mkdirSync(testDir, { recursive: true });
            }

            // Write the test file
            fs.writeFileSync(testFilePath, testCode, 'utf-8');

            console.log(`Test file saved to: ${testFilePath}`);

            return {
                success: true,
                path: testFilePath,
                relativePath: path.relative(projectPath, testFilePath)
            };
        } catch (error: any) {
            console.error('Error saving test file:', error);
            return {
                success: false,
                error: error.message
            };
        }
    });

    // Run a local test file
    ipcMain.handle('cgctl:runLocalTest', async (_, projectPath: string, testFilePath: string) => {
        return executeMcpTool('run_generated_test', {
            test_file_path: testFilePath,
            project_path: projectPath
        }, projectPath);
    });

    // Check if test file exists
    ipcMain.handle('fs:testFileExists', async (_, projectPath: string, sourceFilePath: string) => {
        try {
            const sourcePath = path.parse(sourceFilePath);
            const sourceExt = sourcePath.ext.toLowerCase();

            let testFileName: string;
            if (sourceExt === '.py') {
                testFileName = `test_${sourcePath.name}.py`;
            } else {
                testFileName = `${sourcePath.name}.test${sourceExt}`;
            }

            const testFilePath = path.join(projectPath, 'generated_test_cases', sourcePath.dir, testFileName);

            if (fs.existsSync(testFilePath)) {
                const content = fs.readFileSync(testFilePath, 'utf-8');
                return {
                    exists: true,
                    path: testFilePath,
                    relativePath: path.relative(projectPath, testFilePath),
                    content: content
                };
            }

            return { exists: false };
        } catch (error) {
            return { exists: false };
        }
    });

    // Update Gemini API Key in .env
    ipcMain.handle('cgctl:updateApiKey', async (_, projectPath: string, apiKey: string) => {
        try {
            const envPath = path.join(projectPath, '.env');
            let content = '';

            if (fs.existsSync(envPath)) {
                content = fs.readFileSync(envPath, 'utf-8');
                if (content.includes('GOOGLE_API_KEY=')) {
                    content = content.replace(/GOOGLE_API_KEY=.*/, `GOOGLE_API_KEY=${apiKey}`);
                } else {
                    content += `\nGOOGLE_API_KEY=${apiKey}\n`;
                }
            } else {
                content = `GOOGLE_API_KEY=${apiKey}\n`;
            }

            fs.writeFileSync(envPath, content, 'utf-8');
            console.log(`API Key updated in ${envPath}`);
            return { success: true };
        } catch (error: any) {
            console.error('Error updating API Key:', error);
            return { success: false, error: error.message };
        }
    });

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});
