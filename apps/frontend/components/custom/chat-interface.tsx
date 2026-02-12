"use client";

import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "../ui/textarea";
import { cn } from "@/lib/utils";

interface ChatInterfaceProps {
  onAsk: (query: string) => void;
  showBlurOverlay?: boolean;
  isLoading?: boolean;
}

export function ChatInterface({
  onAsk,
  showBlurOverlay,
  isLoading,
}: ChatInterfaceProps) {
  const [query, setQuery] = useState("");

  const handleAsk = () => {
    if (query.trim()) {
      onAsk(query);
      setQuery("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto">
      {/* Top Blur Overlay */}
      <div
        className={cn(
          "absolute -top-12 left-0 right-0 h-12 z-20 pointer-events-none transition-opacity duration-300 bg-gradient-to-b from-white/50 via-white/20 to-transparent dark:from-zinc-950/50 dark:via-zinc-950/20 dark:to-transparent backdrop-blur-md [mask-image:linear-gradient(to_bottom,black,transparent)]",
          showBlurOverlay ? "opacity-100" : "opacity-0",
        )}
      />
      <div className="relative border dark:bg-zinc-800 rounded-sm overflow-hidden flex flex-col md:flex-row items-end gap-2">
        <Textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything."
          className="flex-1 w-full bg-transparent border-none focus-visible:ring-0 focus-visible:ring-offset-0 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-500 resize-none"
        />

        <div className="absolute bottom-2 right-2 flex items-center justify-end">
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
  );
}
