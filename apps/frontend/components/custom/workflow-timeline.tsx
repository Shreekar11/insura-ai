"use client";

import React, { useMemo, useRef, useEffect } from "react";
import { 
  Loader2, 
  ChevronDown,
  Sparkles,
  Check,
  ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { WorkflowEvent } from "@/hooks/use-workflow-stream";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { motion, AnimatePresence } from "framer-motion";

interface WorkflowTimelineProps {
  definitionName: string;
  events: WorkflowEvent[];
  isConnected: boolean;
  isComplete: boolean;
}

interface WorkflowStep {
  id: string;
  message: string;
  status: "running" | "completed" | "failed";
  timestamp: string;
  docId?: string;
}

export function WorkflowTimeline({ definitionName, events, isConnected, isComplete }: WorkflowTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Aggregate events into logical steps for in-place updates
  const steps = useMemo(() => {
    const stepMap = new Map<string, WorkflowStep>();
    const orderedKeys: string[] = [];

    events.forEach((event) => {
      const { event_type, data, timestamp } = event;
      const docId = data?.document_id;
      const stageName = data?.stage_name;
      const message = data?.message;
      
      let stepKey = "";

      if (event_type.startsWith("stage:")) {
        stepKey = `${docId}:${stageName}`;
      } else if (event_type === "workflow:progress") {
        // Unique key for progress events to keep them distinct but identifiable by doc
        // We use the first few words of the message to identify the intent (e.g., "Reading document")
        const intent = message?.split(' ').slice(0, 2).join('_');
        stepKey = docId ? `${docId}:progress:${intent}` : `global:progress:${intent}`;
      } else {
        return;
      }

      const status = event_type === "stage:completed" || event_type === "workflow:completed" 
        ? "completed" 
        : (event_type === "stage:failed" || event_type === "workflow:failed" ? "failed" : "running");

      if (!stepMap.has(stepKey)) {
        orderedKeys.push(stepKey);
      }

      stepMap.set(stepKey, {
        id: stepKey,
        message: message || "Processing...",
        status,
        timestamp,
        docId
      });
    });
    
    const finalSteps: WorkflowStep[] = orderedKeys.map(key => ({ ...stepMap.get(key)! }));
    
    for (const step of finalSteps) {
        if (step.id.includes(':progress:')) {
            // Check if there is a later step for the same document
            const stepIndex = finalSteps.indexOf(step);
            const hasLaterStep = finalSteps.slice(stepIndex + 1).some(s => s.docId === step.docId && !s.id.includes(':progress:'));
            if (hasLaterStep && step.status === 'running') {
                step.status = 'completed';
            }
        }
    }

    return finalSteps;
  }, [events]);

  // Auto-scroll logic
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [steps]);

  const latestStep = steps[steps.length - 1];
  const latestMessage = latestStep?.message || (isComplete ? "Workflow finished" : "Initializing...");

  return (
    <div className="w-full max-w-2xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="w-full group relative flex items-center justify-between gap-4 px-6 py-5 bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-3xl shadow-sm hover:shadow-md transition-all duration-300">
            <div className="flex items-center gap-4 relative z-10 shrink-0">
              <div className="relative">
                {isComplete ? (
                  <div className="bg-amber-500/10 p-2.5 rounded-full">
                    <Sparkles className="size-5 text-amber-500" />
                  </div>
                ) : (
                  <div className="bg-amber-500/5 p-2.5 rounded-full ring-1 ring-amber-500/10">
                    <Loader2 className="size-5 text-amber-500 animate-spin" />
                  </div>
                )}
              </div>
              
              <div className="flex flex-col items-start gap-1">
                <span className="text-sm font-bold text-zinc-900 dark:text-zinc-100 tracking-tight text-left">
                  {isComplete ? `${definitionName} Successfully Executed` : `${definitionName} Running`}
                </span>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 font-medium text-left">
                  {latestMessage}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-4 relative z-10 shrink-0">
              <div className="flex items-center gap-1.5 text-zinc-400 font-medium text-xs">
                {steps.length} Steps
                <ChevronDown className="size-4 group-data-[state=open]:rotate-180 transition-transform duration-300 ml-1" />
              </div>
            </div>
          </button>
        </DropdownMenuTrigger>

        <DropdownMenuContent 
          align="center" 
          sideOffset={12} 
          className="w-[min(calc(100vw-2rem),40rem)] p-8 bg-white/95 dark:bg-zinc-950/95 backdrop-blur-xl border-zinc-200 dark:border-zinc-800 rounded-[2rem] shadow-2xl overflow-hidden"
          onSelect={(e) => e.preventDefault()}
        >
          <div className="relative">
            <div 
              ref={scrollRef}
              className="relative flex flex-col gap-6 max-h-[450px] overflow-y-auto pr-2 scrollbar-none"
            >
              <div className="absolute left-[11px] top-3 bottom-3 w-px bg-zinc-100 dark:bg-zinc-800" />

              <AnimatePresence initial={false}>
                {steps.map((step, index) => {
                  const isRunning = step.status === "running";
                  const isCompleted = step.status === "completed";
                  const isFailed = step.status === "failed";

                  return (
                    <motion.div
                      key={step.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="relative flex items-center gap-4 group"
                    >
                      <div className="relative z-10">
                        {isCompleted ? (
                          <div className="size-6 rounded-full bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 flex items-center justify-center">
                            <Check className="size-3.5 text-zinc-400 stroke-[3]" />
                          </div>
                        ) : isRunning ? (
                          <div className="size-6 rounded-full bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 flex items-center justify-center">
                            <div className="size-2 rounded-full bg-blue-500 animate-pulse" />
                          </div>
                        ) : (
                          <div className="size-6 rounded-full bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800 flex items-center justify-center">
                            <div className="size-1.5 rounded-full bg-red-500" />
                          </div>
                        )}
                      </div>

                      <div className="flex-1 flex items-center justify-between group-hover:bg-zinc-50/50 dark:hover:bg-zinc-900/30 p-2 -m-2 rounded-xl transition-colors">
                        <span className={cn(
                          "text-sm font-medium transition-colors duration-300",
                          isCompleted ? "text-zinc-500 dark:text-zinc-400" : (isRunning ? "text-blue-600 dark:text-blue-400 font-semibold" : "text-zinc-900 dark:text-zinc-100"),
                        )}>
                          {step.message}
                        </span>
                        
                        {isCompleted && index > 1 && (
                          <button className="flex items-center gap-1.5 px-3 py-1 bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg text-[10px] font-bold text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors">
                            View Output
                            <ArrowRight className="size-3" />
                          </button>
                        )}
                      </div>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            </div>
          </div>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
