import React from "react";
import { AlertTriangle, Shield, FileCheck, FileText, Info } from "lucide-react";
import { 
  Section, 
  Entity, 
  CoverageData, 
  ExclusionData, 
  ConditionData, 
  EndorsementData 
} from "../types/extraction";

/**
 * Converts snake_case or camelCase field keys to human-readable Title Case labels.
 */
export function normalizeFieldLabel(key: string): string {
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
export function formatValue(value: unknown): string {
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
export function getSectionIcon(sectionType: string) {
  switch (sectionType.toLowerCase()) {
    case "exclusions":
    case "exclusion":
      return <AlertTriangle className="size-4" />;
    case "coverages":
    case "coverage":
      return <Shield className="size-4" />;
    case "conditions":
    case "condition":
      return <FileCheck className="size-4" />;
    case "endorsements":
    case "endorsement":
      return <FileText className="size-4" />;
    default:
      return <Info className="size-4" />;
  }
}

/**
 * Returns badge styling based on severity.
 */
export function getSeverityBadgeStyle(severity: string) {
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
 * Checks if a section has items to display.
 */
export function hasSectionItems(section: Section): boolean {
  if (!section.fields) return false;
  
  const mainField = Object.values(section.fields)[0];
  return Array.isArray(mainField) && mainField.length > 0;
}

/**
 * Groups entities by their type.
 */
export function groupEntitiesByType(entities: Entity[]): Map<string, Entity[]> {
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
 * Mapping functions for structured data
 */
export function mapRawToCoverage(item: any): CoverageData {
  const fields = item.fields?.attributes || item;
  return {
    name: fields.coverage_name || fields.title || "Unknown Coverage",
    type: fields.coverage_type || fields.type,
    description: fields.description || fields.what_it_covers,
    limit: formatValue(fields.limit_amount || fields.limit),
    deductible: formatValue(fields.deductible),
    appliesTo: fields.applies_to,
    source: fields.source || fields.reference
  };
}

export function mapRawToExclusion(item: any): ExclusionData {
  const fields = item.fields?.attributes || item;
  return {
    title: fields.title || "Unknown Exclusion",
    affects: fields.impacted_coverage || fields.affects,
    scope: fields.exclusion_scope || fields.scope,
    severity: fields.severity,
    explanation: fields.description || fields.explanation,
    source: fields.source || fields.reference
  };
}

export function mapRawToCondition(item: any): ConditionData {
  const fields = item.fields?.attributes || item;
  return {
    title: fields.title || "Unknown Condition",
    whenApplies: fields.applies_to || fields.when_it_applies,
    requirement: Array.isArray(fields.requirements) ? fields.requirements.join("; ") : fields.requirements,
    consequence: Array.isArray(fields.consequences) ? fields.consequences.join("; ") : fields.consequences,
    source: fields.source || fields.reference
  };
}

export function mapRawToEndorsement(item: any): EndorsementData {
  const fields = item.fields?.attributes || item;
  return {
    title: fields.title || fields.name || "Unknown Endorsement",
    type: fields.type,
    whatChanged: fields.what_changed || fields.description,
    impactedCoverage: fields.impacted_coverage,
    materiality: fields.materiality,
    source: fields.source || fields.reference
  };
}
