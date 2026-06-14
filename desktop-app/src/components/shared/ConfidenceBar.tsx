import { getHealthColor } from "../../lib/constants";

interface ConfidenceBarProps {
  score: number;
  showLabel?: boolean;
  size?: "sm" | "md" | "lg";
}

export function ConfidenceBar({ score, showLabel = true, size = "md" }: ConfidenceBarProps) {
  const clamped = Math.max(0, Math.min(1, score));
  const pct = Math.round(clamped * 100);
  const color = getHealthColor(clamped);

  // ASCII bar: total 20 chars
  const total  = size === "sm" ? 12 : size === "lg" ? 24 : 16;
  const filled = Math.round((pct / 100) * total);
  const empty  = total - filled;
  const bar    = "█".repeat(filled) + "░".repeat(empty);

  return (
    <div className="flex items-center gap-2 font-mono">
      <span className="text-xs" style={{ color }}>
        [{bar}]
      </span>
      {showLabel && (
        <span className="text-[10px]" style={{ color }}>
          {pct}%
        </span>
      )}
    </div>
  );
}
