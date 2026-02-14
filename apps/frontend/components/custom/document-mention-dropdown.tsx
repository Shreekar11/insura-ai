"use client";

import * as React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { FileText } from "lucide-react";
import type { MentionedDocument } from "@/schema/generated/query";
import type { DocumentResponse } from "@/hooks/use-documents";

interface DocumentMentionDropdownProps {
  documents: DocumentResponse[];
  onSelect: (doc: MentionedDocument) => void;
  onClose: () => void;
  filter: string;
}

export function DocumentMentionDropdown({
  documents,
  onSelect,
  onClose,
  filter,
}: DocumentMentionDropdownProps) {
  const [selectedIndex, setSelectedIndex] = React.useState(0);

  const filteredDocs = React.useMemo(() => {
    return documents.filter((doc) =>
      (doc.document_name || "Untitled Document")
        .toLowerCase()
        .includes(filter.toLowerCase()),
    );
  }, [documents, filter]);

  React.useEffect(() => {
    setSelectedIndex(0);
  }, [filteredDocs]);

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (filteredDocs.length === 0) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1) % filteredDocs.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex(
          (prev) => (prev - 1 + filteredDocs.length) % filteredDocs.length,
        );
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filteredDocs[selectedIndex]) {
          onSelect({
            id: filteredDocs[selectedIndex].id,
            name:
              filteredDocs[selectedIndex].document_name || "Untitled Document",
          });
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };

    const dropdown = document.getElementById("mention-dropdown");
    if (dropdown) {
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [filteredDocs, selectedIndex, onSelect, onClose]);

  if (filteredDocs.length === 0) return null;

  return (
    <div
      id="mention-dropdown"
      className="absolute bottom-full left-0 mb-2 w-64 rounded-md border bg-popover p-1 shadow-md z-50 animate-in fade-in slide-in-from-bottom-2"
    >
      <ScrollArea>
        <div className="flex flex-col gap-1 p-1">
          {filteredDocs.map((doc, index) => (
            <Button
              key={doc.id}
              variant={selectedIndex === index ? "secondary" : "ghost"}
              className="rounded justify-start w-full px-2 py-1.5 h-auto text-sm font-normal"
              onClick={() =>
                onSelect({
                  id: doc.id,
                  name: doc.document_name || "Untitled Document",
                })
              }
            >
              <FileText className="mr-2 h-4 w-4 shrink-0 opacity-50" />
              <span className="truncate">
                {doc.document_name || "Untitled Document"}
              </span>
            </Button>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
