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
      <SidebarHeader className="bg-[#F3F2F0]">
        <SidebarMenuButton
          size="lg"
          className="border rounded data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
        >
          <div className="bg-sidebar-primary text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded">
            <GalleryVerticalEnd className="size-4" />
          </div>
          <div className="grid flex-1 text-left text-sm leading-tight">
            <span className="truncate font-medium">InsuraAI</span>
            <span className="truncate text-xs text-gray-500">AI-insurance workspace</span>
          </div>
        </SidebarMenuButton>
      </SidebarHeader>
      <SidebarContent className="bg-[#F3F2F0]">
        <SidebarGroup>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                asChild
                tooltip="Dashboard"
                className={`text-gray-600 hover:rounded hover:bg-white hover:text-gray-900 ${pathname === "/dashboard" ? "bg-white text-gray-900 rounded" : ""}`}
              >
                <a href="/dashboard">
                  <IconChartBar />
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
                    className={`text-gray-600 hover:rounded hover:bg-white hover:text-gray-900 ${item.id === workflowDefId || item.id === activeWorkflowDefinitionId ? "bg-white text-gray-900 rounded" : ""}`}
                    asChild
                    tooltip={item.name}
                  >
                    <a href={`/workflows/${item.id}`}>
                      <Icon />
                      <span>{item.name}</span>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="bg-[#F3F2F0]">
        <NavUser user={data.user} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
