"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "../ui/textarea";
import { cn } from "@/lib/utils";
import { DocumentMentionDropdown } from "./document-mention-dropdown";
import type { MentionedDocument } from "@/schema/generated/query";
import type { DocumentResponse } from "@/hooks/use-documents";

interface ChatInterfaceProps {
  onAsk: (query: string, mentionedDocuments: MentionedDocument[]) => void;
  showBlurOverlay?: boolean;
  isLoading?: boolean;
  documents: DocumentResponse[];
}

export function ChatInterface({
  onAsk,
  showBlurOverlay,
  isLoading,
  documents,
}: ChatInterfaceProps) {
  const [query, setQuery] = useState("");
  const [mentionedDocs, setMentionedDocs] = useState<MentionedDocument[]>([]);
  const [showMentionDropdown, setShowMentionDropdown] = useState(false);
  const [mentionFilter, setMentionFilter] = useState("");
  const [cursorPosition, setCursorPosition] = useState(0);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);

  const handleScroll = () => {
    if (textareaRef.current && mirrorRef.current) {
      mirrorRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  };

  const handleAsk = () => {
    if (query.trim()) {
      const finalMentions = mentionedDocs.filter((doc) =>
        query.includes(`@${doc.name}`),
      );
      onAsk(query, finalMentions);
      setQuery("");
      setMentionedDocs([]);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey && !showMentionDropdown) {
      e.preventDefault();
      handleAsk();
    }
    if (e.key === "Escape" && showMentionDropdown) {
      setShowMentionDropdown(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    const pos = e.target.selectionStart;
    setQuery(value);
    setCursorPosition(pos);

    const textBeforeCursor = value.slice(0, pos);
    const lastAtSymbolIndex = textBeforeCursor.lastIndexOf("@");

    if (lastAtSymbolIndex !== -1) {
      const textSinceAt = textBeforeCursor.slice(lastAtSymbolIndex + 1);
      const isStartOrAfterSpace =
        lastAtSymbolIndex === 0 ||
        value[lastAtSymbolIndex - 1] === " " ||
        value[lastAtSymbolIndex - 1] === "\n";

      if (isStartOrAfterSpace && !textSinceAt.includes(" ")) {
        setShowMentionDropdown(true);
        setMentionFilter(textSinceAt);
      } else {
        setShowMentionDropdown(false);
      }
    } else {
      setShowMentionDropdown(false);
    }
  };

  const handleSelectDocument = (doc: MentionedDocument) => {
    const textBeforeAt = query.slice(0, cursorPosition).lastIndexOf("@");
    const newQuery =
      query.slice(0, textBeforeAt) +
      `@${doc.name} ` +
      query.slice(cursorPosition);

    setQuery(newQuery);
    if (!mentionedDocs.find((d) => d.id === doc.id)) {
      setMentionedDocs([...mentionedDocs, doc]);
    }
    setShowMentionDropdown(false);

    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
        const newPos = textBeforeAt + doc.name.length + 2;
        textareaRef.current.setSelectionRange(newPos, newPos);
      }
    }, 0);
  };

  const renderMirroredText = () => {
    if (!query) return null;

    const sortedMentions = [...mentionedDocs].sort(
      (a, b) => b.name.length - a.name.length,
    );

    let parts: (string | React.ReactNode)[] = [query];

    sortedMentions.forEach((doc) => {
      const mentionText = `@${doc.name}`;
      const newParts: (string | React.ReactNode)[] = [];

      parts.forEach((part) => {
        if (typeof part !== "string") {
          newParts.push(part);
          return;
        }

        const subParts = part.split(mentionText);
        subParts.forEach((subPart, i) => {
          newParts.push(subPart);
          if (i < subParts.length - 1) {
            newParts.push(
              <span
                key={`${doc.id}-${i}`}
                className="bg-blue-100 dark:bg-blue-900/30 p-0.5 text-blue-700 dark:text-blue-300 px-1 rounded border border-blue-200 dark:border-blue-800 font-medium"
              >
                {mentionText}
              </span>,
            );
          }
        });
      });
      parts = newParts;
    });

    return parts;
  };

  return (
    <div className="w-full max-w-2xl mx-auto px-4">
      <div className="relative">
        {showMentionDropdown && (
          <DocumentMentionDropdown
            documents={documents}
            filter={mentionFilter}
            onSelect={handleSelectDocument}
            onClose={() => setShowMentionDropdown(false)}
          />
        )}

        <div className="relative border dark:bg-zinc-800 rounded overflow-hidden flex flex-col items-end min-h-[100px]">
          {/* Overlay for Mentions */}
          <div
            ref={mirrorRef}
            aria-hidden="true"
            className="absolute inset-0 pointer-events-none whitespace-pre-wrap break-words p-3 text-sm leading-relaxed text-transparent"
            style={{
              fontFamily: "inherit",
              paddingRight: "60px",
            }}
          >
            {renderMirroredText()}
          </div>

          <Textarea
            ref={textareaRef}
            value={query}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onScroll={handleScroll}
            placeholder="Ask anything about your documents. Type @ to mention a specific file."
            className="min-h-[100px] w-full bg-transparent border-none focus-visible:ring-0 focus-visible:ring-offset-0 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-500 resize-none p-3 text-sm leading-relaxed"
          />

          <div className="absolute bottom-2 right-2 flex items-center justify-end z-10">
            <Button
              onClick={handleAsk}
              disabled={isLoading || !query.trim()}
              variant="ghost"
              size="icon"
              className="h-9 w-9 bg-[#0232D4]/90 !text-white hover:bg-[#0232D4]/80 rounded flex items-center justify-center transition-all shrink-0"
            >
              <ArrowRight className="size-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
