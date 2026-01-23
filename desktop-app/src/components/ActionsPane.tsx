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

export default function ActionsPane({ selectedFile, projectPath }: ActionsPaneProps) {
    const [activeTab, setActiveTab] = useState<'health' | 'compliance' | 'experts' | 'history' | null>(null);
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<any>(null);

    // Reset results when file changes, but keep the tab if user wants to switch files?
    // Let's reset results when file changes to avoid showing old data.
    useEffect(() => {
        if (!selectedFile) {
            setActiveTab(null);
        }
        setData(null);
        setLoading(false);
    }, [selectedFile]);

    const handleActionClick = async (action: 'health' | 'compliance' | 'experts' | 'history') => {
        console.log(`Action clicked: ${action} for file:`, selectedFile?.path);
        if (!selectedFile) {
            console.warn("No file selected for action");
            return;
        }

        if (activeTab === action && data) {
            // If already open and has data, maybe close it? Or just keep it.
            // Let's toggle it.
            setActiveTab(null);
            setData(null);
            return;
        }

        setActiveTab(action);
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
            }
            setData(result);
        } catch (error) {
            console.error(error);
            setData({ error: 'Failed to load data' });
        } finally {
            setLoading(false);
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
                    <div className="tooltip">Compliance Scan</div>
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
            </div>

            {/* Results Pane Overlay */}
            <div className={`results-pane ${activeTab ? 'open' : ''}`}>
                {activeTab && selectedFile && (
                    <>
                        <div className="results-header">
                            <div>
                                <h2 style={{ margin: 0 }}>{activeTab.charAt(0).toUpperCase() + activeTab.slice(1)}</h2>
                                <p style={{ margin: '4px 0 0 0', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                                    {selectedFile.path}
                                </p>
                            </div>
                            <button className="close-btn" onClick={() => setActiveTab(null)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', fontSize: '1.5rem', cursor: 'pointer' }}>×</button>
                        </div>

                        <div className="results-content">
                            {loading && <div className="loading-spinner"></div>}

                            {!loading && data && (
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

                            {!loading && !data && (
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
