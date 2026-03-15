import { Badge } from "./Badge";

interface RiskBadgeProps {
  risk: "high" | "medium" | "low";
  score?: number;
}

export function RiskBadge({ risk, score }: RiskBadgeProps) {
  const variantMap = {
    high: "error",
    medium: "warning",
    low: "success",
  } as const;

  const label = risk.charAt(0).toUpperCase() + risk.slice(1);

  return (
    <Badge variant={variantMap[risk]} size="sm">
      {label}
      {score !== undefined && ` (${Math.round(score * 100)}%)`}
    </Badge>
  );
}
