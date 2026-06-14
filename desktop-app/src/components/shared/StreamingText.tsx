interface StreamingTextProps {
  text: string;
  className?: string;
}

export function StreamingText({ text, className = "" }: StreamingTextProps) {
  return (
    <span className={`font-mono ${className}`}>
      {text}
      <span className="animate-blink text-accent-green text-shadow-glow">█</span>
    </span>
  );
}
