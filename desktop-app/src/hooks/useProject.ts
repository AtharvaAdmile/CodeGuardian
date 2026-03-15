import { useState, useCallback, useEffect } from "react";
import { indexProject, getIndexStatus, getHealth } from "../lib/api";
import type { IndexStatus, HealthStatus } from "../lib/types";

interface UseProjectReturn {
  projectPath: string | null;
  projectName: string | null;
  isValid: boolean;
  indexJobId: string | null;
  indexStatus: IndexStatus | null;
  healthStatus: HealthStatus | null;
  isLoadingHealth: boolean;
  setProject: (path: string, name: string, isValid: boolean) => void;
  clearProject: () => void;
  refreshHealth: () => Promise<void>;
}

export function useProject(): UseProjectReturn {
  const [projectPath, setProjectPath] = useState<string | null>(null);
  const [projectName, setProjectName] = useState<string | null>(null);
  const [isValid, setIsValid] = useState(false);
  const [indexJobId, setIndexJobId] = useState<string | null>(null);
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [isLoadingHealth, setIsLoadingHealth] = useState(false);

  const refreshHealth = useCallback(async () => {
    setIsLoadingHealth(true);
    try {
      const status = await getHealth();
      setHealthStatus(status);
    } catch (error) {
      console.error("Failed to fetch health:", error);
      setHealthStatus(null);
    } finally {
      setIsLoadingHealth(false);
    }
  }, []);

  useEffect(() => {
    refreshHealth();
    const interval = setInterval(refreshHealth, 30000);
    return () => clearInterval(interval);
  }, [refreshHealth]);

  useEffect(() => {
    if (!indexJobId) return;

    const pollInterval = setInterval(async () => {
      try {
        const status = await getIndexStatus(indexJobId);
        setIndexStatus(status);

        if (status.status === "completed" || status.status === "failed") {
          clearInterval(pollInterval);
        }
      } catch (error) {
        console.error("Failed to poll index status:", error);
      }
    }, 2000);

    return () => clearInterval(pollInterval);
  }, [indexJobId]);

  const setProject = useCallback(
    async (path: string, name: string, valid: boolean) => {
      setProjectPath(path);
      setProjectName(name);
      setIsValid(valid);

      if (!valid) {
        try {
          const result = await indexProject(name, path, false);
          if (result.job_id) {
            setIndexJobId(result.job_id);
          }
        } catch (error) {
          console.error("Failed to index project:", error);
        }
      }
    },
    []
  );

  const clearProject = useCallback(() => {
    setProjectPath(null);
    setProjectName(null);
    setIsValid(false);
    setIndexJobId(null);
    setIndexStatus(null);
  }, []);

  return {
    projectPath,
    projectName,
    isValid,
    indexJobId,
    indexStatus,
    healthStatus,
    isLoadingHealth,
    setProject,
    clearProject,
    refreshHealth,
  };
}
