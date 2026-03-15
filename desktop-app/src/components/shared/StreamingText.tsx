interface StreamingTextProps {
  text: string;
  className?: string;
}

export function StreamingText({ text, className = "" }: StreamingTextProps) {
  return (
    <div className={`relative ${className}`}>
      <span>{text}</span>
      <span className="animate-blink inline-block w-0.5 h-4 bg-accent-blue ml-0.5 align-middle" />
    </div>
  );
}
