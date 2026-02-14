"use client";

import * as React from "react";
import { FileText, Blocks, Sparkle } from "lucide-react";
import { IconChartBar, IconFileWord } from "@tabler/icons-react";
import { GitCompare } from "lucide-react";

import { NavUser } from "@/components/layout/nav-user";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";

import { useWorkflowDefinitions } from "@/hooks/use-workflow-definitions";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveWorkflow } from "@/contexts/active-workflow-context";

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname();
  const { data: workflowDefinitions, isLoading } = useWorkflowDefinitions();

  const workflowDefId = pathname.split("/")[2];

  const { activeWorkflowDefinitionId } = useActiveWorkflow();

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader className="bg-[#EDEDEE]">
        <div className="flex items-start justify-between">
          <SidebarMenuButton
            size="lg"
            className="hover:bg-transparent rounded data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
          >
            <div className="bg-[#0232D4]/90 rounded text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center">
              <Sparkle className="size-4" />
            </div>
            <div className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-medium">InsuraAI</span>
              <span className="truncate text-xs text-gray-600">
                AI-insurance workspace
              </span>
            </div>
          </SidebarMenuButton>
          <SidebarTrigger className="group-data-[collapsible=icon]:hidden h-8 w-8 hover:bg-[#DBDCDE] hover:rounded text-[#2B2C36]" />
        </div>
      </SidebarHeader>
      <SidebarContent className="bg-[#EDEDEE]">
        <SidebarGroup>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                asChild
                tooltip="Dashboard"
                className={`text-[13px] text-[#2B2C36] hover:rounded hover:bg-[#DBDCDE] hover:text-[#2B2C36] ${pathname === "/dashboard" ? "bg-[#DBDCDE] text-[#2B2C36] rounded" : ""}`}
              >
                <Link href="/dashboard">
                  <IconChartBar size={20} />
                  <span>Dashboard</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Workflows</SidebarGroupLabel>
          <SidebarMenu>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <SidebarMenuItem key={i}>
                    <SidebarMenuButton disabled className="animate-pulse">
                      <Skeleton className="size-6 rounded shrink-0 bg-[#DBDCDE]" />
                      <Skeleton className="h-6 w-full rounded bg-[#DBDCDE]" />
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))
              : workflowDefinitions?.map((item, index) => {
                  const Icon = item.name?.toLowerCase().includes("policy")
                    ? GitCompare
                    : item.name?.toLowerCase().includes("proposal")
                      ? IconFileWord
                      : item.name?.toLowerCase().includes("quote")
                        ? FileText
                        : Blocks;

                  return (
                    <SidebarMenuItem key={index}>
                      <SidebarMenuButton
                        className={`text-[13px] text-[#2B2C36] hover:rounded hover:bg-[#DBDCDE] hover:text-[#2B2C36] ${item.id === workflowDefId || item.id === activeWorkflowDefinitionId ? "bg-[#DBDCDE] text-[#2B2C36] rounded" : ""}`}
                        asChild
                        tooltip={item.name}
                      >
                        <Link href={`/workflows/${item.id}`}>
                          <Icon size={20} />
                          <span>{item.name}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="bg-[#EDEDEE]">
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
