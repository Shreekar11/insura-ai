export interface ExtractionOutputSidebarProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workflowId: string | null;
  documentId: string | null;
}

export interface SectionItem {
  title?: string | null;
  [key: string]: unknown;
}

export interface Section {
  section_type: string;
  fields: Record<string, SectionItem[] | unknown>;
  confidence?: { overall: number };
}

export interface Entity {
  entity_type: string;
  fields: Record<string, unknown>;
  confidence?: string | number;
}

// Interfaces for structured data
export interface CoverageData {
  name: string;
  type?: string;
  description?: string;
  limit?: string;
  deductible?: string;
  appliesTo?: string;
  source?: string;
  // Rich fields from effective_coverages
  confidence?: number;
  isModified?: boolean;
  isStandardProvision?: boolean;
  effectiveTerms?: Record<string, string>;
  modificationDetails?: string;
  limits?: { amount?: number; description?: string };
}

export interface ExclusionData {
  title: string;
  affects?: string;
  scope?: string;
  severity?: string;
  explanation?: string;
  source?: string;
}

export interface ConditionData {
  title: string;
  whenApplies?: string;
  requirement?: string;
  consequence?: string;
  source?: string;
}

export interface EndorsementData {
  title: string;
  type?: string;
  whatChanged?: string;
  impactedCoverage?: string;
  materiality?: string;
  source?: string;
  // Extended fields
  endorsementNumber?: string;
  effectiveDate?: string;
}

/**
 * Endorsement modification data - represents how an endorsement modifies
 * base policy coverages or exclusions.
 */
export interface ModificationData {
  effectCategory: "introduces_exclusion" | "narrows_exclusion" | "removes_exclusion" | "expands_coverage" | "restricts_coverage" | string;
  verbatimLanguage?: string;
  referencedSection?: string;
  severity?: "Minor" | "Material" | "Major" | "Critical" | string;
  impactedCoverage?: string;
  impactedExclusion?: string;
  exclusionScope?: string;
  exclusionEffect?: string;
  exceptionConditions?: string;
  reasoning?: string;
}

/**
 * Effective coverage - synthesized coverage with all modifications applied.
 * Mirrors backend effective_coverages structure.
 */
export interface EffectiveCoverageData {
  coverageName: string;
  coverageType?: string;
  description?: string;
  confidence?: number;
  limits?: { amount?: number; description?: string } | null;
  deductibles?: { amount?: number; description?: string } | null;
  isModified?: boolean;
  isStandardProvision?: boolean;
  modificationDetails?: string | null;
  effectiveTerms?: Record<string, string>;
  sources?: string[];
  sourceForm?: string | null;
  formSection?: string | null;
  canonicalId?: string | null;
}
