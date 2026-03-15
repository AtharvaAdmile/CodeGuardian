interface CodeBlockProps {
  code: string;
  language?: string;
  showLineNumbers?: boolean;
  maxHeight?: string;
}

export function CodeBlock({
  code,
  language = "text",
  showLineNumbers = true,
  maxHeight = "400px",
}: CodeBlockProps) {
  const lines = code.split("\n");

  const languageColors: Record<string, string> = {
    python: "text-accent-blue",
    javascript: "text-accent-yellow",
    typescript: "text-accent-cyan",
    jsx: "text-accent-pink",
    tsx: "text-accent-pink",
    text: "text-text-secondary",
  };

  return (
    <div
      className="bg-bg-secondary rounded-lg border border-border overflow-auto"
      style={{ maxHeight }}
    >
      <div className="flex">
        {showLineNumbers && (
          <div className="flex-shrink-0 py-3 px-3 bg-bg-tertiary border-r border-border text-right select-none">
            {lines.map((_, i) => (
              <div key={i} className="text-text-muted text-xs font-mono leading-5">
                {i + 1}
              </div>
            ))}
          </div>
        )}
        <pre className="flex-1 p-3 overflow-x-auto">
          <code className={`text-sm font-mono leading-5 ${languageColors[language] || languageColors.text}`}>
            {lines.map((line, i) => (
              <div key={i}>{line || " "}</div>
            ))}
          </code>
        </pre>
      </div>
    </div>
  );
}
