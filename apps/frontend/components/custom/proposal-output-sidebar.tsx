"use client";

import {
  Loader2,
  FileText,
  X,
  CheckCircle2,
  AlertCircle,
  Download,
  Info,
  ShieldCheck,
  ClipboardList,
  ArrowRightLeft,
} from "lucide-react";
import React from "react";
import { useProposalData } from "@/hooks/use-proposal-data";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";

interface ProposalOutputSidebarProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workflowId: string | null;
}

function DeltaFlagBadge({ flag }: { flag: string }) {
  const config: Record<
    string,
    {
      label: string;
      className: string;
      icon: React.ReactNode;
    }
  > = {
    STABLE: {
      label: "Stable",
      className:
        "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
      icon: <CheckCircle2 className="size-3" />,
    },
    IMPROVED: {
      label: "Improved",
      className:
        "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
      icon: <ArrowRightLeft className="size-3" />,
    },
    DEGRADED: {
      label: "Degraded",
      className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
      icon: <AlertCircle className="size-3" />,
    },
    NEW: {
      label: "New",
      className:
        "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
      icon: <FileText className="size-3" />,
    },
  };

  const { label, className, icon } = config[flag] || {
    label: flag,
    className: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-400",
    icon: <Info className="size-3" />,
  };

  return (
    <Badge
      variant="secondary"
      className={cn("gap-1 font-normal rounded", className)}
    >
      {icon}
      {label}
    </Badge>
  );
}

export function ProposalOutputSidebar({
  open,
  onOpenChange,
  workflowId,
}: ProposalOutputSidebarProps) {
  const { data, isLoading, error } = useProposalData(workflowId || "");

  if (!open) return null;

  return (
    <div className="flex flex-col h-full bg-background border-l shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-zinc-100 dark:bg-zinc-900/30 rounded">
            <ClipboardList className="size-5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold tracking-tight">
              Technical Proposal
            </h2>
            <p className="text-xs text-muted-foreground">
              Generated analysis & comparison
            </p>
          </div>
        </div>
        <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)}>
          <X className="size-4" />
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-6 space-y-8">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 className="size-8 animate-spin text-muted-foreground" />
              <p className="text-sm text-muted-foreground italic">
                Assembling proposal data...
              </p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-12 text-center space-y-3">
              <div className="p-3 bg-destructive/10 text-destructive rounded-full">
                <AlertCircle className="size-6" />
              </div>
              <div>
                <p className="text-sm font-medium">Failed to load proposal</p>
                <p className="text-xs text-muted-foreground max-w-[200px] mx-auto mt-1">
                  There was an error retrieving the generated results.
                </p>
              </div>
            </div>
          ) : data ? (
            <>
              {/* Executive Summary */}
              <section className="space-y-3">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <FileText className="size-4 text-muted-foreground" />
                  Executive Summary
                </h3>
                <div className="p-4 rounded-lg bg-muted/30 border border-muted text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap">
                  {data.executive_summary}
                </div>
              </section>

              {/* Comparison Table */}
              <section className="space-y-3">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <ArrowRightLeft className="size-4 text-muted-foreground" />
                  Documents Comparison
                </h3>
                <div className="rounded-md border">
                  <Table>
                    <TableHeader className="bg-muted/50">
                      <TableRow>
                        <TableHead className="text-[11px] uppercase font-bold text-muted-foreground h-8">
                          Item
                        </TableHead>
                        <TableHead className="text-[11px] uppercase font-bold text-muted-foreground h-8 text-right">
                          Change
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.comparison_table?.map((row, idx) => (
                        <TableRow key={idx} className="group hover:bg-muted/30">
                          <TableCell className="py-3">
                            <div className="space-y-0.5">
                              <p className="text-[13px] font-medium leading-none">
                                {row.label}
                              </p>
                              <p className="text-[11px] text-muted-foreground">
                                {row.category}
                              </p>
                            </div>
                          </TableCell>
                          <TableCell className="py-3 text-right">
                            <DeltaFlagBadge flag={row.delta_flag || "STABLE"} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </section>

              {/* Narratives/Sections */}
              {data.sections?.map((section, idx) => (
                <section key={idx} className="space-y-3">
                  <h3 className="text-sm font-semibold">{section.title}</h3>
                  <div className="p-4 rounded-lg border bg-background text-sm leading-relaxed whitespace-pre-wrap">
                    {section.narrative}
                  </div>
                  {section.key_findings && section.key_findings.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-[11px] uppercase font-bold text-muted-foreground px-1">
                        Key Findings
                      </p>
                      <ul className="space-y-2">
                        {section.key_findings.map(
                          (finding: any, findIdx: number) => (
                            <li
                              key={findIdx}
                              className="flex gap-2 text-sm text-foreground/80"
                            >
                              <div className="size-1.5 rounded-full bg-indigo-400 mt-1.5 shrink-0" />
                              <span>
                                {finding.detail ||
                                  finding.summary ||
                                  JSON.stringify(finding)}
                              </span>
                            </li>
                          ),
                        )}
                      </ul>
                    </div>
                  )}
                </section>
              ))}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
              <ClipboardList className="size-12 opacity-10 mb-2" />
              <p className="text-sm italic">
                No proposal data found for this workflow.
              </p>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
