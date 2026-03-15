import { getHealthColor } from "../../lib/constants";

interface ConfidenceBarProps {
  score: number;
  showLabel?: boolean;
  size?: "sm" | "md" | "lg";
}

export function ConfidenceBar({ score, showLabel = true, size = "md" }: ConfidenceBarProps) {
  const clampedScore = Math.max(0, Math.min(1, score));
  const percentage = Math.round(clampedScore * 100);
  const color = getHealthColor(clampedScore);

  const heightClasses = {
    sm: "h-1",
    md: "h-2",
    lg: "h-3",
  };

  return (
    <div className="flex items-center gap-2">
      <div className={`flex-1 bg-bg-tertiary rounded-full overflow-hidden ${heightClasses[size]}`}>
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${percentage}%`, backgroundColor: color }}
        />
      </div>
      {showLabel && (
        <span className="text-xs font-mono" style={{ color }}>
          {percentage}%
        </span>
      )}
    </div>
  );
}
