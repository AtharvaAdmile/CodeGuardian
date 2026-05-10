import { useState, useEffect, useRef } from "react";
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  Play,
  RefreshCw,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  FolderOpen,
  Brain,
  Wrench,
  Eye,
  Flag,
  CheckCircle2,
  FileText,
} from "lucide-react";
import { useProjectContext } from "../App";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import {
  listComplianceChecks,
  startComplianceScanStream,
  getComplianceReport,
} from "../lib/api";
import type {
  ComplianceCheckType,
  ComplianceReport,
  ComplianceFinding,
  ComplianceStep,
} from "../lib/types";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "text-accent-red bg-accent-red/10 border-accent-red/30",
  high: "text-orange-500 bg-orange-500/10 border-orange-500/30",
  medium: "text-accent-amber bg-accent-amber/10 border-accent-amber/30",
  low: "text-text-muted bg-bg-tertiary border-border",
};

const SEVERITY_BG: Record<string, string> = {
  critical: "bg-accent-red",
  high: "bg-orange-500",
  medium: "bg-accent-amber",
  low: "bg-text-muted",
};

const ACTION_ICONS: Record<string, React.ReactNode> = {
  plan: <Brain className="w-4 h-4 text-accent-blue" />,
  tool_call: <Wrench className="w-4 h-4 text-accent-amber" />,
  observation: <Eye className="w-4 h-4 text-text-muted" />,
  finding: <Flag className="w-4 h-4 text-accent-red" />,
  check_complete: <CheckCircle2 className="w-4 h-4 text-accent-green" />,
  final: <FileText className="w-4 h-4 text-accent-blue" />,
};

const ACTION_LABELS: Record<string, string> = {
  plan: "Planning",
  tool_call: "Exploring",
  observation: "Observing",
  finding: "Violation Found",
  check_complete: "Check Complete",
  final: "Final Summary",
};

function SeverityBadge({ severity }: { severity: string }) {
  const s = severity.toLowerCase();
  const colors = SEVERITY_COLORS[s] || SEVERITY_COLORS.low;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${colors}`}>
      {s.charAt(0).toUpperCase() + s.slice(1)}
    </span>
  );
}

function ScoreGauge({ score, size = "lg" }: { score: number; size?: "sm" | "lg" }) {
  const radius = size === "lg" ? 54 : 36;
  const stroke = size === "lg" ? 10 : 8;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 80 ? "#22c55e" : score >= 50 ? "#f59e0b" : "#ef4444";

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={(radius + stroke) * 2} height={(radius + stroke) * 2} className="transform -rotate-90">
        <circle cx={radius + stroke} cy={radius + stroke} r={radius} stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} fill="none" />
        <circle cx={radius + stroke} cy={radius + stroke} r={radius} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset} className="transition-all duration-1000 ease-out" />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={`font-bold ${size === "lg" ? "text-3xl" : "text-lg"}`} style={{ color }}>{Math.round(score)}</span>
      </div>
    </div>
  );
}

function FindingRow({ finding, defaultOpen }: { finding: ComplianceFinding; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen || false);
  const s = finding.severity.toLowerCase();
  const dotColor = SEVERITY_BG[s] || SEVERITY_BG.low;
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-3 hover:bg-bg-tertiary/50 transition-colors text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
          <div className="min-w-0">
            <p className="text-sm font-medium text-text-primary truncate">{finding.message}</p>
            <p className="text-xs text-text-muted truncate mt-0.5">
              {finding.file_path}:{finding.line}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-3">
          <SeverityBadge severity={finding.severity} />
          {open ? <ChevronUp className="w-4 h-4 text-text-muted" /> : <ChevronDown className="w-4 h-4 text-text-muted" />}
        </div>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-0 border-t border-border space-y-2">
          {finding.snippet && (
            <pre className="text-xs font-mono text-text-secondary bg-bg-tertiary rounded p-2 overflow-x-auto">{finding.snippet}</pre>
          )}
          {finding.suggestion && (
            <div className="flex items-start gap-2 text-xs text-text-muted">
              <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
              <span>{finding.suggestion}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StepCard({ step }: { step: ComplianceStep }) {
  const icon = ACTION_ICONS[step.action] || <Eye className="w-4 h-4 text-text-muted" />;
  const label = ACTION_LABELS[step.action] || step.action;
  const hasFindings = step.findings && step.findings.length > 0;

  return (
    <div className="border border-border rounded-lg bg-bg-secondary overflow-hidden">
      <div className="flex items-start gap-3 p-3">
        <div className="w-6 h-6 flex items-center justify-center shrink-0 mt-0.5">
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
              Round {step.round}
            </span>
            {step.check_type && step.check_type !== "_overall" && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-accent-blue/10 text-accent-blue font-medium">
                {step.check_type}
              </span>
            )}
            <span className="text-xs font-medium text-text-muted">{label}</span>
          </div>
          {step.message && (
            <p className="text-sm text-text-primary leading-relaxed">{step.message}</p>
          )}
          {step.tool_name && (
            <div className="flex items-center gap-2 mt-1">
              <code className="text-xs bg-bg-tertiary px-1.5 py-0.5 rounded text-accent-amber font-mono">
                {step.tool_name}
              </code>
              {step.tool_summary && (
                <span className="text-xs text-text-muted">{step.tool_summary}</span>
              )}
            </div>
          )}
          {hasFindings && (
            <div className="mt-2 space-y-1">
              {step.findings.map((f, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-accent-red bg-accent-red/5 rounded px-2 py-1">
                  <Flag className="w-3 h-3 shrink-0" />
                  <span className="font-mono truncate">{f.file_path}:{f.line}</span>
                  <span className="truncate flex-1">{f.message}</span>
                  <SeverityBadge severity={f.severity} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Compliance() {
  const { projectPath, projectName } = useProjectContext();
  const [checks, setChecks] = useState<ComplianceCheckType[]>([]);
  const [checksLoading, setChecksLoading] = useState(true);
  const [selectedChecks, setSelectedChecks] = useState<Set<string>>(new Set());
  const [lastReport, setLastReport] = useState<ComplianceReport | null>(null);

  // Agent workspace state
  const [isScanning, setIsScanning] = useState(false);
  const [steps, setSteps] = useState<ComplianceStep[]>([]);
  const [liveViolations, setLiveViolations] = useState(0);
  const [currentCheck, setCurrentCheck] = useState<string>("");
  const [streamError, setStreamError] = useState<string>("");
  const abortRef = useRef<AbortController | null>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const fileListRef = useRef<{ file: string; findings: number }[]>([]);

  // Report view state
  const [reportData, setReportData] = useState<ComplianceReport | null>(null);
  const [showFindings, setShowFindings] = useState(false);
  const [showStepLog, setShowStepLog] = useState(true);

  // Load available checks on mount
  useEffect(() => {
    if (!projectName) return;
    setChecksLoading(true);
    listComplianceChecks()
      .then((cs) => {
        setChecks(cs);
        setSelectedChecks(new Set(cs.map((c) => c.id)));
      })
      .catch(() => {
        const fallback: ComplianceCheckType[] = [
          { id: "secrets", name: "Secrets & Credentials", description: "Hardcoded API keys, tokens, passwords", category: "security", default_severity: "critical" },
          { id: "pii", name: "PII Detection", description: "Social Security Numbers, credit card data", category: "privacy", default_severity: "high" },
          { id: "gdpr", name: "GDPR Compliance", description: "Personal data fields: email, phone, address", category: "privacy", default_severity: "medium" },
          { id: "hipaa", name: "HIPAA Compliance", description: "Protected health information", category: "regulatory", default_severity: "critical" },
          { id: "dangerous_funcs", name: "Dangerous Functions", description: "eval, exec, os.system, subprocess", category: "security", default_severity: "critical" },
          { id: "sql_injection", name: "SQL Injection", description: "f-string interpolation in queries", category: "security", default_severity: "high" },
        ];
        setChecks(fallback);
        setSelectedChecks(new Set(fallback.map((c) => c.id)));
      })
      .finally(() => setChecksLoading(false));
  }, [projectName]);

  // Load last report
  useEffect(() => {
    if (!projectName) return;
    getComplianceReport(projectName)
      .then((r) => { if (r) setLastReport(r); })
      .catch(() => {});
  }, [projectName]);

  // Auto-scroll timeline
  useEffect(() => {
    if (timelineRef.current) {
      timelineRef.current.scrollTop = timelineRef.current.scrollHeight;
    }
  }, [steps]);

  const handleStartScan = async (all: boolean) => {
    if (!projectPath || !projectName) return;

    const checksToRun = all
      ? checks.map((c) => c.id)
      : Array.from(selectedChecks);
    if (checksToRun.length === 0) return;

    setIsScanning(true);
    setSteps([]);
    setLiveViolations(0);
    setReportData(null);
    setStreamError("");
    fileListRef.current = [];

    const controller = new AbortController();
    abortRef.current = controller;

    await startComplianceScanStream(
      projectName,
      projectPath,
      checksToRun,
      (step) => {
        setSteps((prev) => [...prev, step]);
        setLiveViolations((prev) => prev + (step.findings?.length || 0));
        if (step.check_type && step.check_type !== "_overall") {
          setCurrentCheck(step.check_type);
        }
      },
      (report) => {
        setReportData(report);
        setLastReport(report);
        setIsScanning(false);
        setCurrentCheck("");
      },
      (error) => {
        setStreamError(error);
        setIsScanning(false);
        setCurrentCheck("");
      },
      controller.signal
    );
  };

  const handleAbort = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setIsScanning(false);
    setCurrentCheck("");
  };

  const toggleCheck = (id: string) => {
    setSelectedChecks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const severityColor = (sev: string) => {
    switch (sev) {
      case "critical": return "text-accent-red";
      case "high": return "text-orange-500";
      case "medium": return "text-accent-amber";
      default: return "text-text-muted";
    }
  };

  if (!projectPath) {
    return (
      <div className="flex-1 overflow-y-auto p-6 flex flex-col items-center justify-center text-text-muted">
        <FolderOpen className="w-12 h-12 mb-3 opacity-50" />
        <p>No project selected</p>
        <p className="text-sm mt-1">Select a project to run compliance checks</p>
      </div>
    );
  }

  // ── View: Agent Workspace (Scanning) ──────────────────────────────

  if (isScanning) {
    return (
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-text-primary">Agent Workspace</h2>
            <p className="text-sm text-text-muted mt-1">{projectName}</p>
          </div>
          <div className="flex items-center gap-3">
            {currentCheck && (
              <span className="text-xs px-2 py-1 rounded bg-accent-blue/10 text-accent-blue font-medium flex items-center gap-1">
                <Brain className="w-3 h-3" />
                {currentCheck}
              </span>
            )}
            <button
              onClick={handleAbort}
              className="px-3 py-1.5 bg-accent-red/10 hover:bg-accent-red/20 text-accent-red border border-accent-red/30 rounded-lg text-sm font-medium transition-all"
            >
              Stop
            </button>
          </div>
        </div>

        {/* Live stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="bg-bg-secondary border border-border rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-text-primary">{steps.length}</div>
            <p className="text-xs text-text-muted mt-1">Agent Steps</p>
          </div>
          <div className="bg-bg-secondary border border-border rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-accent-red">{liveViolations}</div>
            <p className="text-xs text-text-muted mt-1">Findings</p>
          </div>
          <div className="bg-bg-secondary border border-border rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-text-primary">
              {steps.filter((s) => s.action === "check_complete").length}
            </div>
            <p className="text-xs text-text-muted mt-1">Checks Done</p>
          </div>
          <div className="bg-bg-secondary border border-border rounded-xl p-4 text-center">
            <div className="w-5 h-5 mx-auto spinner" />
            <p className="text-xs text-text-muted mt-1">Processing</p>
          </div>
        </div>

        {/* Step timeline */}
        <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-border">
            <h3 className="text-sm font-medium text-text-primary flex items-center gap-2">
              <Brain className="w-4 h-4 text-accent-blue" />
              Agent Reasoning Timeline
            </h3>
          </div>
          <div ref={timelineRef} className="p-4 space-y-3 max-h-[500px] overflow-y-auto">
            {steps.length === 0 ? (
              <div className="flex items-center justify-center py-8">
                <LoadingSpinner size="sm" />
                <span className="ml-3 text-sm text-text-muted">Agent is starting up...</span>
              </div>
            ) : (
              steps.map((step, i) => (
                <StepCard key={i} step={step} />
              ))
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── View: Results Report ──────────────────────────────────────────

  if (reportData) {
    const r = reportData;

    return (
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-text-primary">Compliance Report</h2>
            <p className="text-sm text-text-muted mt-1">{projectName}</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => { handleStartScan(true); }}
              className="px-4 py-2 bg-accent-blue hover:bg-accent-blue/80 rounded-lg text-white text-sm font-medium transition-all flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Re-run
            </button>
          </div>
        </div>

        {/* Score + Summary */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="bg-bg-secondary border border-border rounded-xl p-6 flex flex-col items-center justify-center">
            <ScoreGauge score={r.compliance_score} />
            <p className={`mt-3 text-sm font-medium ${r.passed ? "text-accent-green" : "text-accent-red"}`}>
              {r.passed ? "Passed" : "Failed"}
            </p>
            <p className="text-xs text-text-muted mt-1">{r.scanned_files} files scanned</p>
          </div>
          <div className="lg:col-span-2 bg-bg-secondary border border-border rounded-xl p-6">
            <h3 className="text-sm font-medium text-text-primary mb-3">Summary</h3>
            <p className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">{r.summary}</p>
          </div>
        </div>

        {/* Severity breakdown */}
        <section className="bg-bg-secondary border border-border rounded-xl p-6">
          <h3 className="text-sm font-medium text-text-primary mb-4">Violations by Severity</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: "Critical", sev: "critical", count: r.violation_counts.critical || 0, color: "text-accent-red", bar: "bg-accent-red" },
              { label: "High", sev: "high", count: r.violation_counts.high || 0, color: "text-orange-500", bar: "bg-orange-500" },
              { label: "Medium", sev: "medium", count: r.violation_counts.medium || 0, color: "text-accent-amber", bar: "bg-accent-amber" },
              { label: "Low", sev: "low", count: r.violation_counts.low || 0, color: "text-text-muted", bar: "bg-text-muted" },
            ].map(({ label, sev, count, color, bar }) => (
              <div key={sev} className="text-center">
                <div className={`text-3xl font-bold ${color}`}>{count}</div>
                <div className="mt-1 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${bar}`} style={{ width: `${r.total_violations > 0 ? (count / r.total_violations) * 100 : 0}%` }} />
                </div>
                <p className="text-xs text-text-muted mt-2">{label}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Agent step log */}
        {r.steps && r.steps.length > 0 && (
          <section className="bg-bg-secondary border border-border rounded-xl overflow-hidden">
            <button
              onClick={() => setShowStepLog(!showStepLog)}
              className="w-full px-6 py-4 flex items-center justify-between hover:bg-bg-tertiary/50 transition-colors"
            >
              <h3 className="text-sm font-medium text-text-primary flex items-center gap-2">
                <Brain className="w-4 h-4 text-accent-blue" />
                Agent Steps ({r.steps.length})
              </h3>
              {showStepLog ? <ChevronUp className="w-5 h-5 text-text-muted" /> : <ChevronDown className="w-5 h-5 text-text-muted" />}
            </button>
            {showStepLog && (
              <div className="px-6 pb-6 border-t border-border space-y-3 max-h-[500px] overflow-y-auto">
                {r.steps.filter((s) => s.action !== "final" && s.check_type !== "_overall").map((step, i) => (
                  <StepCard key={i} step={step} />
                ))}
              </div>
            )}
          </section>
        )}

        {/* Findings list */}
        <section className="bg-bg-secondary border border-border rounded-xl overflow-hidden">
          <button
            onClick={() => setShowFindings(!showFindings)}
            className="w-full px-6 py-4 flex items-center justify-between hover:bg-bg-tertiary/50 transition-colors"
          >
            <h3 className="text-sm font-medium text-text-primary">
              Violations ({r.total_violations})
            </h3>
            <div className="flex items-center gap-2">
              {r.check_types_ran.length > 0 && (
                <span className="text-xs text-text-muted">
                  Checks: {r.check_types_ran.join(", ")}
                </span>
              )}
              {showFindings ? <ChevronUp className="w-5 h-5 text-text-muted" /> : <ChevronDown className="w-5 h-5 text-text-muted" />}
            </div>
          </button>
          {showFindings && (
            <div className="px-6 pb-6 border-t border-border space-y-2 max-h-[500px] overflow-y-auto">
              {r.violations.length === 0 ? (
                <p className="text-sm text-text-muted text-center py-8">No violations found. Clean codebase!</p>
              ) : (
                r.violations.map((finding, idx) => (
                  <FindingRow key={idx} finding={finding} defaultOpen={idx < 3} />
                ))
              )}
            </div>
          )}
        </section>

        {/* Check types ran */}
        <section className="bg-bg-secondary border border-border rounded-xl p-4">
          <h3 className="text-xs font-medium text-text-muted mb-2">Checks Performed</h3>
          <div className="flex flex-wrap gap-2">
            {r.check_types_ran.map((ct) => {
              const info = checks.find((c) => c.id === ct);
              return (
                <span key={ct} className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs bg-bg-tertiary text-text-secondary border border-border">
                  <ShieldCheck className="w-3 h-3 text-accent-green" />
                  {info?.name || ct}
                </span>
              );
            })}
          </div>
        </section>
      </div>
    );
  }

  // ── View: Check Selection / Dashboard ────────────────────────────

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div>
          <h2 className="text-xl font-bold text-text-primary">Compliance Check</h2>
          <p className="text-sm text-text-muted mt-1">{projectName}</p>
        </div>
      </div>

      {/* Error banner */}
      {streamError && (
        <div className="bg-accent-red/10 border border-accent-red/30 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-accent-red shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-accent-red">Scan Error</p>
            <p className="text-xs text-text-muted mt-1">{streamError}</p>
          </div>
        </div>
      )}

      {/* Summary card */}
      <div className="bg-bg-secondary border border-border rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-full bg-accent-blue/10 flex items-center justify-center shrink-0">
            <Shield className="w-6 h-6 text-accent-blue" />
          </div>
          <div className="flex-1">
            {lastReport ? (
              <>
                <h3 className="text-lg font-semibold text-text-primary">
                  Last scan: <span className={lastReport.passed ? "text-accent-green" : "text-accent-red"}>
                    {lastReport.passed ? "Passed" : "Failed"}
                  </span>
                </h3>
                <p className="text-text-muted text-sm mt-1">
                  Score: {lastReport.compliance_score}/100 &middot; {lastReport.total_violations} violation(s) &middot; {lastReport.scanned_files} files &middot; {lastReport.steps?.length || 0} agent steps
                </p>
                <button
                  onClick={() => setReportData(lastReport)}
                  className="text-accent-blue hover:underline text-sm mt-2"
                >
                  View last report &rarr;
                </button>
              </>
            ) : (
              <>
                <h3 className="text-lg font-semibold text-text-primary">Ready to Scan</h3>
                <p className="text-text-muted text-sm mt-1">
                  An AI agent will explore your codebase one check at a time, showing each step in real-time.
                </p>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Available checks */}
      {checksLoading ? (
        <div className="flex items-center justify-center py-12">
          <LoadingSpinner size="lg" />
        </div>
      ) : (
        <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-border">
            <h3 className="text-sm font-medium text-text-primary">Available Checks</h3>
          </div>
          <div className="p-3 space-y-1">
            {checks.map((check) => (
              <label
                key={check.id}
                className="flex items-center justify-between p-3 rounded-lg hover:bg-bg-tertiary cursor-pointer transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <input
                    type="checkbox"
                    checked={selectedChecks.has(check.id)}
                    onChange={() => toggleCheck(check.id)}
                    className="w-4 h-4 rounded border-border accent-accent-blue shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-text-primary">{check.name}</p>
                    <p className="text-xs text-text-muted truncate">{check.description}</p>
                  </div>
                </div>
                <span className={`text-xs font-medium shrink-0 ml-3 ${severityColor(check.default_severity)}`}>
                  {check.default_severity.charAt(0).toUpperCase() + check.default_severity.slice(1)}
                </span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center justify-center gap-4 pt-2">
        <button
          onClick={() => handleStartScan(false)}
          disabled={selectedChecks.size === 0}
          className="px-8 py-3 bg-accent-blue hover:bg-accent-blue/80 rounded-xl text-white font-semibold transition-all flex items-center gap-2 shadow-lg shadow-accent-blue/25 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Play className="w-5 h-5" />
          Run Selected ({selectedChecks.size})
        </button>
        <button
          onClick={() => handleStartScan(true)}
          className="px-8 py-3 bg-accent-blue/10 hover:bg-accent-blue/20 text-accent-blue border border-accent-blue/30 rounded-xl font-semibold transition-all flex items-center gap-2"
        >
          <ShieldAlert className="w-5 h-5" />
          Run Complete Check
        </button>
      </div>
    </div>
  );
}
