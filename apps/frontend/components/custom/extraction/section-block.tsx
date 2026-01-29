import React from "react";
import { ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";
import { Section } from "@/types/extraction";
import { normalizeFieldLabel, getSectionIcon } from "@/utils/extraction-utils";
import { 
  CoverageTable, 
  ExclusionTable, 
  ConditionTable, 
  EndorsementTable 
} from "./tables";
import { SectionItemCard } from "./common";

/**
 * Renders a section with its items.
 */
export function SectionBlock({ section }: { section: Section }) {
  const [isOpen, setIsOpen] = React.useState(true);
  const sectionName = normalizeFieldLabel(section.section_type);
  const items = Object.values(section.fields)[0];
  const itemList = Array.isArray(items) ? items : [];
  const confidence = section.confidence?.overall;
  
  if (itemList.length === 0) return null;
  
  const renderTable = () => {
    const type = section.section_type.toLowerCase();
    switch (type) {
      case "coverages":
        return <CoverageTable items={itemList} />;
      case "exclusions":
        return <ExclusionTable items={itemList} />;
      case "conditions":
        return <ConditionTable items={itemList} />;
      case "endorsements":
        return <EndorsementTable items={itemList} />;
      default:
        // Fallback to the original list view if type is unknown
        return (
          <div className="space-y-2">
            {itemList.map((item, idx) => (
              <SectionItemCard key={idx} item={item} index={idx} />
            ))}
          </div>
        );
    }
  };
  
  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="mb-8 last:mb-0">
        <CollapsibleTrigger className="w-full flex items-center justify-between gap-3 py-2 group">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400">
              {getSectionIcon(section.section_type)}
            </div>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {sectionName}
            </h3>
            <Badge variant="secondary" className="text-[10px] font-medium h-5 bg-zinc-100/50 text-zinc-600 border-zinc-200">
              {itemList.length} {itemList.length === 1 ? 'item' : 'items'}
            </Badge>
          </div>
          <div className="flex items-center gap-3">
            {confidence !== undefined && (
              <div className="flex items-center gap-1.5">
                <div className="h-1 w-12 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
                  <div 
                    className={cn(
                      "h-full rounded-full transition-all",
                      confidence > 0.9 ? "bg-emerald-500" : confidence > 0.7 ? "bg-amber-500" : "bg-red-500"
                    )}
                    style={{ width: `${confidence * 100}%` }}
                  />
                </div>
                <span className="text-[10px] font-medium text-zinc-400 dark:text-zinc-500">
                  {Math.round(confidence * 100)}%
                </span>
              </div>
            )}
            <div className="text-zinc-400 dark:text-zinc-500 transition-transform duration-200 group-data-[state=open]:rotate-180">
              <ChevronDown className="size-4" />
            </div>
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-3">
            {renderTable()}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
