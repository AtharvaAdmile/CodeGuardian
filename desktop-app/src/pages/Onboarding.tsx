import { useState } from "react";
import { GraduationCap, BookOpen, Lightbulb, Eye, ArrowRight, User } from "lucide-react";
import { useProjectContext } from "../App";
import { generateOnboardingPath } from "../lib/api";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import { Badge } from "../components/shared/Badge";
import type { LearningStepSchema } from "../lib/types";

const actionIcons = {
  read: BookOpen,
  understand: Lightbulb,
  review: Eye,
};

const actionColors = {
  read: "bg-accent-blue/20 text-accent-blue border-accent-blue/30",
  understand: "bg-accent-green/20 text-accent-green border-accent-green/30",
  review: "bg-accent-amber/20 text-accent-amber border-accent-amber/30",
};

export default function Onboarding() {
  const { projectName } = useProjectContext();
  const [taskDescription, setTaskDescription] = useState("");
  const [learningPath, setLearningPath] = useState<LearningStepSchema[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    if (!taskDescription.trim() || !projectName) return;

    setIsLoading(true);
    setError(null);

    try {
      const result = await generateOnboardingPath(projectName, taskDescription);
      if (result.error) {
        setError(result.error);
      } else {
        setLearningPath(result.learning_path);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-6 border-b border-border">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <GraduationCap className="w-6 h-6 text-accent-violet" />
          Onboarding Copilot
        </h1>
        <p className="text-text-secondary mt-1">
          Describe your task and get a personalized learning path
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl mx-auto space-y-6">
          <div className="bg-bg-secondary border border-border rounded-xl p-6">
            <label className="block text-sm font-medium mb-2">
              Describe your task
            </label>
            <textarea
              value={taskDescription}
              onChange={(e) => setTaskDescription(e.target.value)}
              placeholder="e.g., Implement rate limiting on the payments API endpoint"
              className="w-full h-32 bg-bg-tertiary border border-border rounded-lg px-4 py-3 text-text-primary placeholder-text-muted resize-none focus:outline-none focus:border-accent-blue"
            />
            <button
              onClick={handleGenerate}
              disabled={!taskDescription.trim() || isLoading}
              className="mt-4 px-6 py-2.5 bg-accent-blue hover:bg-accent-blue/80 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors flex items-center gap-2"
            >
              {isLoading ? (
                <>
                  <LoadingSpinner size="sm" />
                  Generating Learning Path...
                </>
              ) : (
                <>
                  Generate Learning Path
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="bg-accent-red/20 border border-accent-red/30 rounded-lg p-4 text-accent-red">
              {error}
            </div>
          )}

          {isLoading && (
            <div className="space-y-4">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="bg-bg-secondary border border-border rounded-xl p-6 animate-pulse"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-full bg-bg-tertiary" />
                    <div className="flex-1 space-y-2">
                      <div className="h-4 bg-bg-tertiary rounded w-1/4" />
                      <div className="h-3 bg-bg-tertiary rounded w-3/4" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {learningPath.length > 0 && !isLoading && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Your Learning Path</h2>
              
              <div className="relative">
                <div className="absolute left-5 top-0 bottom-0 w-0.5 bg-border" />
                
                {learningPath.map((step, idx) => {
                  const IconComponent = actionIcons[step.action] || BookOpen;
                  return (
                    <div key={idx} className="relative flex gap-4 pb-8">
                      <div className="relative z-10 flex-shrink-0 w-10 h-10 rounded-full bg-bg-secondary border-2 border-accent-blue flex items-center justify-center">
                        <IconComponent className="w-5 h-5 text-accent-blue" />
                      </div>
                      
                      <div className="flex-1 bg-bg-secondary border border-border rounded-xl p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <span className={`px-2 py-1 rounded text-xs font-medium border ${actionColors[step.action]}`}>
                            {step.action.toUpperCase()}
                          </span>
                          <span className="font-mono text-sm text-text-muted">
                            {step.file_path}
                          </span>
                        </div>
                        
                        <h3 className="font-semibold text-text-primary mb-2">
                          {step.focus_area}
                        </h3>
                        
                        <p className="text-sm text-text-secondary mb-3">
                          {step.context}
                        </p>
                        
                        {step.related_decisions.length > 0 && (
                          <div className="flex flex-wrap gap-1 mb-3">
                            {step.related_decisions.map((dec, i) => (
                              <Badge key={i} variant="default" size="sm">
                                {dec}
                              </Badge>
                            ))}
                          </div>
                        )}
                        
                        {step.expert_contact && (
                          <div className="flex items-center gap-2 text-sm text-text-muted pt-3 border-t border-border">
                            <User className="w-4 h-4" />
                            <span>Talk to {step.expert_contact}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              <button className="w-full px-6 py-3 bg-accent-green hover:bg-accent-green/80 rounded-lg text-white font-medium transition-colors flex items-center justify-center gap-2">
                Start Exploring
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
