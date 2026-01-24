import { useSettings } from '../context/SettingsContext';
import { useProject } from '../App';
import { useEffect } from 'react';

interface SettingsPaneProps {
    isOpen: boolean;
    onClose: () => void;
}

export default function SettingsPane({ isOpen, onClose }: SettingsPaneProps) {
    const { settings, updateGraphSetting, updateGeminiKey } = useSettings();
    const { projectPath } = useProject();

    // Sync API key with backend .env when it changes
    useEffect(() => {
        if (projectPath && settings.geminiApiKey) {
            window.cgctl.updateApiKey(projectPath, settings.geminiApiKey);
        }
    }, [settings.geminiApiKey, projectPath]);

    if (!isOpen) return null;

    return (
        <div className="settings-overlay" onClick={onClose}>
            <div className="settings-pane" onClick={e => e.stopPropagation()}>
                <div className="settings-header">
                    <h2>Configuration</h2>
                    <button className="close-btn" onClick={onClose}>×</button>
                </div>

                <div className="settings-content">
                    <section>
                        <h3>Graph Visuals</h3>
                        <div className="setting-item">
                            <label>Directory Radius: {settings.graph.dirRadius}px</label>
                            <input
                                type="range"
                                min="10"
                                max="100"
                                value={settings.graph.dirRadius}
                                onChange={e => updateGraphSetting('dirRadius', parseInt(e.target.value))}
                            />
                        </div>

                        <div className="setting-item">
                            <label>File Scale: {settings.graph.fileRadiusScale}</label>
                            <input
                                type="range"
                                min="0.05"
                                max="0.5"
                                step="0.01"
                                value={settings.graph.fileRadiusScale}
                                onChange={e => updateGraphSetting('fileRadiusScale', parseFloat(e.target.value))}
                            />
                        </div>

                        <div className="setting-item">
                            <label>Edge Opacity: {settings.graph.edgeOpacity}</label>
                            <input
                                type="range"
                                min="0.05"
                                max="1.0"
                                step="0.05"
                                value={settings.graph.edgeOpacity}
                                onChange={e => updateGraphSetting('edgeOpacity', parseFloat(e.target.value))}
                            />
                        </div>

                        <div className="setting-item">
                            <label>Node Spread: {Math.abs(settings.graph.nodeSpread)}</label>
                            <input
                                type="range"
                                min="100"
                                max="1000"
                                value={Math.abs(settings.graph.nodeSpread)}
                                onChange={e => updateGraphSetting('nodeSpread', -parseInt(e.target.value))}
                            />
                        </div>
                    </section>

                    <section>
                        <h3>LLM Configuration</h3>
                        <div className="setting-item">
                            <label>Gemini API Key</label>
                            <input
                                type="password"
                                placeholder="Enter API Key..."
                                value={settings.geminiApiKey}
                                onChange={e => updateGeminiKey(e.target.value)}
                                className="api-key-input"
                            />
                            <p className="hint">Used for test generation and compliance summaries.</p>
                        </div>
                    </section>
                </div>

                <div className="settings-footer">
                    <button className="save-btn" onClick={onClose}>Done</button>
                </div>
            </div>
        </div>
    );
}
