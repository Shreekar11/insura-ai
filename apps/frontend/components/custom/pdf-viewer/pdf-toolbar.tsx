"use client";

import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import { useSidebar } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

interface PDFToolbarProps {
  onClose: () => void;
}

export function PDFToolbar({ onClose }: PDFToolbarProps) {
  const { state } = useSidebar();
  const isExpanded = state === "expanded";

  return (
    <div
      className={cn(
        "flex items-center justify-end px-4 border-b border-zinc-200 transition-[height] ease-linear",
        isExpanded ? "h-14" : "h-12",
      )}
    >
      <div className="flex items-end gap-2">
        <div className="ml-2 pl-2">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            onClick={onClose}
          >
            <X className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
