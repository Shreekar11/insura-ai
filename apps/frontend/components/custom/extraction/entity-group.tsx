import React from "react";
import { ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { Entity } from "@/types/extraction";
import { normalizeFieldLabel, getSectionIcon } from "@/utils/extraction-utils";
import {
  CoverageTable,
  ExclusionTable,
  ConditionTable,
  EndorsementTable,
  EntityTable,
} from "./tables";

/**
 * Renders a group of entities of the same type.
 */
export function EntityGroup({
  type,
  entities,
  onItemClick,
}: {
  type: string;
  entities: Entity[];
  onItemClick?: (sourceType: string, sourceId: string) => void;
}) {
  const [isOpen, setIsOpen] = React.useState(true);
  const typeName = normalizeFieldLabel(type);

  const renderTable = () => {
    const lowerType = type.toLowerCase();
    switch (lowerType) {
      case "coverage":
      case "coverages":
        return (
          <CoverageTable
            items={entities}
            isEntity={true}
            onItemClick={onItemClick}
          />
        );
      case "exclusion":
      case "exclusions":
        return (
          <ExclusionTable
            items={entities}
            isEntity={true}
            onItemClick={onItemClick}
          />
        );
      case "condition":
      case "conditions":
        return (
          <ConditionTable
            items={entities}
            isEntity={true}
            onItemClick={onItemClick}
          />
        );
      case "endorsement":
      case "endorsements":
        return (
          <EndorsementTable
            items={entities}
            isEntity={true}
            onItemClick={onItemClick}
          />
        );
      default:
        return (
          <div className="space-y-3">
            {entities.map((entity, idx) => (
              <EntityTable
                key={(entity.fields.id as string) || `entity-${idx}`}
                entity={entity}
                index={idx}
                onItemClick={onItemClick}
              />
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
              {getSectionIcon(type)}
            </div>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {typeName}
            </h3>
            <Badge
              variant="secondary"
              className="text-[10px] font-medium h-5 bg-zinc-100/50 text-zinc-600 border-zinc-200"
            >
              {entities.length} {entities.length === 1 ? "item" : "items"}
            </Badge>
          </div>
          <div className="text-zinc-400 dark:text-zinc-500 transition-transform duration-200 group-data-[state=open]:rotate-180">
            <ChevronDown className="size-4" />
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-3">{renderTable()}</div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
