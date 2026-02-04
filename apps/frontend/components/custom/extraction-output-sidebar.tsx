"use client";

import {
  Search,
  FileText,
  Download,
  Loader2,
  X,
} from "lucide-react";
import React from "react";
import { useExtractedData } from "@/hooks/use-extracted-data";
import { usePDFHighlight } from "@/contexts/pdf-highlight-context";
import { useCitations, findCitation } from "@/hooks/use-citations";
import { useDocuments } from "@/hooks/use-documents";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  hasSectionItems,
  getSectionItems,
  mapSectionToCoverage,
  mapSectionToExclusion,
  mapSectionToCondition,
  mapSectionToEndorsement,
  mapSectionToModification,
  mapEntityToCoverage,
  mapEntityToExclusion,
  mapEntityToCondition,
  mapEntityToEndorsement,
  normalizeFieldLabel,
  formatValue,
} from "@/utils/extraction-utils";
import {
  ExtractionOutputSidebarProps,
  Section,
  Entity,
} from "@/types/extraction";

export function ExtractionOutputSidebar({
  open,
  onOpenChange,
  workflowId,
  documentId,
}: ExtractionOutputSidebarProps) {
  const { data, isLoading, error } = useExtractedData(
    open ? workflowId : null,
    open ? documentId : null,
  );

  const { data: citationsData } = useCitations(
    open ? workflowId : null,
    open ? documentId : null,
  );
  const { data: documentsData } = useDocuments(workflowId ?? undefined);
  const { highlightCitation } = usePDFHighlight();

  const [searchQuery, setSearchQuery] = React.useState("");

  const sections = (data?.extracted_data?.sections || []) as Section[];
  const entities = (data?.extracted_data?.entities || []) as Entity[];

  const validSections = sections.filter(hasSectionItems);

  const flattenedData = React.useMemo(() => {
    const items: Array<{
      id: string;
      type: string;
      item: string;
      content: string;
      sourceSection: string;
    }> = [];

    // Process Sections
    validSections.forEach((section) => {
      const { items: itemList, type: dataType } = getSectionItems(
        section.fields,
      );
      const sectionType = section.section_type.toLowerCase();
      const baseType = normalizeFieldLabel(sectionType.replace(/s$/, ""));

      itemList.forEach((item, idx) => {
        let mapped: any;
        let sourceType: string = "clause";

        if (dataType === "modifications") {
          mapped = mapSectionToModification(item);
          sourceType = "clause";
        } else {
          switch (sectionType) {
            case "coverages":
              mapped = mapSectionToCoverage(item);
              sourceType = "effective_coverage";
              break;
            case "exclusions":
              mapped = mapSectionToExclusion(item);
              sourceType = "effective_exclusion";
              break;
            case "conditions":
              mapped = mapSectionToCondition(item);
              sourceType = "condition";
              break;
            case "endorsements":
              mapped = mapSectionToEndorsement(item);
              sourceType = "endorsement";
              break;
            default:
              mapped = {
                title: item.title || item.name || "Unknown Item",
                description: item.description || item.content || "",
                canonicalId: item.canonical_id || item.id,
              };
          }
        }

        if (mapped) {
          const itemTitle =
            mapped.name ||
            mapped.title ||
            mapped.coverageName ||
            mapped.exclusionName ||
            "";
          items.push({
            id: mapped.canonicalId || item.id || `${sectionType}-${idx}`,
            type: sourceType,
            item: `${baseType} - ${itemTitle}`,
            content:
              mapped.description ||
              mapped.explanation ||
              mapped.requirement ||
              mapped.whatChanged ||
              mapped.verbatimLanguage ||
              "",
            sourceSection: sectionType,
          });
        }
      });
    });

    // Process Entities
    entities.forEach((entity, idx) => {
      const entityType = entity.entity_type.toLowerCase();
      const baseType = normalizeFieldLabel(entityType.replace(/s$/, ""));
      let mapped: any;
      let sourceType: string = "clause";

      switch (entityType) {
        case "coverage":
        case "coverages":
          mapped = mapEntityToCoverage(entity);
          sourceType = "effective_coverage";
          break;
        case "exclusion":
        case "exclusions":
          mapped = mapEntityToExclusion(entity);
          sourceType = "effective_exclusion";
          break;
        case "condition":
        case "conditions":
          mapped = mapEntityToCondition(entity);
          sourceType = "condition";
          break;
        case "endorsement":
        case "endorsements":
          mapped = mapEntityToEndorsement(entity);
          sourceType = "endorsement";
          break;
        default:
          mapped = {
            title: entity.entity_type,
            description: formatValue(entity.fields),
            canonicalId: (entity as any).id,
          };
      }

      const itemTitle = mapped.name || mapped.title || "";
      items.push({
        id: mapped.canonicalId || (entity as any).id || `entity-${idx}`,
        type: sourceType,
        item: `${baseType} - ${itemTitle}`,
        content:
          mapped.description ||
          mapped.explanation ||
          mapped.requirement ||
          mapped.whatChanged ||
          "",
        sourceSection: entityType,
      });
    });

    return items;
  }, [validSections, entities]);

  const filteredData = React.useMemo(() => {
    if (!searchQuery) return flattenedData;
    const lowerQuery = searchQuery.toLowerCase();
    return flattenedData.filter(
      (item) =>
        item.item.toLowerCase().includes(lowerQuery) ||
        item.content.toLowerCase().includes(lowerQuery),
    );
  }, [flattenedData, searchQuery]);

  const hasData = flattenedData.length > 0;

  const currentDocument = documentsData?.documents?.find(
    (doc) => doc.id === documentId,
  );
  const pdfUrl = currentDocument?.file_path;

  const handleItemClick = (sourceType: string, sourceId: string) => {
    if (!citationsData?.citations || !pdfUrl) {
      console.warn("Citations or PDF URL not available");
      return;
    }

    const citation = findCitation(
      citationsData.citations,
      sourceType,
      sourceId,
    );
    if (citation) {
      highlightCitation(citation, pdfUrl, citationsData.pageDimensions);
    } else {
      console.warn(`Citation not found for ${sourceType}:${sourceId}`);
    }
  };

  const hasCitation = (type: string, id: string) => {
    if (!citationsData?.citations) return false;
    return !!findCitation(citationsData.citations, type, id);
  };

  if (!open) return null;

  return (
    <div
      className="flex flex-col h-full overflow-hidden bg-white dark:bg-zinc-950"
      onWheel={(e) => {
        e.stopPropagation();
      }}
    >
      <div className="px-6 py-[0.47rem] border-b border-zinc-200 dark:border-zinc-800 shrink-0 bg-white dark:bg-zinc-950 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-1.5 rounded bg-zinc-100 dark:bg-zinc-800">
            <FileText className="size-4 text-zinc-600 dark:text-zinc-400" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 leading-tight">
              {currentDocument?.document_name || "Document Extraction"}
            </h2>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
          onClick={() => onOpenChange(false)}
        >
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex-1 flex flex-col min-h-0">
        <div className="px-6 py-4 bg-white dark:bg-zinc-950 flex items-center gap-3 border-b border-zinc-100 dark:border-zinc-900">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-zinc-400" />
            <Input
              placeholder="Search table..."
              className="pl-9 h-9 rounded text-xs bg-zinc-50 dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-9 rounded px-3 text-xs gap-2"
            >
              <Download className="size-3.5" />
              Export
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-auto">
          <div className="min-w-full inline-block align-middle">
            <div className="overflow-hidden">
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
                  <div className="p-3 rounded bg-red-100 dark:bg-red-900/20 mb-4">
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
                <TooltipProvider>
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50">
                        <th className="px-6 py-3 text-xs font-semibold text-zinc-500 dark:text-zinc-400 w-1/3">
                          <div className="flex items-center gap-2">
                            Item
                          </div>
                        </th>
                        <th className="px-6 py-3 text-xs font-semibold text-zinc-500 dark:text-zinc-400">
                          <div className="flex items-center gap-2">
                            Content
                          </div>
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
                      {filteredData.map((row, i) => {
                        const citFound = hasCitation(row.type, row.id);
                        return (
                          <Tooltip key={`${row.id}-${i}`}>
                            <TooltipTrigger asChild>
                              <tr
                                className={cn(
                                  "group cursor-pointer hover:bg-zinc-50/50 dark:hover:bg-zinc-900/50 relative",
                                  citFound && "bg-orange-50/10",
                                )}
                                onClick={() =>
                                  handleItemClick(row.type, row.id)
                                }
                              >
                                <td className="px-6 py-4 align-top text-xs font-medium text-zinc-900 dark:text-zinc-100">
                                  {row.item}
                                </td>
                                <td className="px-6 py-4 align-top text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed relative pr-8">
                                  {row.content}
                                  {citFound && (
                                    <div className="absolute top-0 right-0">
                                      <div className="w-0 h-0 border-t-[10px] border-l-[10px] border-t-orange-500 border-l-transparent" />
                                    </div>
                                  )}
                                </td>
                              </tr>
                            </TooltipTrigger>
                            {citFound && (
                              <TooltipContent side="left">
                                Click to view citation in PDF
                              </TooltipContent>
                            )}
                          </Tooltip>
                        );
                      })}
                    </tbody>
                  </table>
                </TooltipProvider>
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
                    The document extraction did not produce any sections or
                    entities.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
