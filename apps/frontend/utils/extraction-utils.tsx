import React from "react";
import { AlertTriangle, Shield, FileCheck, FileText, Info } from "lucide-react";
import {
  Section,
  Entity,
  CoverageData,
  ExclusionData,
  ConditionData,
  EndorsementData,
  ModificationData,
  EffectiveCoverageData
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
 * Mapping functions for Entity data (from 'entities' array)
 * Entities usually have fields within an 'attributes' object.
 */
export function mapEntityToCoverage(entity: any): CoverageData {
  const fields = entity.fields?.attributes || entity.fields || {};
  return {
    name: fields.name || fields.coverage_name || "Unknown Coverage",
    type: fields.type || fields.coverage_type,
    description: fields.description || fields.what_it_covers,
    limit: formatValue(fields.limit_amount || fields.limit),
    deductible: formatValue(fields.deductible),
    appliesTo: fields.applies_to,
    source: fields.source || fields.reference
  };
}

export function mapEntityToExclusion(entity: any): ExclusionData {
  const fields = entity.fields?.attributes || entity.fields || {};
  return {
    title: fields.name || fields.title || fields.exclusion_name || "Unknown Exclusion",
    affects: fields.impacted_coverage || fields.affects,
    scope: fields.exclusion_scope || fields.scope,
    severity: fields.severity,
    explanation: fields.description || fields.explanation,
    source: fields.source || fields.reference
  };
}

export function mapEntityToCondition(entity: any): ConditionData {
  const fields = entity.fields?.attributes || entity.fields || {};
  return {
    title: fields.name || fields.title || fields.condition_name || "Unknown Condition",
    whenApplies: fields.applies_to || fields.when_it_applies,
    requirement: Array.isArray(fields.requirements) ? fields.requirements.join("; ") : fields.requirements,
    consequence: Array.isArray(fields.consequences) ? fields.consequences.join("; ") : fields.consequences,
    source: fields.source || fields.reference
  };
}

export function mapEntityToEndorsement(entity: any): EndorsementData {
  const fields = entity.fields?.attributes || entity.fields || {};
  return {
    title: fields.name || fields.title || fields.endorsement_name || "Unknown Endorsement",
    type: fields.type,
    whatChanged: fields.what_changed || fields.description,
    impactedCoverage: fields.impacted_coverage,
    materiality: fields.materiality,
    source: fields.source || fields.reference
  };
}

/**
 * Mapping functions for Section data (from 'extracted_data' object)
 * Section items are usually flatter and may have different field names.
 */
export function mapSectionToCoverage(item: any): CoverageData {
  return {
    name: item.coverage_name || item.name || "Unknown Coverage",
    type: item.coverage_type || item.type,
    description: item.description || item.what_it_covers,
    limit: formatValue(item.limit_amount || item.limit || item.limits),
    deductible: formatValue(item.deductible || item.deductibles),
    appliesTo: item.applies_to,
    source: item.source || item.reference || (Array.isArray(item.sources) ? item.sources.join(", ") : undefined)
  };
}

export function mapSectionToExclusion(item: any): ExclusionData {
  return {
    title: item.exclusion_name || item.title || "Unknown Exclusion",
    affects: item.impacted_coverage || item.impacted_coverages?.[0] || item.affects,
    scope: item.exclusion_scope || item.scope,
    severity: item.severity,
    explanation: item.description || item.explanation,
    source: item.source || item.reference || (Array.isArray(item.sources) ? item.sources.join(", ") : undefined)
  };
}

export function mapSectionToCondition(item: any): ConditionData {
  return {
    title: item.condition_name || item.title || "Unknown Condition",
    whenApplies: item.applies_to || item.when_it_applies,
    requirement: Array.isArray(item.requirements) ? item.requirements.join("; ") : item.requirement,
    consequence: Array.isArray(item.consequences) ? item.consequences.join("; ") : item.consequence,
    source: item.source || item.reference || (Array.isArray(item.sources) ? item.sources.join(", ") : undefined)
  };
}

export function mapSectionToEndorsement(item: any): EndorsementData {
  return {
    title: item.endorsement_name || item.title || "Unknown Endorsement",
    type: item.endorsement_type || item.type,
    whatChanged: item.what_changed || item.description,
    impactedCoverage: item.impacted_coverage,
    materiality: item.materiality,
    source: item.source || item.reference || (Array.isArray(item.sources) ? item.sources.join(", ") : undefined)
  };
}

/**
 * Legacy mapping functions - Refactored to use Entity mapping by default
 */
export function mapRawToCoverage(item: any): CoverageData {
  return mapEntityToCoverage(item);
}

export function mapRawToExclusion(item: any): ExclusionData {
  return mapEntityToExclusion(item);
}

export function mapRawToCondition(item: any): ConditionData {
  return mapEntityToCondition(item);
}

export function mapRawToEndorsement(item: any): EndorsementData {
  return mapEntityToEndorsement(item);
}

/**
 * Maps a modification item from endorsement extraction to ModificationData.
 * Modifications represent how endorsements modify base policy coverages/exclusions.
 */
export function mapSectionToModification(item: any): ModificationData {
  return {
    effectCategory: item.effect_category || "unknown",
    verbatimLanguage: item.verbatim_language,
    referencedSection: item.referenced_section,
    severity: item.severity,
    impactedCoverage: item.impacted_coverage,
    impactedExclusion: item.impacted_exclusion,
    exclusionScope: item.exclusion_scope,
    exclusionEffect: item.exclusion_effect,
    exceptionConditions: item.exception_conditions,
    reasoning: item.reasoning
  };
}

/**
 * Maps an effective coverage item to EffectiveCoverageData.
 * Effective coverages are synthesized from base policy + endorsement modifications.
 */
export function mapToEffectiveCoverage(item: any): EffectiveCoverageData {
  return {
    coverageName: item.coverage_name || "Unknown Coverage",
    coverageType: item.coverage_type,
    description: item.description,
    confidence: item.confidence,
    limits: item.limits,
    deductibles: item.deductibles,
    isModified: item.is_modified,
    isStandardProvision: item.is_standard_provision,
    modificationDetails: item.modification_details,
    effectiveTerms: item.effective_terms,
    sources: item.sources,
    sourceForm: item.source_form,
    formSection: item.form_section,
    canonicalId: item.canonical_id
  };
}

/**
 * Returns badge styling based on effect category.
 */
export function getEffectCategoryBadgeStyle(category: string) {
  switch (category?.toLowerCase()) {
    case "introduces_exclusion":
      return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800";
    case "removes_exclusion":
      return "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800";
    case "narrows_exclusion":
      return "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 border-blue-200 dark:border-blue-800";
    case "expands_coverage":
      return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800";
    case "restricts_coverage":
      return "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400 border-orange-200 dark:border-orange-800";
    default:
      return "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400 border-zinc-200 dark:border-zinc-700";
  }
}

/**
 * Formats effect category for display.
 */
export function formatEffectCategory(category: string): string {
  if (!category) return "Unknown";
  return category
    .replace(/_/g, " ")
    .replace(/\b\w/g, (l) => l.toUpperCase());
}

/**
 * Detects if section fields contain modifications array.
 * Endorsement extractions store modifications in fields.modifications.
 */
export function hasModifications(fields: Record<string, unknown>): boolean {
  return Array.isArray(fields?.modifications) && fields.modifications.length > 0;
}

/**
 * Gets the primary data array from section fields.
 * Handles different field structures: coverages[], exclusions[], modifications[], endorsements[]
 */
export function getSectionItems(fields: Record<string, unknown>): { items: any[]; type: string } {
  // Check for modifications first (endorsement semantic projection output)
  if (hasModifications(fields)) {
    return { items: fields.modifications as any[], type: "modifications" };
  }

  // Check for specific section type arrays
  if (Array.isArray(fields.coverages)) {
    return { items: fields.coverages, type: "coverages" };
  }
  if (Array.isArray(fields.exclusions)) {
    return { items: fields.exclusions, type: "exclusions" };
  }
  if (Array.isArray(fields.conditions)) {
    return { items: fields.conditions, type: "conditions" };
  }
  if (Array.isArray(fields.endorsements)) {
    return { items: fields.endorsements, type: "endorsements" };
  }

  // Fallback: get first array value
  const firstValue = Object.values(fields)[0];
  if (Array.isArray(firstValue)) {
    return { items: firstValue, type: "unknown" };
  }

  return { items: [], type: "empty" };
}
