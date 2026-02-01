"use client";

import React, { useMemo, useRef, useEffect, useState } from "react";
import { 
  Loader2, 
  ChevronDown,
  Sparkles,
  Check,
  ArrowRight,
  ChevronUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { WorkflowEvent } from "@/hooks/use-workflow-stream";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ExtractionOutputSidebar } from "@/components/custom/extraction-output-sidebar";

interface WorkflowTimelineProps {
  definitionName: string;
  events: WorkflowEvent[];
  isConnected: boolean;
  isComplete: boolean;
  onViewOutput: (workflowId: string, documentId: string) => void;
}

interface WorkflowStep {
  id: string;
  message: string;
  status: "pending" | "running" | "completed" | "failed";
  timestamp: string;
  docId?: string;
  workflowId?: string;
  hasOutput?: boolean;
}

export function WorkflowTimeline({ 
  definitionName, 
  events, 
  isConnected, 
  isComplete,
  onViewOutput 
}: WorkflowTimelineProps) {
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

      // Logic to unify events into stable steps
      if (stageName === "processed") {
        stepKey = `${docId}:processed`;
      } else if (stageName === "classified") {
        stepKey = `${docId}:classified`;
      } else if (stageName === "extracted") {
        stepKey = `${docId}:extracted`;
      } else if (stageName === "enriched") {
        stepKey = `${docId}:enriched`;
      } else if (stageName === "summarized") {
        stepKey = `${docId}:summarized`;
      } else if (stageName) {
        stepKey = `${docId}:${stageName}`;
      } else if (event_type === "workflow:progress") {
        return;
      } else if (event_type.startsWith("workflow:")) {
        return;
      } else {
        stepKey = docId ? `${docId}:${event_type}` : `global:${event_type}`;
      }

      const status = event_type === "stage:completed" || event_type === "workflow:completed" 
        ? "completed" 
        : (event_type === "stage:failed" || event_type === "workflow:failed" ? "failed" : "running");

      const hasOutput = !!data?.has_output;

      if (!stepMap.has(stepKey)) {
        orderedKeys.push(stepKey);
      }

      stepMap.set(stepKey, {
        id: stepKey,
        message: message || "Processing...",
        status,
        timestamp,
        docId,
        workflowId: data?.workflow_id || event.workflow_id,
        hasOutput
      });
    });
    
    const finalSteps: WorkflowStep[] = orderedKeys.map(key => ({ ...stepMap.get(key)! }));
    
    // Pass 2: Clean up statuses based on sequence
    for (let i = 0; i < finalSteps.length; i++) {
        const step = finalSteps[i];
        if (!step) continue;
        
        const isLast = i === finalSteps.length - 1;

        // Auto-complete previous steps for the same document
        if (step.status === 'running') {
            const hasLaterDocStep = finalSteps.slice(i + 1).some(s => s && s.docId === step.docId);
            if (hasLaterDocStep || (isComplete && isLast)) {
                step.status = 'completed';
            }
        }
    }

    return finalSteps;
  }, [events, isComplete]);

  const [showTopBlur, setShowTopBlur] = useState(false);
  const [showBottomBlur, setShowBottomBlur] = useState(false);

  useEffect(() => {
    const scrollContainer = scrollRef.current?.querySelector('[data-radix-scroll-area-viewport]');
    
    const handleScroll = () => {
      if (scrollContainer) {
        const { scrollTop, scrollHeight, clientHeight } = scrollContainer as HTMLElement;
        setShowTopBlur(scrollTop > 10);
        setShowBottomBlur(scrollTop + clientHeight < scrollHeight);
      }
    };

    if (scrollRef.current) {
      const viewport = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (viewport) {
        viewport.scrollTop = viewport.scrollHeight;
        setTimeout(handleScroll, 100);
      }
    }

    if (scrollContainer) {
      scrollContainer.addEventListener("scroll", handleScroll);
      return () => scrollContainer.removeEventListener("scroll", handleScroll);
    }
  }, [steps]);

  if (events.length === 0) return null;

  const latestStep = steps[steps.length - 1];
  const latestMessage = latestStep?.message || (isComplete ? "Workflow finished" : "Initializing...");

  return (
    <div className="w-full max-w-2xl mx-auto">
      <Collapsible defaultOpen>
        <div className="bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded overflow-hidden">
          <CollapsibleTrigger asChild>
            <button className="w-full group flex items-center justify-between gap-4 px-5 py-3 hover:bg-zinc-50/50 dark:hover:bg-zinc-900/50 transition-colors">
              <div className="flex items-center gap-4 relative z-10 shrink-0">
                <div className="flex flex-col items-start gap-1">
                  <span className="text-sm font-bold text-zinc-900 dark:text-zinc-100 tracking-tight text-left">
                    {isComplete ? `${definitionName} Successfully Executed` : `${definitionName} Running`}
                  </span>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 font-medium text-left line-clamp-1">
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
          </CollapsibleTrigger>

          <CollapsibleContent>
            <div className="px-6 pb-8 pt-2">
              <div className="relative">
                <ScrollArea 
                  ref={scrollRef}
                  className="relative flex flex-col gap-1 max-h-[250px]"
                >
                  <div className="absolute left-[11px] top-3 bottom-3 w-[1.5px] bg-zinc-100 dark:bg-zinc-800" />

                  <AnimatePresence initial={false} mode="popLayout">
                    {steps.map((step, index) => {
                      const isRunning = step.status === "running";
                      const isCompleted = step.status === "completed";
                      const isFailed = step.status === "failed";
                      const isPending = step.status === "pending";

                      return (
                        <motion.div
                          key={step.id}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0, scale: 0.95 }}
                          transition={{ duration: 0.2 }}
                          className="relative flex items-center gap-4 group"
                        >
                          <div className="relative z-10 flex items-center justify-center size-6">
                            {isCompleted ? (
                              <div className="size-5 rounded-full bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center shadow-sm">
                                <Check className="size-3 text-zinc-500 stroke-[3]" />
                              </div>
                            ) : isRunning ? (
                              <div className="size-6 rounded-full bg-[#0232D4]/10 dark:bg-blue-400/20 ring-[#0232D4]/20 dark:border-blue-400 flex items-center justify-center shadow-sm">
                                <Loader2 className="size-3 text-[#0232D4]/80 animate-spin stroke-[3]" />
                              </div>
                            ) : (
                              <div className="size-5 rounded-full bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 flex items-center justify-center shadow-sm">
                                <div className="size-1.5 rounded-full bg-zinc-300 dark:bg-zinc-700" />
                              </div>
                            )}
                          </div>

                          <div className="flex-1 flex items-center justify-between min-h-[2.5rem] rounded transition-colors">
                            <span className={cn(
                              "text-[13px] transition-colors duration-300",
                              isCompleted ? "text-zinc-500 dark:text-zinc-400 font-medium" : (isRunning ? "text-[#1D3DCE]/80 dark:text-[#1D3DCE]/80 font-semibold" : "text-zinc-400 dark:text-zinc-500 font-medium"),
                            )}>
                              {step.message}
                            </span>
                            
                            {isCompleted && step.hasOutput && (
                              <Button 
                                variant="ghost" 
                                size="sm" 
                                className="h-7 px-2.5 text-[11px] font-bold text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:hover:text-zinc-100 rounded group/btn shadow-none"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (step.workflowId && step.docId) {
                                    onViewOutput(step.workflowId, step.docId);
                                  }
                                }}
                              >
                                View Output
                                <ArrowRight className="size-3 ml-1 group-hover/btn:translate-x-0.5 transition-transform" />
                              </Button>
                            )}
                          </div>
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>
                </ScrollArea>

                {/* Top Blur Overlay */}
                <div 
                  className={cn(
                    "absolute top-0 left-0 right-0 h-10 z-20 pointer-events-none transition-opacity duration-300 bg-gradient-to-b from-white via-white/80 to-transparent dark:from-zinc-950 dark:via-zinc-950/80 dark:to-transparent",
                    showTopBlur ? "opacity-100" : "opacity-0"
                  )} 
                />

                {/* Bottom Blur Overlay */}
                <div 
                  className={cn(
                    "absolute bottom-0 left-0 right-0 h-10 z-20 pointer-events-none transition-opacity duration-300 bg-gradient-to-t from-white via-white/80 to-transparent dark:from-zinc-950 dark:via-zinc-950/80 dark:to-transparent",
                    showBottomBlur ? "opacity-100" : "opacity-0"
                  )} 
                />
              </div>
            </div>
          </CollapsibleContent>
        </div>
      </Collapsible>
    </div>
  );
}
