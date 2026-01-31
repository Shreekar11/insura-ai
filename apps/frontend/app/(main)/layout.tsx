"use client";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { DynamicBreadcrumb } from "@/components/layout/dynamic-breadcrumb";
import {
  SidebarInset,
  SidebarTrigger,
  SidebarProvider,
  useSidebar,
} from "@/components/ui/sidebar";
import { ActiveWorkflowProvider } from "@/contexts/active-workflow-context";

export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ActiveWorkflowProvider>
      <SidebarProvider>
        <LayoutContent>{children}</LayoutContent>
      </SidebarProvider>
    </ActiveWorkflowProvider>
  );
}

function LayoutContent({ children }: { children: React.ReactNode }) {
  const { state } = useSidebar();
  const isExpanded = state === "expanded";

  return (
    <>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-4 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
          <div className="flex items-center gap-2">
            {!isExpanded && <SidebarTrigger className="-ml-1 hover:rounded" />}
            <DynamicBreadcrumb />
          </div>
        </header>
        {children}
      </SidebarInset>
    </>
  );
}