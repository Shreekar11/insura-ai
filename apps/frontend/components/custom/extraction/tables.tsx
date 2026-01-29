import React from "react";
import { Tag } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { 
  MinimalTableHeader, 
  SourceLink 
} from "./common";
import { 
  mapRawToCoverage, 
  mapRawToExclusion, 
  mapRawToCondition, 
  mapRawToEndorsement,
  normalizeFieldLabel,
  formatValue,
  getSeverityBadgeStyle
} from "@/utils/extraction-utils";
import { Entity } from "@/types/extraction";

/**
 * Specialized Table Components
 */
export function CoverageTable({ items }: { items: any[] }) {
  const data = items.map(mapRawToCoverage);
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <MinimalTableHeader headers={["Coverage Name", "Type", "Applies To", "Limit", "Deductible", "Source"]} />
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {data.map((row, i) => (
            <tr key={i} className="group hover:bg-zinc-50/30 dark:hover:bg-zinc-900/10">
              <td className="px-3 py-3 align-top min-w-[160px]">
                <div className="font-medium text-zinc-900 dark:text-zinc-100">{row.name}</div>
                {row.description && <div className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-1 leading-relaxed line-clamp-2">{row.description}</div>}
              </td>
              <td className="px-3 py-3 align-top text-xs text-zinc-600 dark:text-zinc-400">{row.type || "—"}</td>
              <td className="px-3 py-3 align-top text-xs text-zinc-600 dark:text-zinc-400">{row.appliesTo || "—"}</td>
              <td className="px-3 py-3 align-top text-xs font-mono">{row.limit}</td>
              <td className="px-3 py-3 align-top text-xs font-mono">{row.deductible}</td>
              <td className="px-3 py-3 align-top text-xs"><SourceLink source={row.source} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ExclusionTable({ items }: { items: any[] }) {
  const data = items.map(mapRawToExclusion);
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <MinimalTableHeader headers={["Exclusion", "Scope", "Severity", "Impact", "Source"]} />
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {data.map((row, i) => (
            <tr key={i} className="group hover:bg-zinc-50/30 dark:hover:bg-zinc-900/10">
              <td className="px-3 py-3 align-top min-w-[140px]">
                <div className="font-medium text-zinc-900 dark:text-zinc-100">{row.title}</div>
                {row.explanation && <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 line-clamp-2">{row.explanation}</div>}
              </td>
              <td className="px-3 py-3 align-top text-xs text-zinc-600 dark:text-zinc-400">{row.scope || "—"}</td>
              <td className="px-3 py-3 align-top">
                <Badge variant="outline" className={cn("text-[9px] px-1 py-0 h-4 uppercase tracking-tighter", getSeverityBadgeStyle(row.severity || ""))}>
                  {row.severity || "—"}
                </Badge>
              </td>
              <td className="px-3 py-3 align-top text-xs text-zinc-600 dark:text-zinc-400">{row.affects || "—"}</td>
              <td className="px-3 py-3 align-top text-xs"><SourceLink source={row.source} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ConditionTable({ items }: { items: any[] }) {
  const data = items.map(mapRawToCondition);
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <MinimalTableHeader headers={["Condition", "Applies To", "Requirement", "Source"]} />
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {data.map((row, i) => (
            <tr key={i} className="group hover:bg-zinc-50/30 dark:hover:bg-zinc-900/10">
              <td className="px-3 py-3 align-top min-w-[140px]">
                <div className="font-medium text-zinc-900 dark:text-zinc-100">{row.title}</div>
              </td>
              <td className="px-3 py-3 align-top text-xs text-zinc-600 dark:text-zinc-400">{row.whenApplies || "—"}</td>
              <td className="px-3 py-3 align-top text-xs text-zinc-600 dark:text-zinc-400 max-w-[200px]">
                <div className="line-clamp-3">{row.requirement || "—"}</div>
                {row.consequence && <div className="mt-2 text-[10px] italic text-zinc-500">Consequence: {row.consequence}</div>}
              </td>
              <td className="px-3 py-3 align-top text-xs"><SourceLink source={row.source} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EndorsementTable({ items }: { items: any[] }) {
  const data = items.map(mapRawToEndorsement);
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <MinimalTableHeader headers={["Endorsement", "Change", "Impact", "Source"]} />
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {data.map((row, i) => (
            <tr key={i} className="group hover:bg-zinc-50/30 dark:hover:bg-zinc-900/10">
              <td className="px-3 py-3 align-top min-w-[140px]">
                <div className="font-medium text-zinc-900 dark:text-zinc-100">{row.title}</div>
              </td>
              <td className="px-3 py-3 align-top text-xs text-zinc-600 dark:text-zinc-400 max-w-[200px]">
                <div className="line-clamp-3">{row.whatChanged || "—"}</div>
              </td>
              <td className="px-3 py-3 align-top">
                <div className="text-xs text-zinc-600 dark:text-zinc-400">{row.impactedCoverage || "—"}</div>
                {row.materiality && <div className="mt-1 text-[9px] uppercase font-semibold text-zinc-500">{row.materiality} Materiality</div>}
              </td>
              <td className="px-3 py-3 align-top text-xs"><SourceLink source={row.source} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EntityTable({ entity, index }: { entity: Entity; index: number }) {
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
