import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import * as http from 'http';

// ─── Constants ──────────────────────────────────────────────────────────────

const PYTHON_PATH = '/opt/miniconda3/bin/python';
const SERVER_PORT = 8742;
const SERVER_BASE = `http://localhost:${SERVER_PORT}`;
const HEALTH_POLL_MS = 500;
const HEALTH_TIMEOUT_MS = 60_000;
const REQUEST_TIMEOUT_MS = 30_000;

// ─── State ──────────────────────────────────────────────────────────────────

let mainWindow: BrowserWindow | null = null;
let serverProcess: ChildProcess | null = null;
let isQuitting = false;

// ─── Server Lifecycle ───────────────────────────────────────────────────────

function startServer(): ChildProcess {
    const backendPath = path.resolve(__dirname, '../../');

    const proc = spawn(
        PYTHON_PATH,
        ['-m', 'uvicorn', 'server.app:create_app', '--factory', '--host', '0.0.0.0', '--port', String(SERVER_PORT)],
        {
            cwd: backendPath,
            env: { ...process.env, PYTHONPATH: backendPath },
            stdio: ['ignore', 'pipe', 'pipe'],
        }
    );

    proc.stdout?.on('data', (data) => {
        console.log(`[server] ${data.toString().trimEnd()}`);
    });

    proc.stderr?.on('data', (data) => {
        console.error(`[server] ${data.toString().trimEnd()}`);
    });

    proc.on('exit', (code, signal) => {
        console.error(`[server] exited  code=${code}  signal=${signal}`);
        // Only show crash dialog if we didn't intentionally kill it
        if (serverProcess !== null && !isQuitting) {
            const choice = dialog.showMessageBoxSync({
                type: 'error',
                title: 'CodeGuardian Server Crashed',
                message: `The backend server exited unexpectedly (code ${code}).`,
                buttons: ['Restart Server', 'Quit'],
                defaultId: 0,
            });

            if (choice === 0) {
                serverProcess = startServer();
                waitForServer()
                    .then(() => console.log('[server] restarted successfully'))
                    .catch(() => {
                        dialog.showErrorBox(
                            'CodeGuardian',
                            'Failed to restart the backend server. The application will now quit.'
                        );
                        app.quit();
                    });
            } else {
                app.quit();
            }
        }
    });

    proc.on('error', (err) => {
        console.error(`[server] spawn error: ${err.message}`);
        dialog.showErrorBox(
            'CodeGuardian',
            `Failed to start the backend server:\n${err.message}`
        );
    });

    return proc;
}
async function waitForServer(): Promise<void> {
    const deadline = Date.now() + HEALTH_TIMEOUT_MS;

    while (Date.now() < deadline) {
        try {
            const res = await new Promise<http.IncomingMessage>((resolve, reject) => {
                const req = http.get('http://127.0.0.1:8742/api/health', (res) => {
                    resolve(res);
                });
                req.on('error', reject);
                req.setTimeout(2000, () => {
                    req.destroy();
                    reject(new Error('timeout'));
                });
            });
            // Accept any 2xx response - server is up even if "degraded"
            if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
                console.log('[server] healthy ✓');
                return;
            }
            console.log(`[server] health returned ${res.statusCode}, retrying...`);
        } catch (err: any) {
            // Server not ready yet — retry
            console.log(`[server] not ready: ${err.message}`);
        }
        await new Promise((r) => setTimeout(r, HEALTH_POLL_MS));
    }

    throw new Error(`Server did not become healthy within ${HEALTH_TIMEOUT_MS / 1000}s`);
}

function killServer(): void {
    if (serverProcess && !serverProcess.killed) {
        console.log('[server] sending SIGTERM');
        serverProcess.kill('SIGTERM');
        serverProcess = null;
    }
}

// ─── HTTP Helper ────────────────────────────────────────────────────────────

async function serverFetch<T = any>(
    method: 'GET' | 'POST',
    urlPath: string,
    body?: Record<string, any>
): Promise<T> {
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Request timeout')), REQUEST_TIMEOUT_MS);

        const options: http.RequestOptions = {
            hostname: '127.0.0.1',
            port: SERVER_PORT,
            path: urlPath,
            method,
            headers: { 'Content-Type': 'application/json' },
        };

        const req = http.request(options, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                clearTimeout(timeout);
                if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
                    try {
                        resolve(JSON.parse(data) as T);
                    } catch {
                        resolve(data as T);
                    }
                } else {
                    try {
                        const json = JSON.parse(data);
                        const detail = json?.detail ?? data;
                        reject(new Error(`HTTP ${res.statusCode}: ${detail}`));
                    } catch {
                        reject(new Error(`HTTP ${res.statusCode}: ${data}`));
                    }
                }
            });
        });

        req.on('error', (err) => {
            clearTimeout(timeout);
            reject(err);
        });

        if (body !== undefined) {
            req.write(JSON.stringify(body));
        }
        req.end();
    });
}

// ─── Window ─────────────────────────────────────────────────────────────────

function createWindow(): void {
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

    if (process.env.NODE_ENV === 'development' || !app.isPackaged) {
        mainWindow.loadURL('http://localhost:5173');
        // mainWindow.webContents.openDevTools();
    } else {
        mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
    }

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// ─── App Lifecycle ──────────────────────────────────────────────────────────

app.on('before-quit', () => {
    isQuitting = true;
    killServer();
});

app.whenReady().then(async () => {
    // 1. Start backend server
    console.log('[main] starting backend server …');
    serverProcess = startServer();

    try {
        await waitForServer();
    } catch (err: any) {
        dialog.showErrorBox(
            'CodeGuardian',
            `Backend server failed to start:\n${err.message}\n\nThe application will quit.`
        );
        app.quit();
        return;
    }

    // 2. Register IPC handlers
    registerIpcHandlers();

    // 3. Create window only after server is healthy
    createWindow();

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

// ─── IPC Handlers ───────────────────────────────────────────────────────────

function registerIpcHandlers(): void {
    // ── Dialog / Filesystem (local — no server needed) ──────────────

    ipcMain.handle('dialog:selectDirectory', async () => {
        const result = await dialog.showOpenDialog(mainWindow!, {
            properties: ['openDirectory'],
            title: 'Select CodeGuardian Project',
        });

        if (!result.canceled && result.filePaths.length > 0) {
            const projectPath = result.filePaths[0];
            const configPath = path.join(projectPath, '.codeguardian');
            const isValid = fs.existsSync(configPath);
            return { path: projectPath, isValid };
        }
        return null;
    });

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
                        files.push({ path: relativePath, name: item, size: 0, type: 'directory' });
                        walkDir(fullPath);
                    } else {
                        if (extensions && extensions.length > 0) {
                            if (!extensions.some(ext => item.endsWith(ext))) continue;
                        }
                        files.push({ path: relativePath, name: item, size: stat.size, type: 'file' });
                    }
                }
            } catch (e) {
                // Ignore permission errors
            }
        }

        walkDir(dirPath);
        return files;
    });

    ipcMain.handle('fs:readFile', async (_, filePath: string) => {
        return fs.readFileSync(filePath, 'utf-8');
    });

    ipcMain.handle('fs:saveTestFile', async (_, projectPath: string, sourceFilePath: string, testCode: string) => {
        try {
            const sourcePath = path.parse(sourceFilePath);
            const sourceExt = sourcePath.ext.toLowerCase();

            let testFileName: string;
            if (sourceExt === '.py') {
                testFileName = `test_${sourcePath.name}.py`;
            } else {
                testFileName = `${sourcePath.name}.test${sourceExt}`;
            }

            const testDir = path.join(projectPath, 'generated_test_cases', sourcePath.dir);
            const testFilePath = path.join(testDir, testFileName);

            if (!fs.existsSync(testDir)) {
                fs.mkdirSync(testDir, { recursive: true });
            }

            fs.writeFileSync(testFilePath, testCode, 'utf-8');
            console.log(`Test file saved to: ${testFilePath}`);

            return {
                success: true,
                path: testFilePath,
                relativePath: path.relative(projectPath, testFilePath),
            };
        } catch (error: any) {
            console.error('Error saving test file:', error);
            return { success: false, error: error.message };
        }
    });

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
                    content,
                };
            }

            return { exists: false };
        } catch (error) {
            return { exists: false };
        }
    });

    // ── HTTP-backed IPC Handlers (replacing spawn/executeMcpTool) ───

    // Initialize + index project
    ipcMain.handle('cgctl:init', async (_, projectPath: string, projectName?: string) => {
        try {
            const result = await serverFetch('POST', '/api/index', {
                project_id: projectName || path.basename(projectPath),
                project_path: projectPath,
                force: false,
            });
            return { success: true, output: JSON.stringify(result) };
        } catch (err: any) {
            return { success: false, error: err.message };
        }
    });

    // Index project
    ipcMain.handle('cgctl:index', async (_, projectPath: string, force?: boolean) => {
        try {
            const result = await serverFetch('POST', '/api/index', {
                project_id: path.basename(projectPath),
                project_path: projectPath,
                force: force ?? false,
            });
            return { success: true, output: JSON.stringify(result) };
        } catch (err: any) {
            return { success: false, error: err.message };
        }
    });

    // Analyze structure
    ipcMain.handle('cgctl:analyzeStructure', async (_, projectPath: string) => {
        return serverFetch('POST', '/api/analyze/structure', { project_path: projectPath });
    });

    // Get runtime stats
    ipcMain.handle('cgctl:getRuntimeStats', async (_, projectPath: string, filePath: string) => {
        return serverFetch('POST', '/api/analyze/runtime', {
            project_path: projectPath,
            file_path: filePath,
        });
    });

    // Get file health
    ipcMain.handle('cgctl:getFileHealth', async (_, projectPath: string, filePath: string) => {
        return serverFetch('POST', '/api/analyze/health', {
            project_path: projectPath,
            file_path: filePath,
        });
    });

    // Check compliance (standard)
    ipcMain.handle('cgctl:checkCompliance', async (_, projectPath: string, codeSnippet: string) => {
        return serverFetch('POST', '/api/analyze/compliance', {
            project_path: projectPath,
            code_snippet: codeSnippet,
        });
    });

    // Check compliance (regulatory/medical)
    ipcMain.handle('cgctl:checkRegulatoryCompliance', async (_, projectPath: string, filePath: string, fileContent: string) => {
        return serverFetch('POST', '/api/analyze/regulatory-compliance', {
            project_path: projectPath,
            file_path: filePath,
            file_content: fileContent,
        });
    });

    // Compliance scan API
    ipcMain.handle('cgctl:startComplianceScan', async (_, projectId: string, projectPath: string, selectedChecks: string[]) => {
        return serverFetch('POST', '/api/compliance/scan', {
            project_id: projectId,
            project_path: projectPath,
            selected_checks: selectedChecks,
            mode: 'directory',
        });
    });

    ipcMain.handle('cgctl:getComplianceScanStatus', async (_, jobId: string) => {
        return serverFetch('GET', `/api/compliance/status/${jobId}`);
    });

    ipcMain.handle('cgctl:getComplianceReport', async (_, jobId: string) => {
        return serverFetch('GET', `/api/compliance/report/${jobId}`);
    });

    ipcMain.handle('cgctl:listComplianceChecks', async () => {
        return serverFetch('GET', '/api/compliance/checks');
    });

    // Get file expert
    ipcMain.handle('cgctl:getFileExpert', async (_, projectPath: string, filePath: string) => {
        return serverFetch('POST', '/api/analyze/expert', {
            project_path: projectPath,
            file_path: filePath,
        });
    });

    // Get file history
    ipcMain.handle('cgctl:getFileHistory', async (_, projectPath: string, filePath: string, lineStart?: number, lineEnd?: number) => {
        const body: Record<string, any> = { project_path: projectPath, file_path: filePath };
        if (lineStart) body.line_start = lineStart;
        if (lineEnd) body.line_end = lineEnd;
        return serverFetch('POST', '/api/analyze/history', body);
    });

    // Find dependencies (single file)
    ipcMain.handle('cgctl:findDependencies', async (_, projectPath: string, filePath: string) => {
        return serverFetch('POST', '/api/analyze/dependencies', {
            project_path: projectPath,
            file_path: filePath,
        });
    });

    // Analyze project dependencies (bulk graph)
    ipcMain.handle('cgctl:analyzeProjectDependencies', async (_, projectPath: string) => {
        return serverFetch('POST', '/api/analyze/project-dependencies', {
            project_path: projectPath,
        });
    });

    // Detect documentation gaps
    ipcMain.handle('cgctl:detectDocumentationGaps', async (_, projectPath: string, filePath: string) => {
        return serverFetch('POST', '/api/analyze/documentation-gaps', {
            project_path: projectPath,
            file_path: filePath,
        });
    });

    // Analyze testability
    ipcMain.handle('cgctl:analyzeTestability', async (_, projectPath: string, filePath: string) => {
        return serverFetch('POST', '/api/analyze/testability', {
            project_path: projectPath,
            file_path: filePath,
        });
    });

    // Query codebase (RAG)
    ipcMain.handle('cgctl:queryCodebase', async (_, projectPath: string, query: string, nResults: number = 5) => {
        return serverFetch('POST', '/api/ask', {
            project_id: path.basename(projectPath),
            question: query,
            conversation_history: [],
        });
    });

    // Run tests
    ipcMain.handle('cgctl:runTests', async (_, projectPath: string, filePath?: string, testDir?: string) => {
        const body: Record<string, any> = { project_path: projectPath };
        if (filePath) body.file_path = filePath;
        if (testDir) body.test_dir = testDir;
        return serverFetch('POST', '/api/analyze/tests', body);
    });

    // Generate test case using AI
    ipcMain.handle('cgctl:generateTestCase', async (_, projectPath: string, filePath: string, fileContent: string) => {
        return serverFetch('POST', '/api/analyze/generate-test', {
            project_path: projectPath,
            file_path: filePath,
            file_content: fileContent,
        });
    });

    // Run a generated test file
    ipcMain.handle('cgctl:runLocalTest', async (_, projectPath: string, testFilePath: string) => {
        return serverFetch('POST', '/api/analyze/run-test', {
            project_path: projectPath,
            test_file_path: testFilePath,
        });
    });

    // Update API Key
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
}
