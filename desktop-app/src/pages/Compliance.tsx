import { useState, useEffect, useRef, useMemo } from "react";
import {
  Play,
  RefreshCw,
  AlertTriangle,
  FolderOpen,
  ShieldCheck,
} from "lucide-react";
import { useProjectContext } from "../App";
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

// ── helpers ──────────────────────────────────────────────────────────────────

const LEVEL_MAP: Record<
  string,
  { label: string; color: string }
> = {
  plan:          { label: "[ PLANNING ]", color: "text-primary" },
  tool_call:     { label: "[ WORKING  ]", color: "text-primary" },
  observation:   { label: "[ OBSERVE  ]", color: "text-on-surface-variant" },
  finding:       { label: "[ THREAT   ]", color: "text-terminal-error" },
  check_complete:{ label: "[ SUCCESS  ]", color: "text-secondary" },
  final:         { label: "[ COMPLETE ]", color: "text-secondary" },
};

function deriveThreatLevel(counts: Record<string, number>): string {
  if ((counts.critical ?? 0) > 0) return "CRITICAL";
  if ((counts.high ?? 0) > 0) return "HIGH";
  if ((counts.medium ?? 0) > 0) return "MEDIUM";
  if ((counts.low ?? 0) > 0) return "LOW";
  return "CLEAN";
}

function fmtTime(d: Date): string {
  return d.toISOString().slice(11, 23);
}

// ── sub-components ───────────────────────────────────────────────────────────

function SpinChar() {
  const FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"];
  const [f, setF] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setF((x) => (x + 1) % FRAMES.length), 120);
    return () => clearInterval(t);
  }, []);
  return <span className="text-primary text-base select-none">{FRAMES[f]}</span>;
}

function MetricCard({
  title,
  value,
  subtext,
  valueColor = "text-primary",
}: {
  title: string;
  value: React.ReactNode;
  subtext?: React.ReactNode;
  valueColor?: string;
}) {
  return (
    <div className="border border-outline-variant bg-surface-container-lowest p-4 relative overflow-hidden">
      <div className="text-[10px] font-extrabold tracking-[0.1em] text-outline-variant mb-2 select-none">
        ┌─ {title} ─┐
      </div>
      <div className={`text-[24px] font-bold leading-tight ${valueColor}`}>
        {value}
      </div>
      {subtext && (
        <div className="mt-2 text-[10px] font-mono text-on-surface-variant/60">
          {subtext}
        </div>
      )}
    </div>
  );
}

function ThreatGauge({ violations }: { violations: Record<string, number> }) {
  const level = deriveThreatLevel(violations);
  const segCount = { CRITICAL: 7, HIGH: 5, MEDIUM: 3, LOW: 1, CLEAN: 0 }[level] ?? 0;
  const barColor =
    level === "CRITICAL" || level === "HIGH"
      ? "bg-terminal-error"
      : level === "MEDIUM"
      ? "bg-tertiary"
      : level === "LOW"
      ? "bg-secondary"
      : "bg-surface-container-high";
  const textColor =
    level === "CRITICAL" || level === "HIGH"
      ? "text-terminal-error"
      : level === "MEDIUM"
      ? "text-tertiary"
      : level === "LOW"
      ? "text-secondary"
      : "text-on-surface-variant";

  return (
    <div>
      <div className={`text-[20px] font-bold ${textColor}`}>{level}</div>
      <div className="mt-2 flex gap-0.5">
        {Array.from({ length: 10 }, (_, i) => (
          <div
            key={i}
            className={`h-3 w-2 ${
              i < segCount ? barColor : "bg-surface-container-highest"
            } ${i === segCount - 1 && segCount > 0 ? "animate-pulse" : ""}`}
          />
        ))}
      </div>
    </div>
  );
}

function ChecksPassedBar({ score }: { score: number }) {
  return (
    <div>
      <div className="text-[24px] font-bold text-secondary leading-tight">
        {score.toFixed(1)}%
      </div>
      <div className="mt-2 h-2 w-full bg-surface-container-highest flex overflow-hidden">
        <div className="h-full bg-secondary" style={{ width: `${Math.min(score, 100)}%` }} />
        <div className="h-full flex-1 bg-surface-container-low" />
      </div>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const s = severity.toLowerCase();
  const color =
    s === "critical" || s === "high"
      ? "text-terminal-error"
      : s === "medium"
      ? "text-tertiary"
      : "text-on-surface-variant";
  return (
    <span className={`font-mono text-[10px] font-bold ${color}`}>
      [{s.toUpperCase().padEnd(8)}]
    </span>
  );
}

function FindingRow({
  finding,
  defaultOpen,
}: {
  finding: ComplianceFinding;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen || false);
  return (
    <div className="border-b border-outline-variant/40">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-container-high transition-colors text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <SeverityBadge severity={finding.severity} />
          <div className="min-w-0">
            <p className="text-[12px] text-on-surface truncate">{finding.message}</p>
            <p className="text-[10px] text-on-surface-variant truncate mt-0.5">
              {finding.file_path}
              {finding.line ? `:${finding.line}` : ""}
            </p>
          </div>
        </div>
        <span className="text-on-surface-variant ml-3 shrink-0 text-[10px]">
          {open ? "[-]" : "[+]"}
        </span>
      </button>
      {open && (
        <div className="px-4 pb-3 pt-1 border-t border-outline-variant/30 space-y-2">
          {finding.snippet && (
            <pre className="text-[11px] font-mono text-on-surface-variant bg-surface-container-lowest border border-outline-variant p-2 overflow-x-auto mt-2">
              {finding.snippet}
            </pre>
          )}
          {finding.suggestion && (
            <div className="flex items-start gap-2 text-[11px] text-on-surface-variant mt-1">
              <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0 text-tertiary" />
              <span>{finding.suggestion}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TimelineEntry({
  step,
  index,
  scanStart,
}: {
  step: ComplianceStep;
  index: number;
  scanStart: number | null;
}) {
  const hasFindings = step.findings && step.findings.length > 0;
  const isThreat = step.action === "finding" || hasFindings;
  const level = LEVEL_MAP[step.action] ?? {
    label: "[ INFO     ]",
    color: "text-on-surface-variant",
  };
  const ts = scanStart
    ? fmtTime(new Date(scanStart + index * 1500))
    : fmtTime(new Date());

  return (
    <div
      className={`flex gap-4 items-start text-[11px] py-2 px-3 border-b border-outline-variant/20 last:border-0 ${
        isThreat ? "bg-terminal-error/5" : ""
      }`}
    >
      <span className="text-outline-variant shrink-0 tabular-nums font-mono">{ts}</span>
      <span className={`shrink-0 font-bold font-mono ${level.color}`}>
        {level.label}
      </span>
      <div className="flex-1 min-w-0">
        {step.message && (
          <span className={isThreat ? "text-terminal-error" : "text-on-surface"}>
            {step.message}
          </span>
        )}
        {step.check_type && step.check_type !== "_overall" && (
          <span className="ml-2 text-[10px] text-tertiary">
            [{step.check_type.toUpperCase()}]
          </span>
        )}
        {step.tool_name && (
          <span className="ml-2 text-[10px] text-on-surface-variant font-mono">
            {step.tool_name}
          </span>
        )}
        {step.tool_summary && (
          <span className="ml-1 text-[10px] text-outline font-mono">
            · {step.tool_summary}
          </span>
        )}
        {hasFindings &&
          step.findings.map((f, i) => (
            <div
              key={i}
              className="mt-1 pl-3 border-l-2 border-terminal-error/40 text-[10px] text-terminal-error"
            >
              {f.file_path}
              {f.line ? `:${f.line}` : ""}{" "}
              <span className="text-on-surface-variant">· {f.message}</span>
            </div>
          ))}
      </div>
    </div>
  );
}

// ── main page ────────────────────────────────────────────────────────────────

export default function Compliance() {
  const { projectPath, projectName } = useProjectContext();
  const [checks, setChecks] = useState<ComplianceCheckType[]>([]);
  const [checksLoading, setChecksLoading] = useState(true);
  const [selectedChecks, setSelectedChecks] = useState<Set<string>>(new Set());
  const [lastReport, setLastReport] = useState<ComplianceReport | null>(null);

  const [isScanning, setIsScanning] = useState(false);
  const [steps, setSteps] = useState<ComplianceStep[]>([]);
  const [liveViolations, setLiveViolations] = useState(0);
  const [currentCheck, setCurrentCheck] = useState<string>("");
  const [streamError, setStreamError] = useState<string>("");
  const [scanStartTime, setScanStartTime] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timelineRef = useRef<HTMLDivElement>(null);

  const [reportData, setReportData] = useState<ComplianceReport | null>(null);
  const [showFindings, setShowFindings] = useState(false);
  const [showStepLog, setShowStepLog] = useState(false);

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

  useEffect(() => {
    if (!projectName) return;
    getComplianceReport(projectName)
      .then((r) => { if (r) setLastReport(r); })
      .catch(() => {});
  }, [projectName]);

  useEffect(() => {
    if (timelineRef.current) {
      timelineRef.current.scrollTop = timelineRef.current.scrollHeight;
    }
  }, [steps]);

  const handleStartScan = async (all: boolean) => {
    if (!projectPath || !projectName) return;
    const checksToRun = all ? checks.map((c) => c.id) : Array.from(selectedChecks);
    if (checksToRun.length === 0) return;

    setIsScanning(true);
    setSteps([]);
    setLiveViolations(0);
    setReportData(null);
    setStreamError("");
    setScanStartTime(Date.now());

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await startComplianceScanStream(
        projectName,
        projectPath,
        checksToRun,
        (step) => {
          setSteps((prev) => [...prev, step]);
          setLiveViolations((prev) => prev + (step.findings?.length || 0));
          if (step.check_type && step.check_type !== "_overall")
            setCurrentCheck(step.check_type);
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
    } catch (err) {
      if (err instanceof Error && err.name !== "AbortError")
        setStreamError(err.message);
      setIsScanning(false);
      setCurrentCheck("");
    }
  };

  const handleAbort = () => {
    abortRef.current?.abort();
    abortRef.current = null;
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

  // Derive scanned file status from steps or report violations
  const scannedFileStatus = useMemo(() => {
    const fileMap = new Map<string, "flag" | "warn" | "clean">();
    const source = reportData ? reportData.violations : steps.flatMap((s) => s.findings || []);
    for (const f of source) {
      const sev = f.severity.toLowerCase();
      const current = fileMap.get(f.file_path);
      if (sev === "critical" || sev === "high") {
        fileMap.set(f.file_path, "flag");
      } else if (sev === "medium" && current !== "flag") {
        fileMap.set(f.file_path, "warn");
      } else if (!current) {
        fileMap.set(f.file_path, "clean");
      }
    }
    return Array.from(fileMap.entries()).slice(0, 8).map(([file, status]) => ({ file, status }));
  }, [steps, reportData]);

  // ── No project ────────────────────────────────────────────────────────────

  if (!projectPath) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center h-full font-mono text-on-surface-variant">
        <FolderOpen className="w-10 h-10 mb-4 opacity-20" />
        <p className="text-[11px] uppercase tracking-[0.1em]">
          -- NO_PROJECT_SELECTED --
        </p>
        <p className="text-[10px] mt-2 text-outline">
          select a project to run compliance checks
        </p>
      </div>
    );
  }

  // ── Shared: secondary panels ──────────────────────────────────────────────

  const SecondaryPanels = (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* SYSTEM_CONTEXT */}
      <div className="border border-outline-variant bg-surface-container-lowest">
        <div className="px-4 py-2 border-b border-outline-variant bg-surface-container text-[10px] font-extrabold tracking-[0.1em] text-on-surface uppercase">
          ┌─ SYSTEM_CONTEXT ─┐
        </div>
        <div className="p-4 font-mono text-[11px] text-on-surface-variant space-y-1.5">
          <div>
            <span className="text-primary">$</span>{" "}
            SCAN_MODE: DEEP_RECURSION
          </div>
          <div>
            <span className="text-primary">$</span>{" "}
            TARGET_CHECKS:{" "}
            {currentCheck
              ? currentCheck.toUpperCase()
              : isScanning
              ? "ALL_CHECKS"
              : `${selectedChecks.size}_SELECTED`}
          </div>
          <div>
            <span className="text-primary">$</span>{" "}
            PROJECT: {projectName?.toUpperCase() ?? "—"}
          </div>
          <div>
            <span className="text-primary">$</span>{" "}
            FINDINGS:{" "}
            <span
              className={
                liveViolations > 0 ? "text-terminal-error" : "text-secondary"
              }
            >
              {liveViolations}
            </span>
          </div>
          <div className="pt-3 space-y-1.5">
            <div>
              [{"█".repeat(isScanning ? 7 : reportData ? 10 : 3)}
              {"░".repeat(isScanning ? 3 : reportData ? 0 : 7)}] AGENT_01{" "}
              (
              {isScanning
                ? "ACTIVE"
                : reportData
                ? "COMPLETE"
                : "IDLE"}
              )
            </div>
          </div>
        </div>
      </div>

      {/* LAST_SCANNED_ENTITIES */}
      <div className="border border-outline-variant bg-surface-container-lowest flex flex-col">
        <div className="px-4 py-2 border-b border-outline-variant bg-surface-container text-[10px] font-extrabold tracking-[0.1em] text-on-surface uppercase">
          ┌─ LAST_SCANNED_ENTITIES ─┐
        </div>
        <div className="p-3 font-mono text-[11px] space-y-1 flex-1">
          {scannedFileStatus.length === 0 ? (
            <div className="text-outline text-center py-4 uppercase tracking-[0.08em]">
              {isScanning ? "-- SCANNING IN PROGRESS --" : "-- NO ENTITIES SCANNED --"}
            </div>
          ) : (
            scannedFileStatus.map(({ file, status }, i) => {
              const shortPath =
                file.length > 36 ? ".../" + file.split("/").slice(-2).join("/") : file;
              const statusColor =
                status === "flag"
                  ? "text-terminal-error"
                  : status === "warn"
                  ? "text-tertiary"
                  : "text-secondary";
              const statusLabel =
                status === "flag" ? "[ FLAG  ]" : status === "warn" ? "[ WARN  ]" : "[ CLEAN ]";
              return (
                <div
                  key={i}
                  className="flex justify-between items-center py-1 hover:bg-surface-container-high px-2 -mx-2 transition-colors cursor-default"
                >
                  <span className="text-on-surface-variant truncate flex-1 mr-3">
                    {shortPath}
                  </span>
                  <span className={`shrink-0 font-bold ${statusColor}`}>{statusLabel}</span>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );

  // ── View: Agent Workspace (Scanning) ─────────────────────────────────────

  if (isScanning) {
    const checksDone = steps.filter((s) => s.action === "check_complete").length;

    return (
      <div className="h-full overflow-y-auto p-4 pb-14 font-mono space-y-4">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1 text-[11px] text-on-surface-variant">
          <span>ROOT</span>
          <span className="text-outline-variant mx-1">/</span>
          <span>COMPLIANCE</span>
          <span className="text-outline-variant mx-1">/</span>
          <span className="text-primary">AGENT_COMPLIANCE_SCANNER</span>
          {currentCheck && (
            <span className="ml-2 border border-tertiary/50 text-tertiary text-[10px] px-1.5 py-0.5">
              {currentCheck.toUpperCase()}
            </span>
          )}
        </div>

        {/* Metrics row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard
            title="AGENT_STEPS"
            value={steps.length.toLocaleString()}
            valueColor="text-primary"
            subtext="SYSTEM_ITERATION: ACTIVE"
          />
          <MetricCard
            title="TOTAL_FINDINGS"
            value={liveViolations}
            valueColor={liveViolations > 0 ? "text-terminal-error" : "text-on-surface-variant"}
            subtext={liveViolations > 0 ? "REQUIRES_INTERVENTION" : "CLEAN_SO_FAR"}
          />
          <MetricCard
            title="CHECKS_DONE"
            value={checksDone}
            valueColor="text-secondary"
            subtext={`OF ${selectedChecks.size} SELECTED`}
          />
          <MetricCard
            title="PROCESSING"
            value={<SpinChar />}
            valueColor="text-primary"
            subtext="DEEP_RECURSION_MODE"
          />
        </div>

        {/* Timeline */}
        <div className="border border-outline-variant bg-surface-container-lowest">
          <div className="flex justify-between items-center px-4 py-2.5 border-b border-outline-variant bg-surface-container">
            <span className="text-[11px] font-extrabold tracking-[0.1em] text-on-surface uppercase">
              ┌─ AGENT_REASONING_TIMELINE ─────────┐
            </span>
            <button
              onClick={handleAbort}
              className="bg-terminal-error/10 border border-terminal-error text-terminal-error px-3 py-1 text-[10px] font-extrabold tracking-[0.1em] uppercase hover:bg-terminal-error hover:text-surface transition-colors"
            >
              [ EMERGENCY_STOP ]
            </button>
          </div>
          <div
            ref={timelineRef}
            className="h-[360px] overflow-y-auto"
          >
            {steps.length === 0 ? (
              <div className="flex items-center justify-center py-12 gap-3 text-[12px] text-on-surface-variant">
                <SpinChar />
                <span>agent starting up...</span>
              </div>
            ) : (
              steps.map((step, i) => (
                <TimelineEntry
                  key={i}
                  step={step}
                  index={i}
                  scanStart={scanStartTime}
                />
              ))
            )}
            {/* Live cursor */}
            <div className="flex gap-4 items-center text-[11px] py-2 px-3">
              <span className="text-outline-variant shrink-0 tabular-nums font-mono">
                {fmtTime(new Date())}
              </span>
              <span className="text-primary font-bold font-mono shrink-0">
                [ RUNNING  ]
              </span>
              <span className="text-on-surface">Fetching next task queue...</span>
              <span className="inline-block w-2 h-4 bg-primary cursor-blink ml-1" />
            </div>
          </div>
        </div>

        {SecondaryPanels}
      </div>
    );
  }

  // ── View: Results Report ──────────────────────────────────────────────────

  if (reportData) {
    const r = reportData;

    return (
      <div className="h-full overflow-y-auto p-4 pb-14 font-mono space-y-4">
        {/* Breadcrumb */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 text-[11px] text-on-surface-variant">
            <span>ROOT</span>
            <span className="text-outline-variant mx-1">/</span>
            <span>COMPLIANCE</span>
            <span className="text-outline-variant mx-1">/</span>
            <span className="text-primary">COMPLIANCE_REPORT</span>
          </div>
          <button
            onClick={() => handleStartScan(true)}
            className="border border-primary text-primary text-[10px] px-3 py-1.5 uppercase hover:bg-primary hover:text-on-primary transition-colors flex items-center gap-1.5 font-extrabold tracking-[0.08em]"
          >
            <RefreshCw className="w-3 h-3" />
            [ RE-RUN_SCAN ]
          </button>
        </div>

        {/* Metrics row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard
            title="COMPLIANCE_SCORE"
            value={Math.round(r.compliance_score)}
            valueColor={
              r.compliance_score >= 80
                ? "text-secondary"
                : r.compliance_score >= 50
                ? "text-tertiary"
                : "text-terminal-error"
            }
            subtext={r.passed ? "STATUS: PASS" : "STATUS: FAIL"}
          />
          <MetricCard
            title="TOTAL_FINDINGS"
            value={r.total_violations}
            valueColor={
              r.total_violations > 0 ? "text-terminal-error" : "text-secondary"
            }
            subtext={
              r.total_violations > 0 ? "REQUIRES_INTERVENTION" : "CODEBASE_CLEAN"
            }
          />
          <div className="border border-outline-variant bg-surface-container-lowest p-4 relative overflow-hidden">
            <div className="text-[10px] font-extrabold tracking-[0.1em] text-outline-variant mb-2 select-none">
              ┌─ CHECKS_PASSED ─┐
            </div>
            <ChecksPassedBar score={r.compliance_score} />
          </div>
          <div className="border border-outline-variant bg-surface-container-lowest p-4 relative overflow-hidden">
            <div className="text-[10px] font-extrabold tracking-[0.1em] text-outline-variant mb-2 select-none">
              ┌─ THREAT_LEVEL ─┐
            </div>
            <ThreatGauge violations={r.violation_counts} />
          </div>
        </div>

        {/* Severity breakdown */}
        <div className="border border-outline-variant bg-surface-container-lowest">
          <div className="px-4 py-2 border-b border-outline-variant bg-surface-container text-[10px] font-extrabold tracking-[0.1em] text-on-surface uppercase">
            ┌─ VIOLATIONS_BY_SEVERITY ─┐
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-outline-variant/40">
            {[
              { label: "CRITICAL", key: "critical", color: "text-terminal-error" },
              { label: "HIGH",     key: "high",     color: "text-terminal-error" },
              { label: "MEDIUM",   key: "medium",   color: "text-tertiary" },
              { label: "LOW",      key: "low",      color: "text-on-surface-variant" },
            ].map(({ label, key, color }) => (
              <div key={key} className="p-4 text-center">
                <div className={`text-[28px] font-bold font-mono ${color}`}>
                  {String(r.violation_counts[key] ?? 0).padStart(2, "0")}
                </div>
                <p className="text-[10px] text-on-surface-variant mt-1 uppercase tracking-[0.08em]">
                  {label}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Summary */}
        {r.summary && (
          <div className="tui-border bg-surface-container-low p-4">
            <span className="tui-border-title text-primary">AGENT_SUMMARY</span>
            <p className="text-[12px] text-on-surface-variant leading-6 whitespace-pre-wrap pt-1">
              {r.summary}
            </p>
          </div>
        )}

        {/* Timeline accordion */}
        {r.steps && r.steps.length > 0 && (
          <div className="border border-outline-variant bg-surface-container-lowest overflow-hidden">
            <button
              onClick={() => setShowStepLog(!showStepLog)}
              className="w-full px-4 py-2.5 flex items-center justify-between hover:bg-surface-container-high transition-colors border-b border-outline-variant bg-surface-container"
            >
              <span className="text-[10px] font-extrabold tracking-[0.1em] text-on-surface uppercase">
                ┌─ AGENT_REASONING_TIMELINE ({r.steps.length} STEPS) ─┐
              </span>
              <span className="text-primary text-[10px] font-mono shrink-0">
                {showStepLog ? "[-]" : "[+]"}
              </span>
            </button>
            {showStepLog && (
              <div className="max-h-[400px] overflow-y-auto">
                {r.steps
                  .filter((s) => s.action !== "final" && s.check_type !== "_overall")
                  .map((step, i) => (
                    <TimelineEntry
                      key={i}
                      step={step}
                      index={i}
                      scanStart={scanStartTime}
                    />
                  ))}
              </div>
            )}
          </div>
        )}

        {/* Violations list */}
        <div className="border border-outline-variant bg-surface-container-lowest overflow-hidden">
          <button
            onClick={() => setShowFindings(!showFindings)}
            className="w-full px-4 py-2.5 flex items-center justify-between hover:bg-surface-container-high transition-colors border-b border-outline-variant bg-surface-container"
          >
            <span className="text-[10px] font-extrabold tracking-[0.1em] text-on-surface uppercase">
              ┌─ VIOLATIONS ({r.total_violations}) ─┐
              {r.check_types_ran.length > 0 && (
                <span className="ml-3 font-normal text-outline lowercase tracking-normal">
                  {r.check_types_ran.join(", ")}
                </span>
              )}
            </span>
            <span className="text-primary text-[10px] font-mono shrink-0">
              {showFindings ? "[-]" : "[+]"}
            </span>
          </button>
          {showFindings && (
            <div className="max-h-[400px] overflow-y-auto">
              {r.violations.length === 0 ? (
                <p className="text-[12px] text-secondary text-center py-8 uppercase tracking-[0.1em]">
                  -- CLEAN_CODEBASE --
                </p>
              ) : (
                r.violations.map((finding, idx) => (
                  <FindingRow
                    key={idx}
                    finding={finding}
                    defaultOpen={idx < 3}
                  />
                ))
              )}
            </div>
          )}
        </div>

        {/* Checks performed */}
        <div className="tui-border bg-surface-container-low p-4">
          <span className="tui-border-title text-on-surface-variant">
            CHECKS_PERFORMED
          </span>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {r.check_types_ran.map((ct) => {
              const info = checks.find((c) => c.id === ct);
              return (
                <span
                  key={ct}
                  className="inline-flex items-center gap-1.5 px-2 py-1 text-[10px] bg-surface-container text-on-surface-variant border border-outline-variant font-mono uppercase tracking-[0.06em]"
                >
                  <ShieldCheck className="w-3 h-3 text-secondary" />
                  {info?.name || ct}
                </span>
              );
            })}
          </div>
        </div>

        {SecondaryPanels}
      </div>
    );
  }

  // ── View: Check Selection ─────────────────────────────────────────────────


  return (
    <div className="h-full overflow-y-auto p-4 pb-14 font-mono space-y-4">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1 text-[11px] text-on-surface-variant">
        <span>ROOT</span>
        <span className="text-outline-variant mx-1">/</span>
        <span>COMPLIANCE</span>
        <span className="text-outline-variant mx-1">/</span>
        <span className="text-primary">AGENT_COMPLIANCE_SCANNER</span>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          title="LAST_SCORE"
          value={lastReport ? Math.round(lastReport.compliance_score) : "—"}
          valueColor={
            !lastReport
              ? "text-on-surface-variant"
              : lastReport.compliance_score >= 80
              ? "text-secondary"
              : lastReport.compliance_score >= 50
              ? "text-tertiary"
              : "text-terminal-error"
          }
          subtext={lastReport ? (lastReport.passed ? "STATUS: PASS" : "STATUS: FAIL") : "NO_PRIOR_SCAN"}
        />
        <MetricCard
          title="LAST_VIOLATIONS"
          value={lastReport ? lastReport.total_violations : "—"}
          valueColor={
            !lastReport
              ? "text-on-surface-variant"
              : lastReport.total_violations > 0
              ? "text-terminal-error"
              : "text-secondary"
          }
          subtext={lastReport ? `${lastReport.scanned_files} FILES_SCANNED` : "AWAITING_SCAN"}
        />
        <MetricCard
          title="CHECKS_AVAIL"
          value={checksLoading ? <SpinChar /> : checks.length}
          valueColor="text-primary"
          subtext={`${selectedChecks.size} SELECTED`}
        />
        <div className="border border-outline-variant bg-surface-container-lowest p-4 relative overflow-hidden">
          <div className="text-[10px] font-extrabold tracking-[0.1em] text-outline-variant mb-2 select-none">
            ┌─ THREAT_LEVEL ─┐
          </div>
          <ThreatGauge violations={lastReport?.violation_counts ?? {}} />
        </div>
      </div>

      {/* Error banner */}
      {streamError && (
        <div className="tui-border border-terminal-error bg-surface-container-low p-4">
          <span className="tui-border-title text-terminal-error flex items-center gap-1.5">
            <AlertTriangle className="w-3 h-3" />
            SCAN_ERROR
          </span>
          <p className="text-[11px] text-on-surface-variant pt-1">{streamError}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* Left: check selection */}
        <div className="lg:col-span-8 space-y-4">
          {/* Status panel */}
          {lastReport && (
            <div className="border border-outline-variant bg-surface-container-lowest p-4">
              <div className="flex items-center justify-between">
                <div>
                  <span
                    className={`text-[12px] font-bold ${
                      lastReport.passed ? "text-secondary" : "text-terminal-error"
                    }`}
                  >
                    {lastReport.passed ? "[OK] " : "[ERR] "}LAST_SCAN_{lastReport.passed ? "PASSED" : "FAILED"}
                  </span>
                  <p className="text-[11px] text-on-surface-variant mt-1">
                    score: {lastReport.compliance_score}/100 · {lastReport.total_violations} violation(s) ·{" "}
                    {lastReport.scanned_files} files · {lastReport.steps?.length || 0} steps
                  </p>
                </div>
                <button
                  onClick={() => setReportData(lastReport)}
                  className="text-[10px] text-primary border border-primary/40 px-3 py-1.5 uppercase hover:bg-primary hover:text-on-primary transition-colors font-extrabold tracking-[0.08em]"
                >
                  [ VIEW_REPORT ]
                </button>
              </div>
            </div>
          )}

          {/* Available checks */}
          <div className="border border-outline-variant bg-surface-container-lowest overflow-hidden">
            <div className="px-4 py-2.5 border-b border-outline-variant bg-surface-container text-[10px] font-extrabold tracking-[0.1em] text-on-surface uppercase">
              ┌─ AVAILABLE_CHECKS ─┐
            </div>
            {checksLoading ? (
              <div className="flex items-center justify-center py-12 gap-3 text-[12px] text-on-surface-variant">
                <SpinChar />
                <span>LOADING_CHECKS...</span>
              </div>
            ) : (
              <div className="divide-y divide-outline-variant/30">
                {checks.map((check) => {
                  const sevColor =
                    check.default_severity === "critical" || check.default_severity === "high"
                      ? "text-terminal-error"
                      : check.default_severity === "medium"
                      ? "text-tertiary"
                      : "text-on-surface-variant";
                  return (
                    <label
                      key={check.id}
                      className="flex items-center justify-between px-4 py-2.5 hover:bg-surface-container-high cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <input
                          type="checkbox"
                          checked={selectedChecks.has(check.id)}
                          onChange={() => toggleCheck(check.id)}
                          className="w-3.5 h-3.5 accent-primary shrink-0"
                        />
                        <div className="min-w-0">
                          <p className="text-[12px] text-on-surface">{check.name}</p>
                          <p className="text-[10px] text-on-surface-variant truncate">
                            {check.description}
                          </p>
                        </div>
                      </div>
                      <span className={`text-[10px] font-mono font-bold shrink-0 ml-3 ${sevColor}`}>
                        [{check.default_severity.toUpperCase()}]
                      </span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right: system context + actions */}
        <div className="lg:col-span-4 space-y-4">
          {/* Context panel */}
          <div className="border border-outline-variant bg-surface-container-lowest">
            <div className="px-4 py-2 border-b border-outline-variant bg-surface-container text-[10px] font-extrabold tracking-[0.1em] text-on-surface uppercase">
              ┌─ SYSTEM_CONTEXT ─┐
            </div>
            <div className="p-4 font-mono text-[11px] text-on-surface-variant space-y-1.5">
              <div>
                <span className="text-primary">$</span> SCAN_MODE: DEEP_RECURSION
              </div>
              <div>
                <span className="text-primary">$</span> TARGET_REG:{" "}
                {checks
                  .filter((c) => selectedChecks.has(c.id) && c.category === "privacy")
                  .map((c) => c.id.toUpperCase())
                  .join(", ") || "NONE_SELECTED"}
              </div>
              <div>
                <span className="text-primary">$</span> NODES_ACTIVE:{" "}
                {selectedChecks.size} / {checks.length}
              </div>
              <div className="pt-3 space-y-1.5 text-on-surface-variant">
                <div>[{"█".repeat(3)}{"░".repeat(7)}] AGENT_01 (IDLE)</div>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="space-y-2">
            <button
              onClick={() => handleStartScan(false)}
              disabled={selectedChecks.size === 0}
              className="w-full border border-primary text-primary px-4 py-3 hover:bg-primary hover:text-on-primary transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex justify-between items-center text-[11px] font-extrabold tracking-[0.1em] uppercase"
            >
              <span className="flex items-center gap-2">
                <Play className="w-3.5 h-3.5" />
                RUN_SELECTED ({selectedChecks.size})
              </span>
              <span className="opacity-40 font-normal">[ ENTER ]</span>
            </button>
            <button
              onClick={() => handleStartScan(true)}
              disabled={checks.length === 0}
              className="w-full border border-outline-variant text-on-surface-variant px-4 py-3 hover:bg-surface-container-high hover:text-on-surface transition-colors disabled:opacity-40 flex justify-between items-center text-[11px] font-extrabold tracking-[0.1em] uppercase"
            >
              <span>RUN_ALL ({checks.length})</span>
              <span className="opacity-40 font-normal">[ F5 ]</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
