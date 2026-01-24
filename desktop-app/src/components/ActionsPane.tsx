import { useState, useEffect } from 'react';

interface FileNode {
    path: string;
    name: string;
    size: number;
    type: 'file' | 'directory';
}

interface ActionsPaneProps {
    selectedFile: FileNode | null;
    projectPath: string;
}

interface TestState {
    code: string | null;
    path: string | null;
    isGenerating: boolean;
    isRunning: boolean;
    output: string | null;
    passed: boolean | null;
    error: string | null;
}

const formatLineRanges = (lines: number[]): string => {
    if (lines.length === 0) return '';
    const sorted = [...new Set(lines)].sort((a, b) => a - b);
    const ranges: string[] = [];
    let start = sorted[0];
    let end = sorted[0];

    for (let i = 1; i <= sorted.length; i++) {
        if (i < sorted.length && sorted[i] === end + 1) {
            end = sorted[i];
        } else {
            if (start === end) {
                ranges.push(`${start}`);
            } else {
                ranges.push(`${start}-${end}`);
            }
            if (i < sorted.length) {
                start = sorted[i];
                end = sorted[i];
            }
        }
    }
    return ranges.join(', ');
};

// Check if file is testable (Python, JS, or TS)
const isTestableFile = (fileName: string): boolean => {
    const ext = fileName.toLowerCase();
    return ext.endsWith('.py') || ext.endsWith('.js') || ext.endsWith('.ts') || ext.endsWith('.tsx') || ext.endsWith('.jsx');
};

export default function ActionsPane({ selectedFile, projectPath }: ActionsPaneProps) {
    const [activeTab, setActiveTab] = useState<'health' | 'compliance' | 'regulatory' | 'experts' | 'history' | 'tests' | null>(null);
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<any>(null);

    // Test-specific state
    const [testState, setTestState] = useState<TestState>({
        code: null,
        path: null,
        isGenerating: false,
        isRunning: false,
        output: null,
        passed: null,
        error: null,
    });

    // Reset results when file changes
    useEffect(() => {
        if (!selectedFile) {
            setActiveTab(null);
        }
        setData(null);
        setLoading(false);
        setTestState({
            code: null,
            path: null,
            isGenerating: false,
            isRunning: false,
            output: null,
            passed: null,
            error: null,
        });
    }, [selectedFile]);

    // Check for existing test when tests tab is opened
    useEffect(() => {
        const checkExistingTest = async () => {
            if (activeTab === 'tests' && selectedFile && projectPath) {
                try {
                    const result = await window.cgctl.testFileExists(projectPath, selectedFile.path);
                    if (result.exists && result.content) {
                        setTestState(prev => ({
                            ...prev,
                            code: result.content || null,
                            path: result.path || null,
                        }));
                    }
                } catch (err) {
                    console.error('Error checking existing test:', err);
                }
            }
        };
        checkExistingTest();
    }, [activeTab, selectedFile, projectPath]);

    const handleActionClick = async (action: 'health' | 'compliance' | 'regulatory' | 'experts' | 'history' | 'tests') => {
        console.log(`Action clicked: ${action} for file:`, selectedFile?.path);
        if (!selectedFile) {
            console.warn("No file selected for action");
            return;
        }

        if (activeTab === action && data) {
            setActiveTab(null);
            setData(null);
            return;
        }

        setActiveTab(action);

        // Tests are handled differently
        if (action === 'tests') {
            setData({ isTestsTab: true });
            return;
        }

        setLoading(true);
        setData(null);

        try {
            let result;
            const fullPath = selectedFile.path;

            switch (action) {
                case 'health':
                    result = await window.cgctl.getFileHealth(projectPath, fullPath);
                    break;
                case 'compliance':
                    const absPath = `${projectPath}/${fullPath}`;
                    const content = await window.cgctl.readFile(absPath);
                    result = await window.cgctl.checkCompliance(projectPath, content);
                    break;
                case 'experts':
                    result = await window.cgctl.getFileExpert(projectPath, fullPath);
                    break;
                case 'history':
                    result = await window.cgctl.getFileHistory(projectPath, fullPath);
                    break;
                case 'regulatory':
                    const regAbsPath = `${projectPath}/${fullPath}`;
                    const regContent = await window.cgctl.readFile(regAbsPath);
                    result = await window.cgctl.checkRegulatoryCompliance(projectPath, fullPath, regContent);
                    break;
            }
            setData(result);
        } catch (error) {
            console.error(error);
            setData({ error: 'Failed to load data' });
        } finally {
            setLoading(false);
        }
    };

    const handleGenerateTest = async () => {
        if (!selectedFile || !projectPath) return;

        setTestState(prev => ({ ...prev, isGenerating: true, error: null }));

        try {
            const absPath = `${projectPath}/${selectedFile.path}`;
            const fileContent = await window.cgctl.readFile(absPath);

            // Generate the test
            const result = await window.cgctl.generateTestCase(projectPath, selectedFile.path, fileContent);

            if (result.error || !result.test_code) {
                setTestState(prev => ({
                    ...prev,
                    isGenerating: false,
                    error: result.error || 'Failed to generate test',
                }));
                return;
            }

            // Save the test file
            const saveResult = await window.cgctl.saveTestFile(projectPath, selectedFile.path, result.test_code);

            if (!saveResult.success) {
                setTestState(prev => ({
                    ...prev,
                    isGenerating: false,
                    error: saveResult.error || 'Failed to save test file',
                }));
                return;
            }

            setTestState(prev => ({
                ...prev,
                isGenerating: false,
                code: result.test_code,
                path: saveResult.path || null,
            }));

        } catch (err: any) {
            console.error('Error generating test:', err);
            setTestState(prev => ({
                ...prev,
                isGenerating: false,
                error: err.message || 'Failed to generate test',
            }));
        }
    };

    const handleRunTest = async () => {
        if (!testState.path || !projectPath) return;

        setTestState(prev => ({ ...prev, isRunning: true, output: null, passed: null }));

        try {
            const result = await window.cgctl.runLocalTest(projectPath, testState.path);

            setTestState(prev => ({
                ...prev,
                isRunning: false,
                output: result.output || result.error_message || '',
                passed: result.passed,
            }));
        } catch (err: any) {
            console.error('Error running test:', err);
            setTestState(prev => ({
                ...prev,
                isRunning: false,
                output: err.message || 'Failed to run test',
                passed: false,
            }));
        }
    };

    return (
        <div className="actions-container" onClick={(e) => e.stopPropagation()}>
            {/* Persistent Sidebar Overlaid on Graph */}
            <div className="actions-sidebar">
                <div
                    className={`action-card ${!selectedFile ? 'disabled' : ''} ${activeTab === 'health' ? 'active' : ''}`}
                    onClick={() => handleActionClick('health')}
                >
                    ❤️
                    <div className="tooltip">File Health</div>
                </div>
                <div
                    className={`action-card ${!selectedFile ? 'disabled' : ''} ${activeTab === 'compliance' ? 'active' : ''}`}
                    onClick={() => handleActionClick('compliance')}
                >
                    🛡️
                    <div className="tooltip">Standard Compliance</div>
                </div>
                <div
                    className={`action-card ${!selectedFile ? 'disabled' : ''} ${activeTab === 'regulatory' ? 'active' : ''}`}
                    onClick={() => handleActionClick('regulatory')}
                >
                    ⚖️
                    <div className="tooltip">Regulatory Compliance</div>
                </div>
                <div
                    className={`action-card ${!selectedFile ? 'disabled' : ''} ${activeTab === 'experts' ? 'active' : ''}`}
                    onClick={() => handleActionClick('experts')}
                >
                    👥
                    <div className="tooltip">Code Experts</div>
                </div>
                <div
                    className={`action-card ${!selectedFile ? 'disabled' : ''} ${activeTab === 'history' ? 'active' : ''}`}
                    onClick={() => handleActionClick('history')}
                >
                    📜
                    <div className="tooltip">Git History</div>
                </div>
                <div
                    className={`action-card ${!selectedFile || !isTestableFile(selectedFile.name) ? 'disabled' : ''} ${activeTab === 'tests' ? 'active' : ''}`}
                    onClick={() => selectedFile && isTestableFile(selectedFile.name) && handleActionClick('tests')}
                >
                    🧪
                    <div className="tooltip">Gen Tests</div>
                </div>
            </div>

            {/* Results Pane Overlay */}
            <div className={`results-pane ${activeTab ? 'open' : ''}`}>
                {activeTab && selectedFile && (
                    <>
                        <div className="results-header">
                            <div>
                                <h2 style={{ margin: 0 }}>
                                    {activeTab === 'tests' ? 'Test Generation' :
                                        activeTab === 'regulatory' ? 'Regulatory Compliance' :
                                            activeTab.charAt(0).toUpperCase() + activeTab.slice(1)}
                                </h2>
                                <p style={{ margin: '4px 0 0 0', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                                    {selectedFile.path}
                                </p>
                            </div>
                            <button className="close-btn" onClick={() => setActiveTab(null)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', fontSize: '1.5rem', cursor: 'pointer' }}>×</button>
                        </div>

                        <div className="results-content">
                            {loading && <div className="loading-spinner"></div>}

                            {/* Tests Tab */}
                            {activeTab === 'tests' && (
                                <div className="tests-result">
                                    {/* Generating State */}
                                    {testState.isGenerating && (
                                        <div className="test-generating">
                                            <div className="loading-spinner"></div>
                                            <p style={{ marginTop: '1rem', color: 'var(--text-secondary)' }}>
                                                AI is writing tests...
                                            </p>
                                        </div>
                                    )}

                                    {/* Error State */}
                                    {testState.error && !testState.isGenerating && (
                                        <div className="test-error">
                                            <div className="status fail">❌ Error</div>
                                            <p>{testState.error}</p>
                                            <button className="generate-test-btn" onClick={handleGenerateTest}>
                                                🔄 Retry
                                            </button>
                                        </div>
                                    )}

                                    {/* No Test State */}
                                    {!testState.code && !testState.isGenerating && !testState.error && (
                                        <div className="test-empty">
                                            <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
                                                No test file exists for this source file.
                                            </p>
                                            <button className="generate-test-btn" onClick={handleGenerateTest}>
                                                🧪 Generate Test Case
                                            </button>
                                        </div>
                                    )}

                                    {/* Test Exists State */}
                                    {testState.code && !testState.isGenerating && (
                                        <div className="test-exists">
                                            <div className="test-actions">
                                                <button
                                                    className="run-test-btn"
                                                    onClick={handleRunTest}
                                                    disabled={testState.isRunning}
                                                >
                                                    {testState.isRunning ? '⏳ Running...' : '▶️ Run Test'}
                                                </button>
                                                <button
                                                    className="regenerate-test-btn"
                                                    onClick={handleGenerateTest}
                                                    disabled={testState.isGenerating}
                                                >
                                                    🔄 Regenerate
                                                </button>
                                            </div>

                                            {testState.path && (
                                                <p className="test-path">
                                                    📁 {testState.path.replace(projectPath + '/', '')}
                                                </p>
                                            )}

                                            <div className="test-code-preview">
                                                <pre><code>{testState.code}</code></pre>
                                            </div>

                                            {/* Test Output Console */}
                                            {(testState.output || testState.isRunning) && (
                                                <div className="test-output-section">
                                                    <h4>Test Output</h4>
                                                    {testState.isRunning ? (
                                                        <div className="test-console running">
                                                            <span className="blinking">Running tests...</span>
                                                        </div>
                                                    ) : (
                                                        <>
                                                            <div className={`test-result-badge ${testState.passed ? 'success' : 'failure'}`}>
                                                                {testState.passed ? '✅ All Tests Passed' : '❌ Tests Failed'}
                                                            </div>
                                                            <div className={`test-console ${testState.passed ? 'success' : 'failure'}`}>
                                                                <pre>{testState.output}</pre>
                                                            </div>
                                                        </>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}

                            {!loading && data && activeTab !== 'tests' && (
                                <div className="result-container fade-in">
                                    {activeTab === 'health' && (
                                        <div className="health-result">
                                            <div className="score-ring" style={{ '--score': data.health_score } as any}>
                                                <span>{data.health_score}</span>
                                            </div>
                                            <div className="metrics">
                                                <div>Complexity: {data.complexity?.score} ({data.complexity?.rank})</div>
                                                <div>Churn: {data.churn?.value} ({data.churn?.rank})</div>
                                            </div>
                                            <div className={`status ${data.is_hotspot ? 'fail' : 'pass'}`} style={{ marginTop: '1rem', textAlign: 'center' }}>
                                                {data.is_hotspot ? '🔥 Hotspot Detected' : '✅ Stable File'}
                                            </div>
                                            <p style={{ marginTop: '1.5rem', color: 'var(--text-primary)', fontWeight: 500 }}>
                                                {data.recommendation?.message}
                                            </p>
                                            {data.recommendation?.action && (
                                                <p style={{ marginTop: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                                                    Recommended: {data.recommendation.action}
                                                </p>
                                            )}
                                        </div>
                                    )}

                                    {activeTab === 'compliance' && (
                                        <div className="compliance-result">
                                            <div className={`status ${data.passed ? 'pass' : 'fail'}`}>
                                                {data.passed ? '✅ Compliant' : '❌ Issues Found'}
                                            </div>
                                            <p style={{ marginBottom: '1.5rem' }}>{data.summary}</p>
                                            {(() => {
                                                const grouped = (data.violations || []).reduce((acc: any, v: any) => {
                                                    const key = `${v.severity}-${v.message}`;
                                                    if (!acc[key]) {
                                                        acc[key] = {
                                                            severity: v.severity,
                                                            message: v.message,
                                                            lines: []
                                                        };
                                                    }
                                                    acc[key].lines.push(v.line || v.line_number);
                                                    return acc;
                                                }, {});

                                                return Object.values(grouped).map((g: any, i: number) => (
                                                    <div key={i} className="violation-item">
                                                        <div style={{ fontWeight: 600, color: '#f85149', marginBottom: '4px' }}>
                                                            Lines {formatLineRanges(g.lines)}: {g.severity?.toUpperCase()}
                                                        </div>
                                                        <div>{g.message}</div>
                                                    </div>
                                                ));
                                            })()}
                                        </div>
                                    )}

                                    {activeTab === 'regulatory' && (
                                        <div className="regulatory-result">
                                            <div className="score-ring" style={{ '--score': data.score } as any}>
                                                <span>{data.score}</span>
                                            </div>
                                            <div className={`status ${data.passed ? 'pass' : 'fail'}`} style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
                                                {data.passed ? '✅ FDA/ISO Compliant' : '⚠️ Gaps Detected'}
                                            </div>

                                            <p style={{ marginBottom: '1.5rem', lineHeight: '1.5' }}>{data.summary}</p>

                                            {data.violations?.length > 0 && (
                                                <div className="violations-list">
                                                    <h4 style={{ marginBottom: '1rem' }}>Gaps Found:</h4>
                                                    {data.violations.map((v: any, i: number) => (
                                                        <div key={i} className="violation-item" style={{ borderLeftColor: v.severity === 'Critical' ? '#f85149' : '#e3b341' }}>
                                                            <div style={{ fontWeight: 600, color: v.severity === 'Critical' ? '#f85149' : '#e3b341', marginBottom: '4px' }}>
                                                                {v.rule} | {v.severity?.toUpperCase()}
                                                            </div>
                                                            <div style={{ fontSize: '0.9rem', marginBottom: '8px' }}>{v.message}</div>
                                                            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                                                                Recommendation: {v.recommendation}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {activeTab === 'experts' && (
                                        <div className="experts-result">
                                            <h4>Primary Expert</h4>
                                            <div className="expert-card primary">
                                                {data.primary_expert || 'None'}
                                            </div>

                                            {data.backup && (
                                                <>
                                                    <h4>Backup</h4>
                                                    <div className="expert-card">
                                                        {data.backup}
                                                    </div>
                                                </>
                                            )}

                                            {data.experts?.length > 0 && (
                                                <>
                                                    <h4>Contributors</h4>
                                                    <ul className="expert-list">
                                                        {data.experts.map((e: any, i: number) => (
                                                            <li key={i}>
                                                                <span>{e.name || e.author}</span>
                                                                <span className="text-secondary">{e.score?.toFixed(1)}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </>
                                            )}
                                            <p style={{ marginTop: '1.5rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                                Last active: {data.last_active}
                                            </p>
                                        </div>
                                    )}

                                    {activeTab === 'history' && (
                                        <div className="history-result">
                                            <h4>Recent Changes</h4>
                                            <p style={{ fontSize: '0.9rem', marginBottom: '1.5rem', color: 'var(--text-secondary)' }}>
                                                {data.summary}
                                            </p>
                                            <div className="timeline">
                                                {data.history?.map((commit: any, i: number) => (
                                                    <div key={i} className="timeline-item">
                                                        <div className="commit-date">{new Date(commit.date).toLocaleDateString()}</div>
                                                        <div className="commit-msg">{commit.message}</div>
                                                        <div className="commit-author">{commit.author}</div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {data.error && <div className="error-msg">{data.error}</div>}
                                </div>
                            )}

                            {!loading && !data && activeTab !== 'tests' && (
                                <div className="empty-action-state">
                                    Select an action to analyze this file.
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
