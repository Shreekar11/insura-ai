"use client";

import * as React from "react";
import { GalleryVerticalEnd, FileText, Blocks } from "lucide-react";
import { IconChartBar, IconReport, IconFileWord } from "@tabler/icons-react";

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

// This is sample data.
const data = {
  user: {
    name: "shadcn",
    email: "m@example.com",
    avatar: "/avatars/shadcn.jpg",
  },
};

import { useActiveWorkflow } from "@/contexts/active-workflow-context";

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname();
  const {
    data: workflowDefinitions,
    isLoading,
    error,
  } = useWorkflowDefinitions();
  const { activeWorkflowDefinitionId } = useActiveWorkflow();

  const workflowDefId = pathname.split("/")[2];

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader className="bg-[#EDEDEE] group-data-[collapsible=icon]:hidden">
        <div className="flex items-start justify-between">
          <SidebarMenuButton
            size="lg"
            className="hover:bg-transparent data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
          >
            <div className="bg-blue-700/90 text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded">
              <GalleryVerticalEnd className="size-4" />
            </div>
            <div className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-medium">InsuraAI</span>
              <span className="truncate text-xs text-gray-600">AI-insurance workspace</span>
            </div>
          </SidebarMenuButton>
          <SidebarTrigger className="h-8 w-8 hover:bg-[#DBDCDE] hover:rounded text-[#2B2C36]" />
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
                <a href="/dashboard">
                  <IconChartBar size={20}/>
                  <span>Dashboard</span>
                </a>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Workflows</SidebarGroupLabel>
          <SidebarMenu>
            {workflowDefinitions?.map((item, index) => {
              const Icon = item.name?.toLowerCase().includes("policy")
                ? IconReport
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
                    <a href={`/workflows/${item.id}`}>
                      <Icon size={20}/>
                      <span>{item.name}</span>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="bg-[#EDEDEE]">
        <NavUser user={data.user} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
