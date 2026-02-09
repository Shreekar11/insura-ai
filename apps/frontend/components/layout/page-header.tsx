"use client";

import { DynamicBreadcrumb } from "@/components/layout/dynamic-breadcrumb";
import { SidebarTrigger, useSidebar } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  className?: string;
  showTrigger?: boolean;
}

export function PageHeader({ className, showTrigger = true }: PageHeaderProps) {
  const { state } = useSidebar();
  const isExpanded = state === "expanded";

  return (
    <header className={cn(
      "sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-4 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12",
      className
    )}>
      <div className="flex items-center gap-2">
        {showTrigger && !isExpanded && (
          <SidebarTrigger className="-ml-1 hover:rounded" />
        )}
        <DynamicBreadcrumb />
      </div>
    </header>
  );
}
