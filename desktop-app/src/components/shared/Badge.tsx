

interface BadgeProps {
  variant?: "default" | "success" | "warning" | "error" | "info";
  size?: "sm" | "md";
  children: React.ReactNode;
}

export function Badge({ variant = "default", size = "md", children }: BadgeProps) {
  const baseClasses = "inline-flex items-center font-medium rounded-full";
  
  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm";
  
  const variantClasses: Record<string, string> = {
    default: "bg-bg-tertiary text-text-secondary border border-border",
    success: "bg-accent-green/20 text-accent-green border border-accent-green/30",
    warning: "bg-accent-amber/20 text-accent-amber border border-accent-amber/30",
    error: "bg-accent-red/20 text-accent-red border border-accent-red/30",
    info: "bg-accent-blue/20 text-accent-blue border border-accent-blue/30",
  };

  return (
    <span className={`${baseClasses} ${sizeClasses} ${variantClasses[variant]}`}>
      {children}
    </span>
  );
}

interface StatusDotProps {
  status: "healthy" | "degraded" | "unhealthy" | "running" | "completed" | "failed";
  size?: "sm" | "md" | "lg";
}

export function StatusDot({ status, size = "md" }: StatusDotProps) {
  const sizeClasses = {
    sm: "w-2 h-2",
    md: "w-2.5 h-2.5",
    lg: "w-3 h-3",
  };

  const colorClasses: Record<string, string> = {
    healthy: "bg-accent-green",
    degraded: "bg-accent-amber",
    unhealthy: "bg-accent-red",
    running: "bg-accent-blue animate-pulse",
    completed: "bg-accent-green",
    failed: "bg-accent-red",
  };

  return (
    <span className={`${sizeClasses[size]} ${colorClasses[status]} rounded-full inline-block`} />
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  const variantMap: Record<string, BadgeProps["variant"]> = {
    critical: "error",
    high: "error",
    medium: "warning",
    low: "default",
  };

  return (
    <Badge variant={variantMap[severity] || "default"} size="sm">
      {severity.toUpperCase()}
    </Badge>
  );
}
