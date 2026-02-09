import React from "react";
import {
  ExternalLink,
  ChevronDown,
  ChevronRight,
  FileText,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { SectionItem } from "@/types/extraction";
import {
  normalizeFieldLabel,
  formatValue,
  getSeverityBadgeStyle,
} from "@/utils/extraction-utils";

/**
 * Fields to exclude from the detail table (shown separately or not useful).
 */
export const EXCLUDED_FIELDS = new Set(["title", "id", "type", "severity"]);

/**
 * Minimal Table Header component
 */
export function MinimalTableHeader({ headers }: { headers: string[] }) {
  return (
    <thead className="bg-zinc-50/50 dark:bg-zinc-900/50">
      <tr>
        {headers.map((header) => (
          <th
            key={header}
            className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-zinc-800"
          >
            {header}
          </th>
        ))}
      </tr>
    </thead>
  );
}

/**
 * Source link component
 */
export function SourceLink({ source }: { source?: string }) {
  if (!source) return <span className="text-zinc-400">—</span>;
  return (
    <button className="flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline">
      <span className="truncate max-w-[100px]">{source}</span>
      <ExternalLink className="size-3 shrink-0" />
    </button>
  );
}

/**
 * Renders a single item's details in a table format (Fallback).
 */
export function ItemDetailTable({ item }: { item: SectionItem }) {
  const displayFields = Object.entries(item).filter(
    ([key]) =>
      !EXCLUDED_FIELDS.has(key) &&
      item[key] !== null &&
      item[key] !== undefined,
  );

  if (displayFields.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {displayFields.map(([key, value]) => (
            <tr key={key} className="group">
              <td className="px-3 py-2.5 w-[140px] min-w-[140px] bg-zinc-50/50 dark:bg-zinc-900/50 text-xs font-medium text-zinc-500 dark:text-zinc-400 align-top whitespace-nowrap">
                {normalizeFieldLabel(key)}
              </td>
              <td className="px-3 py-2.5 text-zinc-700 dark:text-zinc-300 break-words">
                {Array.isArray(value) ? (
                  <ul className="list-disc list-inside space-y-1">
                    {value.map((v, i) => (
                      <li key={i} className="text-sm leading-relaxed">
                        {formatValue(v)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="leading-relaxed">{formatValue(value)}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Renders a collapsible section item card.
 */
export function SectionItemCard({
  item,
  index,
  onItemClick,
  sourceType,
  itemId,
}: {
  item: SectionItem;
  index: number;
  onItemClick?: (sourceType: string, sourceId: string) => void;
  sourceType?: string;
  itemId?: string;
}) {
  const [isOpen, setIsOpen] = React.useState(false);
  const title = item.title || `Item ${index + 1}`;
  const severity = item.severity as string | undefined;

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="border border-zinc-200 dark:border-zinc-800 rounded overflow-hidden bg-white dark:bg-zinc-950 group/card">
        <div className="flex items-center">
          <CollapsibleTrigger className="flex-1 px-4 py-3 flex items-center justify-between gap-3 hover:bg-zinc-50 dark:hover:bg-zinc-900/50 transition-colors">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <div className="shrink-0 text-zinc-400 dark:text-zinc-500">
                {isOpen ? (
                  <ChevronDown className="size-4" />
                ) : (
                  <ChevronRight className="size-4" />
                )}
              </div>
              <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100 truncate text-left">
                {title}
              </span>
            </div>
            {severity && (
              <Badge
                variant="outline"
                className={cn(
                  "shrink-0 text-[10px] font-medium uppercase tracking-wide",
                  getSeverityBadgeStyle(severity),
                )}
              >
                {severity}
              </Badge>
            )}
          </CollapsibleTrigger>

          {onItemClick && sourceType && itemId && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => onItemClick(sourceType, itemId)}
                    className="p-3 text-zinc-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                  >
                    <FileText className="size-4 opacity-40 group-hover/card:opacity-100 transition-opacity" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" className="text-[10px] py-1 px-2">
                  View citation in PDF
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
        <CollapsibleContent>
          <div className="px-4 pb-4 pt-1">
            <ItemDetailTable item={item} />
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
