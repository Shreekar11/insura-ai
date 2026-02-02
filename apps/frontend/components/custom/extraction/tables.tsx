import React from "react";
import { Tag } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { MinimalTableHeader } from "./common";
import {
  mapEntityToCoverage,
  mapSectionToCoverage,
  mapEntityToExclusion,
  mapSectionToExclusion,
  mapEntityToCondition,
  mapSectionToCondition,
  mapEntityToEndorsement,
  mapSectionToEndorsement,
  mapSectionToModification,
  normalizeFieldLabel,
  formatValue,
  getSeverityBadgeStyle,
  getEffectCategoryBadgeStyle,
  formatEffectCategory
} from "@/utils/extraction-utils";
import { Entity } from "@/types/extraction";

/**
 * Specialized Table Components - Simplified view showing item + description
 */
export function CoverageTable({ items, isEntity = false }: { items: any[]; isEntity?: boolean }) {
  const data = items.map(isEntity ? mapEntityToCoverage : mapSectionToCoverage);
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <MinimalTableHeader headers={["Coverage", "Description"]} />
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {data.map((row, i) => (
            <tr key={i} className="group hover:bg-zinc-50/30 dark:hover:bg-zinc-900/10">
              <td className="px-3 py-3 align-top w-[220px] min-w-[180px]">
                <div className="font-medium text-zinc-900 dark:text-zinc-100">{row.name}</div>
                {row.type && (
                  <Badge variant="outline" className="mt-1 text-[9px] px-1.5 py-0 h-4 text-zinc-500 border-zinc-200 dark:border-zinc-700">
                    {row.type}
                  </Badge>
                )}
              </td>
              <td className="px-3 py-3 align-top text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {row.description || "Provides coverage as defined in the policy."}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ExclusionTable({ items, isEntity = false }: { items: any[]; isEntity?: boolean }) {
  const data = items.map(isEntity ? mapEntityToExclusion : mapSectionToExclusion);
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <MinimalTableHeader headers={["Exclusion", "Description"]} />
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {data.map((row, i) => (
            <tr key={i} className="group hover:bg-zinc-50/30 dark:hover:bg-zinc-900/10">
              <td className="px-3 py-3 align-top w-[220px] min-w-[180px]">
                <div className="font-medium text-zinc-900 dark:text-zinc-100">{row.title}</div>
                {row.severity && (
                  <Badge variant="outline" className={cn("mt-1 text-[9px] px-1.5 py-0 h-4 uppercase tracking-tighter", getSeverityBadgeStyle(row.severity))}>
                    {row.severity}
                  </Badge>
                )}
              </td>
              <td className="px-3 py-3 align-top text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {row.explanation || "This insurance does not apply to claims related to this exclusion."}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ConditionTable({ items, isEntity = false }: { items: any[]; isEntity?: boolean }) {
  const data = items.map(isEntity ? mapEntityToCondition : mapSectionToCondition);
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <MinimalTableHeader headers={["Condition", "Description"]} />
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {data.map((row, i) => (
            <tr key={i} className="group hover:bg-zinc-50/30 dark:hover:bg-zinc-900/10">
              <td className="px-3 py-3 align-top w-[220px] min-w-[180px]">
                <div className="font-medium text-zinc-900 dark:text-zinc-100">{row.title}</div>
                {row.whenApplies && (
                  <div className="mt-1 text-[10px] text-zinc-500 dark:text-zinc-400">
                    Applies to: {row.whenApplies}
                  </div>
                )}
              </td>
              <td className="px-3 py-3 align-top text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {row.requirement || "Policy condition as defined in the coverage form."}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EndorsementTable({ items, isEntity = false }: { items: any[]; isEntity?: boolean }) {
  const data = items.map(isEntity ? mapEntityToEndorsement : mapSectionToEndorsement);
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <MinimalTableHeader headers={["Endorsement", "Description"]} />
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {data.map((row, i) => (
            <tr key={i} className="group hover:bg-zinc-50/30 dark:hover:bg-zinc-900/10">
              <td className="px-3 py-3 align-top w-[220px] min-w-[180px]">
                <div className="font-medium text-zinc-900 dark:text-zinc-100">{row.title}</div>
                {row.type && (
                  <Badge variant="outline" className="mt-1 text-[9px] px-1.5 py-0 h-4 text-zinc-500 border-zinc-200 dark:border-zinc-700">
                    {row.type}
                  </Badge>
                )}
              </td>
              <td className="px-3 py-3 align-top text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {row.whatChanged || (row.impactedCoverage ? `Modifies ${row.impactedCoverage}` : "Endorsement modifying policy terms.")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * ModificationTable - Displays endorsement modifications with rich context.
 * Shows effect category, verbatim language, referenced sections, and severity.
 */
export function ModificationTable({ items }: { items: any[] }) {
  const data = items.map(mapSectionToModification);
  return (
    <div className="space-y-3">
      {data.map((row, i) => (
        <div
          key={i}
          className="rounded-md border border-zinc-200 dark:border-zinc-800 overflow-hidden bg-white dark:bg-zinc-950"
        >
          {/* Header with effect category and severity */}
          <div className="px-3 py-2.5 bg-zinc-50 dark:bg-zinc-900/50 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className={cn(
                  "text-[9px] px-1.5 py-0 h-5 font-medium",
                  getEffectCategoryBadgeStyle(row.effectCategory)
                )}
              >
                {formatEffectCategory(row.effectCategory)}
              </Badge>
              {row.exclusionScope && (
                <span className="text-xs text-zinc-600 dark:text-zinc-400">
                  {row.exclusionScope}
                </span>
              )}
            </div>
            {row.severity && (
              <Badge
                variant="outline"
                className={cn(
                  "text-[9px] px-1.5 py-0 h-5 uppercase tracking-tighter",
                  getSeverityBadgeStyle(row.severity)
                )}
              >
                {row.severity}
              </Badge>
            )}
          </div>

          {/* Content */}
          <div className="px-3 py-3 space-y-2">
            {/* Impacted coverage/section */}
            {row.impactedCoverage && (
              <div className="text-xs">
                <span className="font-medium text-zinc-500 dark:text-zinc-400">
                  Impacts:{" "}
                </span>
                <span className="text-zinc-700 dark:text-zinc-300">
                  {row.impactedCoverage}
                </span>
              </div>
            )}

            {/* Referenced section */}
            {row.referencedSection && (
              <div className="text-xs">
                <span className="font-medium text-zinc-500 dark:text-zinc-400">
                  Section:{" "}
                </span>
                <span className="text-zinc-600 dark:text-zinc-400 font-mono text-[10px]">
                  {row.referencedSection}
                </span>
              </div>
            )}

            {/* Verbatim language (collapsible for long text) */}
            {row.verbatimLanguage && (
              <div className="mt-2 pt-2 border-t border-zinc-100 dark:border-zinc-800">
                <div className="text-[10px] font-medium text-zinc-500 dark:text-zinc-400 mb-1">
                  Policy Language:
                </div>
                <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed italic bg-zinc-50 dark:bg-zinc-900/30 rounded px-2 py-1.5">
                  &ldquo;{row.verbatimLanguage}&rdquo;
                </p>
              </div>
            )}

            {/* Exception conditions */}
            {row.exceptionConditions && (
              <div className="text-xs">
                <span className="font-medium text-zinc-500 dark:text-zinc-400">
                  Conditions:{" "}
                </span>
                <span className="text-zinc-600 dark:text-zinc-400">
                  {row.exceptionConditions}
                </span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export function EntityTable({ entity, index: _index }: { entity: Entity; index: number }) {
  const fields = entity.fields;
  const entityName = normalizeFieldLabel(entity.entity_type);
  const confidence = entity.confidence;
  
  // Combine top-level fields with nested attributes
  const displayFields: [string, unknown][] = [];
  
  Object.entries(fields).forEach(([key, value]) => {
    if (key === "attributes" && typeof value === "object" && value !== null) {
      // Flatten attributes into the display list
      Object.entries(value as Record<string, unknown>).forEach(([attrKey, attrValue]) => {
        displayFields.push([attrKey, attrValue]);
      });
    } else if (key !== "id" && key !== "type" && key !== "confidence") {
      displayFields.push([key, value]);
    }
  });
  
  if (displayFields.length === 0) return null;
  
  return (
    <div className="border border-zinc-200 dark:border-zinc-800 rounded overflow-hidden bg-white dark:bg-zinc-950">
      <div className="px-4 py-3 bg-zinc-50 dark:bg-zinc-900/50 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Tag className="size-3.5 text-zinc-500" />
          <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {entityName}
          </span>
        </div>
        {confidence !== undefined && (
          <span className="text-xs text-zinc-400 dark:text-zinc-500">
            {Math.round(Number(confidence) * 100)}% confidence
          </span>
        )}
      </div>
      <table className="w-full text-sm">
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {displayFields.map(([key, value]) => (
            <tr key={key}>
              <td className="px-4 py-2.5 w-[160px] min-w-[160px] text-xs font-medium text-zinc-500 dark:text-zinc-400 align-top whitespace-nowrap">
                {normalizeFieldLabel(key)}
              </td>
              <td className="px-4 py-2.5 text-zinc-700 dark:text-zinc-300 break-words">
                {formatValue(value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
