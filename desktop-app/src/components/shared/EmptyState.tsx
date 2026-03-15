import { FileQuestion } from "lucide-react";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      {icon || <FileQuestion className="w-12 h-12 text-text-muted mb-4" />}
      <h3 className="text-text-primary font-medium mb-2">{title}</h3>
      {description && (
        <p className="text-text-secondary text-sm mb-4 max-w-sm">{description}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
