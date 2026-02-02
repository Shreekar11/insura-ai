"use client";

import { Loader2, GitCompare, X, CheckCircle2, MinusCircle, PlusCircle, AlertCircle } from "lucide-react";
import { useComparisonData } from "@/hooks/use-comparison-data";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { EntityComparison, EntityComparisonSummary } from "@/schema/generated/workflows";

interface ComparisonOutputSidebarProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workflowId: string | null;
}

function MatchTypeBadge({ matchType }: { matchType: string }) {
  const config: Record<string, { label: string; className: string; icon: React.ReactNode }> = {
    match: {
      label: "Match",
      className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
      icon: <CheckCircle2 className="size-3" />,
    },
    partial_match: {
      label: "Partial",
      className: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
      icon: <AlertCircle className="size-3" />,
    },
    added: {
      label: "Added",
      className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
      icon: <PlusCircle className="size-3" />,
    },
    removed: {
      label: "Removed",
      className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
      icon: <MinusCircle className="size-3" />,
    },
    no_match: {
      label: "No Match",
      className: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-400",
      icon: <X className="size-3" />,
    },
  };

  const { label, className, icon } = config[matchType] || config.no_match;

  return (
    <Badge variant="secondary" className={cn("gap-1 font-normal", className)}>
      {icon}
      {label}
    </Badge>
  );
}

function ComparisonSummaryCard({ summary, doc1Name, doc2Name }: {
  summary: EntityComparisonSummary;
  doc1Name: string;
  doc2Name: string;
}) {
  return (
    <div className="bg-zinc-50 dark:bg-zinc-900 rounded-lg p-4 mb-6">
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">
        Comparison Summary
      </h3>
      <div className="grid grid-cols-2 gap-4 text-xs">
        <div>
          <p className="text-zinc-500 dark:text-zinc-400 mb-2 font-medium">{doc1Name}</p>
          <div className="space-y-1">
            <p>{summary.total_coverages_doc1} coverages</p>
            <p>{summary.total_exclusions_doc1} exclusions</p>
          </div>
        </div>
        <div>
          <p className="text-zinc-500 dark:text-zinc-400 mb-2 font-medium">{doc2Name}</p>
          <div className="space-y-1">
            <p>{summary.total_coverages_doc2} coverages</p>
            <p>{summary.total_exclusions_doc2} exclusions</p>
          </div>
        </div>
      </div>
      <div className="border-t border-zinc-200 dark:border-zinc-800 mt-4 pt-4">
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-green-600 font-medium">{summary.coverage_matches + summary.exclusion_matches}</span>
            <span className="text-zinc-500">Exact Matches</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-yellow-600 font-medium">{summary.coverage_partial_matches + summary.exclusion_partial_matches}</span>
            <span className="text-zinc-500">Partial Matches</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-blue-600 font-medium">{summary.coverages_added + summary.exclusions_added}</span>
            <span className="text-zinc-500">Added</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-red-600 font-medium">{summary.coverages_removed + summary.exclusions_removed}</span>
            <span className="text-zinc-500">Removed</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function ComparisonRow({ comparison, doc1Name, doc2Name }: {
  comparison: EntityComparison;
  doc1Name: string;
  doc2Name: string;
}) {
  const entityName = comparison.doc1_name || comparison.doc2_name || "Unknown";
  const entityType = comparison.entity_type === "coverage" ? "Coverage" : "Exclusion";

  return (
    <div className="border border-zinc-200 dark:border-zinc-800 rounded-lg p-4 mb-3">
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
              {entityType}
            </span>
            <MatchTypeBadge matchType={comparison.match_type || "no_match"} />
          </div>
          <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {entityName}
          </h4>
        </div>
      </div>

      {/* Side-by-side comparison */}
      <div className="grid grid-cols-2 gap-4 text-xs">
        <div className={cn(
          "p-3 rounded-md",
          comparison.match_type === "added"
            ? "bg-zinc-100 dark:bg-zinc-800 opacity-50"
            : "bg-zinc-50 dark:bg-zinc-900"
        )}>
          <p className="text-zinc-500 dark:text-zinc-400 mb-2 font-medium truncate" title={doc1Name}>
            {doc1Name}
          </p>
          {comparison.doc1_entity ? (
            <div className="space-y-1 text-zinc-700 dark:text-zinc-300">
              <p className="font-medium">{comparison.doc1_name || "—"}</p>
              {comparison.doc1_canonical_id && (
                <p className="text-zinc-400 text-[10px]">ID: {comparison.doc1_canonical_id}</p>
              )}
            </div>
          ) : (
            <p className="text-zinc-400 italic">Not present</p>
          )}
        </div>
        <div className={cn(
          "p-3 rounded-md",
          comparison.match_type === "removed"
            ? "bg-zinc-100 dark:bg-zinc-800 opacity-50"
            : "bg-zinc-50 dark:bg-zinc-900"
        )}>
          <p className="text-zinc-500 dark:text-zinc-400 mb-2 font-medium truncate" title={doc2Name}>
            {doc2Name}
          </p>
          {comparison.doc2_entity ? (
            <div className="space-y-1 text-zinc-700 dark:text-zinc-300">
              <p className="font-medium">{comparison.doc2_name || "—"}</p>
              {comparison.doc2_canonical_id && (
                <p className="text-zinc-400 text-[10px]">ID: {comparison.doc2_canonical_id}</p>
              )}
            </div>
          ) : (
            <p className="text-zinc-400 italic">Not present</p>
          )}
        </div>
      </div>

      {/* Reasoning */}
      {comparison.reasoning && (
        <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-800">
          <p className="text-xs text-zinc-600 dark:text-zinc-400">
            {comparison.reasoning}
          </p>
        </div>
      )}

      {/* Field Differences */}
      {comparison.field_differences && comparison.field_differences.length > 0 && (
        <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-800">
          <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-2">
            Differences:
          </p>
          <div className="space-y-1">
            {comparison.field_differences.map((diff: any, index: number) => (
              <div key={index} className="text-xs text-zinc-600 dark:text-zinc-400 flex gap-2">
                <span className="font-medium text-zinc-700 dark:text-zinc-300">{diff.field}:</span>
                <span className="text-red-500 line-through">{String(diff.doc1_value ?? "—")}</span>
                <span>→</span>
                <span className="text-green-500">{String(diff.doc2_value ?? "—")}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ComparisonOutputSidebar({
  open,
  onOpenChange,
  workflowId,
}: ComparisonOutputSidebarProps) {
  const { data, isLoading, error } = useComparisonData(open ? workflowId : null);

  const comparisons = data?.comparisons || [];
  const summary = data?.summary;
  const hasData = comparisons.length > 0;
  const doc1Name = data?.doc1_name || "Document 1";
  const doc2Name = data?.doc2_name || "Document 2";

  // Separate by entity type
  const coverageComparisons = comparisons.filter((c) => c.entity_type === "coverage");
  const exclusionComparisons = comparisons.filter((c) => c.entity_type === "exclusion");

  if (!open) return null;

  return (
    <div
      className="flex flex-col h-full overflow-hidden bg-white dark:bg-zinc-950 border-l border-zinc-200 dark:border-zinc-800"
      onWheel={(e) => {
        e.stopPropagation();
      }}
    >
      <div className="px-6 py-5 border-b border-zinc-200 dark:border-zinc-800 shrink-0 bg-zinc-50/50 dark:bg-zinc-900/50 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Policy Comparison
          </h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Entity-level comparison between policies
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded-full"
          onClick={() => onOpenChange(false)}
        >
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        <div className="px-6 py-5 pb-20">
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
              <div className="p-3 rounded-full bg-red-100 dark:bg-red-900/20 mb-4">
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

          {/* Data Display */}
          {!isLoading && !error && hasData && (
            <div>
              {/* Summary */}
              {summary && (
                <ComparisonSummaryCard
                  summary={summary}
                  doc1Name={doc1Name}
                  doc2Name={doc2Name}
                />
              )}

              {/* Overall Explanation */}
              {data?.overall_explanation && (
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 mb-6 border border-blue-200 dark:border-blue-800">
                  <h3 className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-2">
                    Summary
                  </h3>
                  <p className="text-sm text-blue-800 dark:text-blue-200">
                    {data.overall_explanation}
                  </p>
                </div>
              )}

              {/* Coverage Comparisons */}
              {coverageComparisons.length > 0 && (
                <div className="mb-8">
                  <div className="flex items-center gap-2 mb-4 pb-3 border-b border-zinc-200 dark:border-zinc-800">
                    <GitCompare className="size-4 text-zinc-500" />
                    <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      Coverages ({coverageComparisons.length})
                    </h2>
                  </div>
                  {coverageComparisons.map((comparison, index) => (
                    <ComparisonRow
                      key={`coverage-${index}`}
                      comparison={comparison}
                      doc1Name={doc1Name}
                      doc2Name={doc2Name}
                    />
                  ))}
                </div>
              )}

              {/* Exclusion Comparisons */}
              {exclusionComparisons.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-4 pb-3 border-b border-zinc-200 dark:border-zinc-800">
                    <GitCompare className="size-4 text-zinc-500" />
                    <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      Exclusions ({exclusionComparisons.length})
                    </h2>
                  </div>
                  {exclusionComparisons.map((comparison, index) => (
                    <ComparisonRow
                      key={`exclusion-${index}`}
                      comparison={comparison}
                      doc1Name={doc1Name}
                      doc2Name={doc2Name}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Empty State */}
          {!isLoading && !error && !hasData && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="p-4 rounded-full bg-zinc-100 dark:bg-zinc-800 mb-4">
                <GitCompare className="size-8 text-zinc-400 dark:text-zinc-500" />
              </div>
              <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mb-1">
                No comparison data available
              </p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-xs">
                The comparison has not been executed yet or no entities were found to compare.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
