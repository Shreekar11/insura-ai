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
}
