interface StatusBarProps {
  projectName: string | null;
  isIndexing: boolean;
}

export function StatusBar({ projectName, isIndexing }: StatusBarProps) {
  return (
    <div className="fixed bottom-0 left-64 right-0 h-7 bg-surface-container-lowest border-t border-outline-variant flex items-center px-3 gap-3 text-[11px] font-mono text-on-surface-variant z-40 select-none">
      <span className={isIndexing ? "text-tertiary" : "text-secondary"}>
        INDEX: {isIndexing ? "RUNNING" : "READY"}
      </span>
      <span className="text-outline-variant">|</span>
      <span>PROJECT: {projectName ?? "—"}</span>
      <div className="ml-auto flex items-center gap-3">
        <span>UTF-8</span>
        <span className="text-outline-variant">|</span>
        <span>NORMAL</span>
      </div>
    </div>
  );
}
