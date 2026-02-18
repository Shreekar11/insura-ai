"use client";

import {
  Loader2,
  GitCompare,
  X,
  CheckCircle2,
  MinusCircle,
  PlusCircle,
  AlertCircle,
  Search,
  Download,
} from "lucide-react";
import React from "react";
import { useComparisonData } from "@/hooks/use-comparison-data";
import { useCitations, findCitation } from "@/hooks/use-citations";
import { usePDFHighlight } from "@/contexts/pdf-highlight-context";
import { useDocuments } from "@/hooks/use-documents";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EntityComparison } from "@/schema/generated/workflows";
import { useSidebar } from "../ui/sidebar";

interface ComparisonOutputSidebarProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workflowId: string | null;
}

function MatchTypeBadge({ matchType }: { matchType: string }) {
  const config: Record<
    string,
    {
      label: string | undefined;
      className: string | undefined;
      icon: React.ReactNode | undefined;
    }
  > = {
    match: {
      label: "Match",
      className:
        "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
      icon: <CheckCircle2 className="size-3" />,
    },
    partial_match: {
      label: "Partial",
      className:
        "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
      icon: <AlertCircle className="size-3" />,
    },
    added: {
      label: "Added",
      className:
        "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
      icon: <PlusCircle className="size-3" />,
    },
    removed: {
      label: "Removed",
      className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
      icon: <MinusCircle className="size-3" />,
    },
    no_match: {
      label: "No Match",
      className:
        "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-400",
      icon: <X className="size-3" />,
    },
  };

  const { label, className, icon } = config[matchType] ||
    config.no_match || { label: "", className: "", icon: null };

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

export function ComparisonOutputSidebar({
  open,
  onOpenChange,
  workflowId,
}: ComparisonOutputSidebarProps) {
  const { data, isLoading, error } = useComparisonData(
    open ? workflowId : null,
  );

  const { state } = useSidebar();
  const isExpanded = state === "expanded";

  const [searchQuery, setSearchQuery] = React.useState("");

  const comparisons = React.useMemo(
    () => (data?.comparisons || []) as EntityComparison[],
    [data?.comparisons],
  );
  const summary = data?.summary;
  const doc1Name = React.useMemo(
    () => data?.doc1_name || "Document 1",
    [data?.doc1_name],
  );
  const doc2Name = React.useMemo(
    () => data?.doc2_name || "Document 2",
    [data?.doc2_name],
  );

  const { data: citations1 } = useCitations(workflowId, data?.doc1_id || null);
  const { data: citations2 } = useCitations(workflowId, data?.doc2_id || null);
  const { data: documentsData } = useDocuments(workflowId ?? undefined);
  const { highlightCitation } = usePDFHighlight();

  const hasCitation1 = React.useCallback(
    (type: string | undefined, id: string | null | undefined) => {
      if (!type || !id || !citations1?.citations) return false;
      return !!findCitation(citations1.citations, type, id);
    },
    [citations1?.citations],
  );

  const hasCitation2 = React.useCallback(
    (type: string | undefined, id: string | null | undefined) => {
      if (!type || !id || !citations2?.citations) return false;
      return !!findCitation(citations2.citations, type, id);
    },
    [citations2?.citations],
  );

  const handleDocHighlight = React.useCallback(
    (
      docNum: 1 | 2,
      entityType: string | undefined,
      entityId: string | null | undefined,
    ) => {
      const citData = docNum === 1 ? citations1 : citations2;
      const docId = docNum === 1 ? data?.doc1_id : data?.doc2_id;
      const document = documentsData?.documents?.find((d) => d.id === docId);

      if (
        !citData?.citations ||
        !document?.file_path ||
        !entityType ||
        !entityId
      )
        return;

      const citation = findCitation(citData.citations, entityType, entityId);
      if (citation && docId) {
        highlightCitation(
          citation,
          document.file_path,
          docId,
          citData.pageDimensions,
        );
      }
    },
    [
      citations1,
      citations2,
      data?.doc1_id,
      data?.doc2_id,
      documentsData?.documents,
      highlightCitation,
    ],
  );

  const filteredComparisons = React.useMemo(() => {
    // Initial filter for non-null Item
    let result = comparisons.filter((c) => c.entity_name || c.entity_type);

    // Sort by citation presence (items with citations on top)
    result = [...result].sort((a, b) => {
      const aHasCit =
        hasCitation1(a.entity_type, a.entity_id) ||
        hasCitation2(a.entity_type, a.entity_id);
      const bHasCit =
        hasCitation1(b.entity_type, b.entity_id) ||
        hasCitation2(b.entity_type, b.entity_id);
      if (aHasCit && !bHasCit) return -1;
      if (!aHasCit && bHasCit) return 1;
      return 0;
    });

    // Search query filter
    if (searchQuery) {
      const lowerQuery = searchQuery.toLowerCase();
      result = result.filter((c) => {
        const entityName = (c.entity_name || "").toLowerCase();
        const reasoning = (c.reasoning || "").toLowerCase();
        const summary = (c.comparison_summary || "").toLowerCase();
        const type = (c.entity_type || "").toLowerCase();
        return (
          entityName.includes(lowerQuery) ||
          reasoning.includes(lowerQuery) ||
          summary.includes(lowerQuery) ||
          type.includes(lowerQuery)
        );
      });
    }
    return result;
  }, [comparisons, searchQuery, hasCitation1, hasCitation2]);

  const hasData = filteredComparisons.length > 0;

  const formatAttributes = (content: any) => {
    if (!content) return "—";
    // If content is just a string/number (not object), return it
    if (typeof content !== "object") return String(content);

    return Object.entries(content)
      .filter(([key]) => {
        const lowerKey = key.toLowerCase();
        return (
          !["name", "title", "id"].includes(lowerKey) && !key.startsWith("_")
        );
      })
      .map(([key, val]) => {
        // Handle nested objects or arrays gracefully
        const displayVal = typeof val === "object" ? JSON.stringify(val) : val;
        return `${key.replace(/_/g, " ")}: ${displayVal}`;
      })
      .join("; ");
  };

  if (!open) return null;

  return (
    <div
      className="flex flex-col h-full overflow-hidden bg-white dark:bg-zinc-950"
      onWheel={(e) => {
        e.stopPropagation();
      }}
    >
      <div
        className={cn(
          "px-6 border-b border-zinc-200 dark:border-zinc-800 shrink-0 bg-white dark:bg-zinc-950 flex items-center justify-between transition-[height] ease-linear",
          isExpanded ? "h-14" : "h-12",
        )}
      >
        <div className="flex items-center gap-3">
          <div className="p-1.5 rounded bg-zinc-100 dark:bg-zinc-800">
            <GitCompare className="size-4 text-zinc-600 dark:text-zinc-400" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 leading-tight">
              Policy Comparison
            </h2>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
          onClick={() => onOpenChange(false)}
        >
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex-1 flex flex-col min-h-0">
        <div className="px-6 py-4 bg-white dark:bg-zinc-950 flex items-center gap-3 border-b border-zinc-100 dark:border-zinc-900">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-zinc-400" />
            <Input
              placeholder="Search comparison..."
              className="pl-9 h-9 rounded text-xs bg-zinc-50 dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        <div className="flex-1 overflow-auto">
          <div className="min-w-full inline-block align-middle">
            <div className="overflow-hidden">
              <div className="p-2 pb-0">
                {/* Overall Explanation */}
                {!isLoading && !error && data?.overall_explanation && (
                  <div className="bg-gray-50 dark:bg-gray-900/10 rounded p-4 mb-2 border border-gray-100 dark:border-gray-900/50">
                    <h3 className="text-sm font-semibold text-[#2B2C36] dark:text-gray-100 mb-2 tracking-wider">
                      Overall Summary
                    </h3>
                    <p className="text-xs text-[#2B2C36] leading-relaxed">
                      {data.overall_explanation}
                    </p>
                  </div>
                )}
              </div>

              {/* Loading State */}
              {isLoading && (
                <div className="flex flex-col items-center justify-center py-16">
                  <div className="p-3 rounded-full bg-zinc-100 dark:bg-zinc-800 mb-4">
                    <Loader2 className="size-6 text-zinc-500 animate-spin" />
                  </div>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    Loading comparison data...
                  </p>
                </div>
              )}

              {/* Error State */}
              {error && (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="p-3 rounded bg-red-100 dark:bg-red-900/20 mb-4">
                    <X className="size-6 text-red-500" />
                  </div>
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mb-1">
                    Failed to load comparison data
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-xs">
                    {error.message}
                  </p>
                </div>
              )}

              {/* Data Display Table */}
              {!isLoading && !error && hasData && (
                <TooltipProvider>
                  <Table className="table-fixed">
                    <TableHeader className="border-t ">
                      <TableRow className="bg-zinc-50/50 dark:bg-zinc-900/50">
                        <TableHead className="px-6 py-3 text-xs font-semibold text-zinc-500 dark:text-zinc-400 w-[15%] whitespace-normal break-words">
                          Item
                        </TableHead>
                        <TableHead className="px-6 py-3 text-xs font-semibold text-zinc-500 dark:text-zinc-400 w-[25%] whitespace-normal break-words">
                          {doc1Name}
                        </TableHead>
                        <TableHead className="px-6 py-3 text-xs font-semibold text-zinc-500 dark:text-zinc-400 w-[25%] whitespace-normal break-words">
                          {doc2Name}
                        </TableHead>
                        <TableHead className="px-6 py-3 text-xs font-semibold text-zinc-500 dark:text-zinc-400 w-[35%] whitespace-normal break-words">
                          Comparison
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredComparisons.map((c, i) => {
                        let entityTypeLabel = "Unknown";
                        switch (c.entity_type) {
                          case "coverage":
                            entityTypeLabel = "Coverage";
                            break;
                          case "exclusion":
                            entityTypeLabel = "Exclusion";
                            break;
                          case "section_coverage":
                            entityTypeLabel = "Coverage (Section)";
                            break;
                          case "section_exclusion":
                            entityTypeLabel = "Exclusion (Section)";
                            break;
                          default:
                            entityTypeLabel = c.entity_type || "Entity";
                        }

                        // Helper to get name from content if available
                        const getName = (content: any, type?: string) => {
                          if (!content || !type) return null;
                          if (
                            type === "coverage" ||
                            type === "section_coverage"
                          ) {
                            return (
                              content.attributes?.coverage_name ||
                              content.coverage_name ||
                              content.name ||
                              content.title ||
                              null
                            );
                          }
                          return (
                            content.attributes?.name ||
                            content.name ||
                            content.title ||
                            null
                          );
                        };

                        const entityName =
                          getName(c.doc1_content, c.entity_type) ||
                          getName(c.doc2_content, c.entity_type) ||
                          c.entity_name ||
                          "—";

                        const cit1 = hasCitation1(c.entity_type, c.entity_id);
                        const cit2 = hasCitation2(c.entity_type, c.entity_id);
                        const anyCit = cit1 || cit2;

                        return (
                          <TableRow
                            key={i}
                            className={cn(
                              "group hover:bg-zinc-50/50 dark:hover:bg-zinc-900/50 border-b border-zinc-100 dark:border-zinc-900 transition-colors",
                              anyCit && "bg-orange-50/10",
                            )}
                          >
                            <TableCell
                              className="px-6 py-4 align-top text-xs font-medium text-zinc-900 dark:text-zinc-100 whitespace-normal break-words relative pr-6 cursor-pointer"
                              onClick={() => {
                                if (cit1)
                                  handleDocHighlight(
                                    1,
                                    c.entity_type,
                                    c.entity_id,
                                  );
                                else if (cit2)
                                  handleDocHighlight(
                                    2,
                                    c.entity_type,
                                    c.entity_id,
                                  );
                              }}
                            >
                              <span className="text-[10px] uppercase text-zinc-400 block mb-1">
                                {entityTypeLabel}
                              </span>
                              {entityName}
                              {anyCit && (
                                <div className="absolute top-0 right-0">
                                  <div className="w-0 h-0 border-t-[8px] border-l-[8px] border-t-orange-500 border-l-transparent" />
                                </div>
                              )}
                            </TableCell>
                            <TableCell
                              className={cn(
                                "px-6 py-4 align-top text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed whitespace-normal break-words relative group/cell",
                                cit1 && "cursor-pointer hover:bg-orange-50/20",
                              )}
                              onClick={() =>
                                cit1 &&
                                handleDocHighlight(
                                  1,
                                  c.entity_type,
                                  c.entity_id,
                                )
                              }
                            >
                              {c.doc1_content ? (
                                <div className="space-y-1">
                                  {getName(c.doc1_content, c.entity_type) && (
                                    <span className="font-medium text-zinc-900 dark:text-zinc-200 block">
                                      {getName(c.doc1_content, c.entity_type)}
                                    </span>
                                  )}
                                  <p className="text-zinc-700 dark:text-zinc-300">
                                    {c.doc1_summary ||
                                      formatAttributes(c.doc1_content)}
                                  </p>
                                  {c.doc1_summary && (
                                    <span className="text-[10px] text-zinc-400 block mt-1 italic">
                                      {formatAttributes(c.doc1_content)}
                                    </span>
                                  )}
                                  {cit1 && (
                                    <div className="absolute top-0 right-0">
                                      <div className="w-0 h-0 border-t-[10px] border-l-[10px] border-t-orange-500 border-l-transparent" />
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <span className="text-zinc-400 italic">
                                  Not present
                                </span>
                              )}
                            </TableCell>
                            <TableCell
                              className={cn(
                                "px-6 py-4 align-top text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed whitespace-normal break-words relative group/cell",
                                cit2 && "cursor-pointer hover:bg-orange-50/20",
                              )}
                              onClick={() =>
                                cit2 &&
                                handleDocHighlight(
                                  2,
                                  c.entity_type,
                                  c.entity_id,
                                )
                              }
                            >
                              {c.doc2_content ? (
                                <div className="space-y-1">
                                  {getName(c.doc2_content, c.entity_type) && (
                                    <span className="font-medium text-zinc-900 dark:text-zinc-200 block">
                                      {getName(c.doc2_content, c.entity_type)}
                                    </span>
                                  )}
                                  <p className="text-zinc-700 dark:text-zinc-300">
                                    {c.doc2_summary ||
                                      formatAttributes(c.doc2_content)}
                                  </p>
                                  {c.doc2_summary && (
                                    <span className="text-[10px] text-zinc-400 block mt-1 italic">
                                      {formatAttributes(c.doc2_content)}
                                    </span>
                                  )}
                                  {cit2 && (
                                    <div className="absolute top-0 right-0">
                                      <div className="w-0 h-0 border-t-[10px] border-l-[10px] border-t-orange-500 border-l-transparent" />
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <span className="text-zinc-400 italic">
                                  Not present
                                </span>
                              )}
                            </TableCell>
                            <TableCell className="px-6 py-4 align-top text-xs leading-relaxed whitespace-normal break-words w-[35%]">
                              <div className="flex flex-col gap-2">
                                <MatchTypeBadge
                                  matchType={c.match_type || "no_match"}
                                />
                                {(c.comparison_summary || c.reasoning) && (
                                  <p className="text-zinc-700 dark:text-zinc-300 font-medium text-[11px]">
                                    {c.comparison_summary || c.reasoning}
                                  </p>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TooltipProvider>
              )}

              {/* Empty State */}
              {!isLoading && !error && !hasData && (
                <div className="flex flex-col items-center justify-center py-20 text-center px-6">
                  <div className="p-4 rounded-full bg-zinc-100 dark:bg-zinc-800 mb-4">
                    <GitCompare className="size-8 text-zinc-400 dark:text-zinc-500" />
                  </div>
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mb-1">
                    No comparison data found
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-xs">
                    {searchQuery
                      ? "Try adjusting your search query."
                      : "The comparison has not been executed yet or no entities were found to compare."}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
