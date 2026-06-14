interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center font-mono">
      <div className="text-text-muted text-xs mb-4 uppercase tracking-widest">
        -- NULL --
      </div>
      <div className="border border-border p-6 space-y-3 max-w-sm">
        <p className="text-text-primary text-sm uppercase tracking-wider">{title}</p>
        {description && (
          <p className="text-text-muted text-xs leading-relaxed">{description}</p>
        )}
        {action && <div className="pt-2">{action}</div>}
      </div>
    </div>
  );
}
