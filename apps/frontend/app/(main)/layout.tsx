"use client";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { PageHeader } from "@/components/layout/page-header";
import {
  SidebarInset,
  SidebarProvider,
} from "@/components/ui/sidebar";
import { ActiveWorkflowProvider } from "@/contexts/active-workflow-context";
import { usePathname } from "next/navigation";

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
  const pathname = usePathname();
  const isWorkflowExecution = pathname?.startsWith("/workflow-execution/");

  return (
    <>
      <AppSidebar />
      <SidebarInset>
        {!isWorkflowExecution && <PageHeader />}
        {children}
      </SidebarInset>
    </>
  );
}