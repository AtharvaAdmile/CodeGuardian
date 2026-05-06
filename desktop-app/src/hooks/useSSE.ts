import { useState, useRef, useCallback, useEffect } from "react";
import { API_BASE } from "../lib/constants";
import type { SourceRef, DecisionRef, ExpertRef } from "../lib/types";

interface SSEState {
  chunks: string[];
  sources: SourceRef[];
  decisions: DecisionRef[];
  experts: ExpertRef[];
  isStreaming: boolean;
  error: string | null;
  confidence: number;
}

interface UseSSEReturn extends SSEState {
  sendQuestion: (projectId: string, question: string) => Promise<void>;
  reset: () => void;
}

export function useSSE(): UseSSEReturn {
  const [chunks, setChunks] = useState<string[]>([]);
  const [sources, setSources] = useState<SourceRef[]>([]);
  const [decisions, setDecisions] = useState<DecisionRef[]>([]);
  const [experts, setExperts] = useState<ExpertRef[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confidence, setConfidence] = useState(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setChunks([]);
    setSources([]);
    setDecisions([]);
    setExperts([]);
    setIsStreaming(false);
    setError(null);
    setConfidence(0);
  }, []);

  const sendQuestion = useCallback(
    async (projectId: string, question: string) => {
      reset();
      setIsStreaming(true);
      setError(null);

      abortControllerRef.current = new AbortController();

      try {
        const response = await fetch(`${API_BASE}/api/ask/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            project_id: projectId,
            question,
            conversation_history: [],
          }),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        if (!response.body) {
          throw new Error("No response body");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();

          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              try {
                const event = JSON.parse(data);

                switch (event.type) {
                  case "source":
                    if (event.source) {
                      setSources((prev) => [...prev, event.source]);
                    }
                    break;
                  case "chunk":
                    if (event.content) {
                      setChunks((prev) => [...prev, event.content]);
                    }
                    break;
                  case "metadata":
                    if (event.decisions) {
                      setDecisions(event.decisions);
                    }
                    if (event.experts) {
                      setExperts(event.experts);
                    }
                    break;
                  case "done":
                    setIsStreaming(false);
                    break;
                  case "error":
                    setError(event.message || "Unknown error");
                    setIsStreaming(false);
                    break;
                }
              } catch (e) {
                console.warn("Failed to parse SSE event:", e);
              }
            }
          }
        }

        setIsStreaming(false);
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError((err as Error).message);
          setIsStreaming(false);
        }
      }
    },
    [reset]
  );

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return {
    chunks,
    sources,
    decisions,
    experts,
    isStreaming,
    error,
    confidence,
    sendQuestion,
    reset,
  };
}
