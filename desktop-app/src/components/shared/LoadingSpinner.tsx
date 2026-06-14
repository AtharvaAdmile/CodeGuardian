interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"];

export function LoadingSpinner({ size = "md", className = "" }: LoadingSpinnerProps) {
  const sizeClass = { sm: "text-xs", md: "text-sm", lg: "text-base" }[size];

  return (
    <span
      className={`font-mono text-accent-green animate-spin inline-block ${sizeClass} ${className}`}
      style={{ animationDuration: "0.7s" }}
      aria-label="Loading"
    >
      {FRAMES[0]}
    </span>
  );
}

export function LoadingOverlay({ message = "LOADING..." }: { message?: string }) {
  return (
    <div className="absolute inset-0 bg-bg-primary/90 flex items-center justify-center z-50">
      <div className="border border-border p-6 text-center space-y-3">
        <div className="text-accent-green text-2xl animate-spin" style={{ animationDuration: "0.7s" }}>
          ⣾
        </div>
        <p className="text-text-secondary text-xs uppercase tracking-widest">{message}</p>
      </div>
    </div>
  );
}
