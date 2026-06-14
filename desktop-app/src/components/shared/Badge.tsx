interface BadgeProps {
  variant?: "default" | "success" | "warning" | "error" | "info";
  size?: "sm" | "md";
  children: React.ReactNode;
}

const VARIANT_CLASSES: Record<string, string> = {
  default: "text-text-muted border-border",
  success: "text-accent-green border-accent-green",
  warning: "text-accent-amber border-accent-amber",
  error:   "text-accent-red   border-accent-red",
  info:    "text-accent-cyan  border-accent-cyan",
};

const VARIANT_GLOW: Record<string, string> = {
  default: "",
  success: "drop-shadow-[0_0_4px_rgba(51,255,0,0.5)]",
  warning: "drop-shadow-[0_0_4px_rgba(255,176,0,0.5)]",
  error:   "drop-shadow-[0_0_4px_rgba(255,51,51,0.5)]",
  info:    "drop-shadow-[0_0_4px_rgba(0,255,255,0.5)]",
};

export function Badge({ variant = "default", size = "md", children }: BadgeProps) {
  const sizeClass = size === "sm" ? "text-[10px] px-1 py-px" : "text-xs px-1.5 py-0.5";
  const colors = VARIANT_CLASSES[variant] ?? VARIANT_CLASSES.default;
  const glow   = VARIANT_GLOW[variant] ?? "";

  return (
    <span
      className={`inline-flex items-center border font-mono uppercase tracking-wider ${sizeClass} ${colors} ${glow}`}
    >
      [{children}]
    </span>
  );
}

interface StatusDotProps {
  status: "healthy" | "degraded" | "unhealthy" | "running" | "completed" | "failed";
  size?: "sm" | "md" | "lg";
}

const STATUS_CHAR: Record<string, string> = {
  healthy:   "[OK]",
  degraded:  "[WARN]",
  unhealthy: "[ERR]",
  running:   "[...]",
  completed: "[OK]",
  failed:    "[ERR]",
};

const STATUS_COLOR: Record<string, string> = {
  healthy:   "text-accent-green",
  degraded:  "text-accent-amber",
  unhealthy: "text-accent-red",
  running:   "text-accent-green animate-blink",
  completed: "text-accent-green",
  failed:    "text-accent-red",
};

const STATUS_SIZE: Record<string, string> = {
  sm: "text-[9px]",
  md: "text-[10px]",
  lg: "text-xs",
};

export function StatusDot({ status, size = "md" }: StatusDotProps) {
  return (
    <span className={`font-mono ${STATUS_SIZE[size]} ${STATUS_COLOR[status]}`}>
      {STATUS_CHAR[status]}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  const variantMap: Record<string, BadgeProps["variant"]> = {
    critical: "error",
    high:     "error",
    medium:   "warning",
    low:      "default",
  };

  return (
    <Badge variant={variantMap[severity] ?? "default"} size="sm">
      {severity.toUpperCase()}
    </Badge>
  );
}
