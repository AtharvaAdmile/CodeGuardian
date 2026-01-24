import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface GraphSettings {
    dirRadius: number;
    fileRadiusScale: number;
    nodeSpread: number;
    edgeOpacity: number;
}

interface AppSettings {
    graph: GraphSettings;
    geminiApiKey: string;
}

interface SettingsContextType {
    settings: AppSettings;
    updateGraphSetting: (key: keyof GraphSettings, value: number) => void;
    updateGeminiKey: (key: string) => void;
}

const DEFAULT_SETTINGS: AppSettings = {
    graph: {
        dirRadius: 20,
        fileRadiusScale: 0.1,
        nodeSpread: -400,
        edgeOpacity: 0.2,
    },
    geminiApiKey: '',
};

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: ReactNode }) {
    const [settings, setSettings] = useState<AppSettings>(() => {
        const saved = localStorage.getItem('cg_settings');
        return saved ? JSON.parse(saved) : DEFAULT_SETTINGS;
    });

    useEffect(() => {
        localStorage.setItem('cg_settings', JSON.stringify(settings));
    }, [settings]);

    const updateGraphSetting = (key: keyof GraphSettings, value: number) => {
        setSettings(prev => ({
            ...prev,
            graph: {
                ...prev.graph,
                [key]: value
            }
        }));
    };

    const updateGeminiKey = (key: string) => {
        setSettings(prev => ({
            ...prev,
            geminiApiKey: key
        }));
    };

    return (
        <SettingsContext.Provider value={{ settings, updateGraphSetting, updateGeminiKey }}>
            {children}
        </SettingsContext.Provider>
    );
}

export const useSettings = () => {
    const context = useContext(SettingsContext);
    if (!context) throw new Error('useSettings must be used within a SettingsProvider');
    return context;
};
