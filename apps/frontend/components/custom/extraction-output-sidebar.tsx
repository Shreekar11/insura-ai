"use client";

import { Loader2, FileText, Tag, X } from "lucide-react";
import { useExtractedData } from "@/hooks/use-extracted-data";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  ExtractionOutputSidebarProps, 
  Section, 
  Entity 
} from "@/types/extraction";
import { 
  hasSectionItems, 
  groupEntitiesByType 
} from "@/utils/extraction-utils";
import { SectionBlock } from "./extraction/section-block";
import { EntityGroup } from "./extraction/entity-group";

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
            Extracted Output
          </h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Sections and entities extracted from the document
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
      </div>
    </div>
  );
}
