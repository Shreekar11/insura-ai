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

// This is sample data.
const data = {
  user: {
    name: "shadcn",
    email: "m@example.com",
    avatar: "/avatars/shadcn.jpg",
  },
};

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const {
    data: workflowDefinitions,
    isLoading,
    error,
  } = useWorkflowDefinitions();

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenuButton
          size="lg"
          className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground bg-gray-200"
        >
          <div className="bg-sidebar-primary text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg">
            <GalleryVerticalEnd className="size-4" />
          </div>
          <div className="grid flex-1 text-left text-sm leading-tight">
            <span className="truncate font-medium">InsuraAI</span>
            <span className="truncate text-xs">AI-insurance workspace</span>
          </div>
        </SidebarMenuButton>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
            <SidebarMenu>
                <SidebarMenuItem>
                    <SidebarMenuButton asChild tooltip="Dashboard">
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
                    <SidebarMenuButton asChild tooltip={item.name}>
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
      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
