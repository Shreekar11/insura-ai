"use client";

import { Button } from "@/components/ui/button";
import { X } from "lucide-react";

interface PDFToolbarProps {
  onClose: () => void;
}

export function PDFToolbar({ onClose }: PDFToolbarProps) {
  return (
    <div className="flex items-center justify-end px-4 h-14 border-b border-zinc-200">
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
