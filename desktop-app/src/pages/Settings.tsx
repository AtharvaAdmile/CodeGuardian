import { useState } from "react";
import { Settings, Eye, EyeOff, CheckCircle, XCircle, RefreshCw, Key } from "lucide-react";
import { useProjectContext } from "../App";
import { getHealth } from "../lib/api";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import { StatusDot } from "../components/shared/Badge";

export default function SettingsPage() {
  const { healthStatus } = useProjectContext();
  const [showNimKey, setShowNimKey] = useState(false);
  const [showSupabaseKey, setShowSupabaseKey] = useState(false);
  const [nimApiKey, setNimApiKey] = useState("");
  const [supabaseUrl, setSupabaseUrl] = useState("");
  const [supabaseKey, setSupabaseKey] = useState("");
  const [isTestingNim, setIsTestingNim] = useState(false);
  const [isTestingSupabase, setIsTestingSupabase] = useState(false);
  const [nimStatus, setNimStatus] = useState<"idle" | "success" | "error">("idle");
  const [supabaseStatus, setSupabaseStatus] = useState<"idle" | "success" | "error">("idle");

  const handleTestNim = async () => {
    setIsTestingNim(true);
    setNimStatus("idle");
    try {
      await getHealth();
      setNimStatus("success");
    } catch {
      setNimStatus("error");
    } finally {
      setIsTestingNim(false);
    }
  };

  const handleTestSupabase = async () => {
    setIsTestingSupabase(true);
    setSupabaseStatus("idle");
    try {
      await getHealth();
      setSupabaseStatus("success");
    } catch {
      setSupabaseStatus("error");
    } finally {
      setIsTestingSupabase(false);
    }
  };

  const serverStatus = healthStatus?.status || "unhealthy";

  return (
    <div className="flex flex-col h-full">
      <div className="p-6 border-b border-border">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Settings className="w-6 h-6 text-text-secondary" />
          Settings
        </h1>
        <p className="text-text-secondary mt-1">
          Configure API keys and project settings
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl mx-auto space-y-6">
          <div className="bg-bg-secondary border border-border rounded-xl p-6">
            <h2 className="text-lg font-semibold mb-4">Server Status</h2>
            <div className="flex items-center gap-3 p-4 bg-bg-tertiary rounded-lg">
              <StatusDot status={serverStatus as "healthy" | "degraded" | "unhealthy"} size="lg" />
              <div>
                <div className="font-medium">Backend Server</div>
                <div className="text-sm text-text-muted">
                  {serverStatus === "healthy" ? "Connected and healthy" : 
                   serverStatus === "degraded" ? "Degraded performance" : 
                   "Not connected"}
                </div>
              </div>
              {healthStatus && (
                <div className="ml-auto text-right text-sm text-text-muted">
                  <div>Uptime: {Math.round(healthStatus.uptime_seconds / 60)}m</div>
                  <div>Components: {Object.keys(healthStatus.components).length}</div>
                </div>
              )}
            </div>

            {Object.keys(healthStatus?.components || {}).length > 0 && (
              <div className="mt-4 space-y-2">
                {Object.entries(healthStatus!.components).map(([name, status]) => (
                  <div key={name} className="flex items-center justify-between text-sm">
                    <span className="text-text-secondary">{name}</span>
                    <span className={status === "healthy" ? "text-accent-green" : "text-accent-amber"}>
                      {status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-bg-secondary border border-border rounded-xl p-6">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Key className="w-5 h-5" />
              API Keys
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  NVIDIA NIM API Key
                </label>
                <div className="flex gap-2">
                  <div className="flex-1 relative">
                    <input
                      type={showNimKey ? "text" : "password"}
                      value={nimApiKey}
                      onChange={(e) => setNimApiKey(e.target.value)}
                      placeholder="nvapi-..."
                      className="w-full bg-bg-tertiary border border-border rounded-lg px-4 py-2 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                    />
                    <button
                      type="button"
                      onClick={() => setShowNimKey(!showNimKey)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
                    >
                      {showNimKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <button
                    onClick={handleTestNim}
                    disabled={isTestingNim}
                    className="px-4 py-2 bg-bg-tertiary hover:bg-bg-hover border border-border rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                  >
                    {isTestingNim ? <LoadingSpinner size="sm" /> : <RefreshCw className="w-4 h-4" />}
                    Test
                  </button>
                </div>
                {nimStatus === "success" && (
                  <div className="flex items-center gap-1 mt-2 text-sm text-accent-green">
                    <CheckCircle className="w-4 h-4" /> Connection successful
                  </div>
                )}
                {nimStatus === "error" && (
                  <div className="flex items-center gap-1 mt-2 text-sm text-accent-red">
                    <XCircle className="w-4 h-4" /> Connection failed
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Supabase URL
                </label>
                <input
                  type="text"
                  value={supabaseUrl}
                  onChange={(e) => setSupabaseUrl(e.target.value)}
                  placeholder="https://xxxxx.supabase.co"
                  className="w-full bg-bg-tertiary border border-border rounded-lg px-4 py-2 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Supabase Key
                </label>
                <div className="flex gap-2">
                  <div className="flex-1 relative">
                    <input
                      type={showSupabaseKey ? "text" : "password"}
                      value={supabaseKey}
                      onChange={(e) => setSupabaseKey(e.target.value)}
                      placeholder="eyJ..."
                      className="w-full bg-bg-tertiary border border-border rounded-lg px-4 py-2 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                    />
                    <button
                      type="button"
                      onClick={() => setShowSupabaseKey(!showSupabaseKey)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
                    >
                      {showSupabaseKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <button
                    onClick={handleTestSupabase}
                    disabled={isTestingSupabase}
                    className="px-4 py-2 bg-bg-tertiary hover:bg-bg-hover border border-border rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                  >
                    {isTestingSupabase ? <LoadingSpinner size="sm" /> : <RefreshCw className="w-4 h-4" />}
                    Test
                  </button>
                </div>
                {supabaseStatus === "success" && (
                  <div className="flex items-center gap-1 mt-2 text-sm text-accent-green">
                    <CheckCircle className="w-4 h-4" /> Connection successful
                  </div>
                )}
                {supabaseStatus === "error" && (
                  <div className="flex items-center gap-1 mt-2 text-sm text-accent-red">
                    <XCircle className="w-4 h-4" /> Connection failed
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="bg-bg-secondary border border-border rounded-xl p-6">
            <h2 className="text-lg font-semibold mb-4">Project Configuration</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Quality Threshold
                </label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  defaultValue="70"
                  className="w-full accent-accent-blue"
                />
                <div className="flex justify-between text-xs text-text-muted mt-1">
                  <span>0</span>
                  <span>70%</span>
                  <span>100</span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Batch Size
                </label>
                <select className="w-full bg-bg-tertiary border border-border rounded-lg px-4 py-2 text-text-primary focus:outline-none focus:border-accent-blue">
                  <option value="16">16</option>
                  <option value="32">32</option>
                  <option value="64">64</option>
                  <option value="128">128</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
