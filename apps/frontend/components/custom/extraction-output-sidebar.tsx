"use client";

import React from "react";
import { Loader2, FileText, Tag, X, AlertTriangle, Shield, FileCheck, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useExtractedData } from "@/hooks/use-extracted-data";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

interface ExtractionOutputSidebarProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workflowId: string | null;
  documentId: string | null;
}

interface SectionItem {
  title?: string | null;
  [key: string]: unknown;
}

interface Section {
  section_type: string;
  fields: Record<string, SectionItem[] | unknown>;
  confidence?: { overall: number };
}

interface Entity {
  entity_type: string;
  fields: Record<string, unknown>;
  confidence?: string | number;
}

/**
 * Converts snake_case or camelCase field keys to human-readable Title Case labels.
 * Examples:
 *   exclusion_type → Exclusion Type
 *   policy_start_date → Policy Start Date
 *   coverageName → Coverage Name
 */
function normalizeFieldLabel(key: string): string {
  if (!key) return "";
  
  // Handle snake_case and camelCase
  const words = key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .toLowerCase()
    .split(" ");
  
  return words
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Safely formats a value for display in the table.
 * Handles arrays, objects, null/undefined, and primitives.
 */
function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  
  if (Array.isArray(value)) {
    if (value.length === 0) return "—";
    // For simple arrays, join with commas
    if (value.every((v) => typeof v === "string" || typeof v === "number")) {
      return value.join(", ");
    }
    // For complex arrays, show count
    return `${value.length} items`;
  }
  
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  
  return String(value);
}

/**
 * Returns the appropriate icon for a section type.
 */
function getSectionIcon(sectionType: string) {
  switch (sectionType.toLowerCase()) {
    case "exclusions":
      return <AlertTriangle className="size-4" />;
    case "coverages":
      return <Shield className="size-4" />;
    case "conditions":
      return <FileCheck className="size-4" />;
    default:
      return <FileText className="size-4" />;
  }
}

/**
 * Returns badge styling based on severity.
 */
function getSeverityBadgeStyle(severity: string) {
  switch (severity?.toLowerCase()) {
    case "critical":
      return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800";
    case "major":
      return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-800";
    case "material":
      return "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400 border-orange-200 dark:border-orange-800";
    case "minor":
      return "bg-slate-100 text-slate-600 dark:bg-slate-800/50 dark:text-slate-400 border-slate-200 dark:border-slate-700";
    default:
      return "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400 border-zinc-200 dark:border-zinc-700";
  }
}

/**
 * Fields to exclude from the detail table (shown separately or not useful).
 */
const EXCLUDED_FIELDS = new Set(["title", "id", "type", "severity"]);

/**
 * Checks if a section has items to display.
 */
function hasSectionItems(section: Section): boolean {
  if (!section.fields) return false;
  
  const mainField = Object.values(section.fields)[0];
  return Array.isArray(mainField) && mainField.length > 0;
}

/**
 * Renders a single item's details in a table format.
 */
function ItemDetailTable({ item }: { item: SectionItem }) {
  const displayFields = Object.entries(item).filter(
    ([key]) => !EXCLUDED_FIELDS.has(key) && item[key] !== null && item[key] !== undefined
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
function SectionItemCard({ item, index }: { item: SectionItem; index: number }) {
  const [isOpen, setIsOpen] = React.useState(false);
  const title = item.title || `Item ${index + 1}`;
  const severity = item.severity as string | undefined;
  
  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden bg-white dark:bg-zinc-950">
        <CollapsibleTrigger className="w-full px-4 py-3 flex items-center justify-between gap-3 hover:bg-zinc-50 dark:hover:bg-zinc-900/50 transition-colors">
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
              className={cn("shrink-0 text-[10px] font-medium uppercase tracking-wide", getSeverityBadgeStyle(severity))}
            >
              {severity}
            </Badge>
          )}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-4 pb-4 pt-1">
            <ItemDetailTable item={item} />
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

/**
 * Renders a section with its items.
 */
function SectionBlock({ section, index }: { section: Section; index: number }) {
  const [isOpen, setIsOpen] = React.useState(true);
  const sectionName = normalizeFieldLabel(section.section_type);
  const items = Object.values(section.fields)[0];
  const itemList = Array.isArray(items) ? items as SectionItem[] : [];
  const confidence = section.confidence?.overall;
  
  if (itemList.length === 0) return null;
  
  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="mb-6 last:mb-0">
        <CollapsibleTrigger className="w-full flex items-center justify-between gap-3 py-2 group">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400">
              {getSectionIcon(section.section_type)}
            </div>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {sectionName}
            </h3>
            <Badge variant="secondary" className="text-xs font-normal">
              {itemList.length}
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            {confidence !== undefined && (
              <span className="text-xs text-zinc-400 dark:text-zinc-500">
                {Math.round(confidence * 100)}% confidence
              </span>
            )}
            <div className="text-zinc-400 dark:text-zinc-500 transition-transform group-data-[state=open]:rotate-180">
              <ChevronDown className="size-4" />
            </div>
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-3 space-y-2">
            {itemList.map((item, idx) => (
              <SectionItemCard key={item.title || `item-${idx}`} item={item} index={idx} />
            ))}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

/**
 * Renders an entity in a table format.
 */
function EntityTable({ entity, index }: { entity: Entity; index: number }) {
  const fields = entity.fields;
  const attributes = fields.attributes as Record<string, unknown> | undefined;
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
    <div className="border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden bg-white dark:bg-zinc-950">
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

/**
 * Groups entities by their type.
 */
function groupEntitiesByType(entities: Entity[]): Map<string, Entity[]> {
  const grouped = new Map<string, Entity[]>();
  
  entities.forEach((entity) => {
    const type = entity.entity_type;
    if (!grouped.has(type)) {
      grouped.set(type, []);
    }
    grouped.get(type)!.push(entity);
  });
  
  return grouped;
}

/**
 * Renders a group of entities of the same type.
 */
function EntityGroup({ type, entities }: { type: string; entities: Entity[] }) {
  const [isOpen, setIsOpen] = React.useState(true);
  const typeName = normalizeFieldLabel(type);
  
  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="mb-6 last:mb-0">
        <CollapsibleTrigger className="w-full flex items-center justify-between gap-3 py-2 group">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400">
              <Tag className="size-4" />
            </div>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {typeName}
            </h3>
            <Badge variant="secondary" className="text-xs font-normal">
              {entities.length}
            </Badge>
          </div>
          <div className="text-zinc-400 dark:text-zinc-500 transition-transform group-data-[state=open]:rotate-180">
            <ChevronDown className="size-4" />
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-3 space-y-3">
            {entities.map((entity, idx) => (
              <EntityTable key={entity.fields.id as string || `entity-${idx}`} entity={entity} index={idx} />
            ))}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

export function ExtractionOutputSidebar({
  open,
  onOpenChange,
  workflowId,
  documentId,
}: ExtractionOutputSidebarProps) {
  const { data, isLoading, error } = useExtractedData(
    open ? workflowId : null,
    open ? documentId : null
  );

  const sections = (data?.extracted_data?.sections || []) as Section[];
  const entities = (data?.extracted_data?.entities || []) as Entity[];
  
  // Filter sections that have actual items to display
  const validSections = sections.filter(hasSectionItems);
  const groupedEntities = groupEntitiesByType(entities);
  const hasData = validSections.length > 0 || entities.length > 0;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-lg md:max-w-xl lg:max-w-2xl xl:max-w-3xl p-0 flex flex-col overflow-scroll"
      >
        <SheetHeader className="px-6 py-5 border-b border-zinc-200 dark:border-zinc-800 shrink-0 bg-zinc-50/50 dark:bg-zinc-900/50">
          <SheetTitle className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Extracted Output
          </SheetTitle>
          <SheetDescription className="text-sm text-zinc-500 dark:text-zinc-400">
            Sections and entities extracted from the document
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1">
          <div className="px-6 py-5">
            {/* Loading State */}
            {isLoading && (
              <div className="flex flex-col items-center justify-center py-16">
                <div className="p-3 rounded-full bg-zinc-100 dark:bg-zinc-800 mb-4">
                  <Loader2 className="size-6 text-zinc-500 animate-spin" />
                </div>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  Loading extracted data...
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
                  Failed to load extracted data
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-xs">
                  {error.message}
                </p>
              </div>
            )}

            {/* Data Display */}
            {!isLoading && !error && hasData && (
              <div className="space-y-8">
                {/* Sections */}
                {validSections.length > 0 && (
                  <div>
                    <div className="flex items-center gap-2 mb-4 pb-3 border-b border-zinc-200 dark:border-zinc-800">
                      <FileText className="size-4 text-zinc-500" />
                      <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                        Extracted Sections
                      </h2>
                    </div>
                    {validSections.map((section, index) => (
                      <SectionBlock
                        key={`section-${section.section_type}-${index}`}
                        section={section}
                        index={index}
                      />
                    ))}
                  </div>
                )}

                {/* Entities */}
                {entities.length > 0 && (
                  <div>
                    <div className="flex items-center gap-2 mb-4 pb-3 border-b border-zinc-200 dark:border-zinc-800">
                      <Tag className="size-4 text-zinc-500" />
                      <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                        Extracted Entities
                      </h2>
                    </div>
                    {Array.from(groupedEntities.entries()).map(([type, entityList]) => (
                      <EntityGroup key={type} type={type} entities={entityList} />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Empty State */}
            {!isLoading && !error && !hasData && (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="p-4 rounded-full bg-zinc-100 dark:bg-zinc-800 mb-4">
                  <FileText className="size-8 text-zinc-400 dark:text-zinc-500" />
                </div>
                <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mb-1">
                  No extracted data available
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-xs">
                  The document extraction did not produce any sections or entities.
                </p>
              </div>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
