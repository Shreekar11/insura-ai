"use client";

import { usePathname } from "next/navigation";
import {
  Breadcrumb,
  BreadcrumbEllipsis,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkflowDefinitionById } from "@/hooks/use-workflow-definitions";
import { useWorkflowById } from "@/hooks/use-workflows";
import { Fragment } from "react";
import { IconChevronRight } from "@tabler/icons-react";

interface BreadcrumbItemData {
  label: string;
  href: string;
  isCurrentPage: boolean;
  isLoading?: boolean;
  icon?: React.ReactNode;
}

/**
 * Route configuration for breadcrumb generation
 * Add new routes here as your app grows
 */
const ROUTE_CONFIG: Record<string, (segments: string[]) => string> = {
  dashboard: () => "Dashboard",
};

/**
 * Dynamic breadcrumb component with intelligent route parsing
 * Features:
 * - Auto-detects current route
 * - Fetches workflow names dynamically
 * - Shows loading states
 * - Supports nested routes
 * - Mobile-responsive with ellipsis
 */
export function DynamicBreadcrumb() {
  const pathname = usePathname();
  const pathSegments = pathname.split("/").filter(Boolean);

  // Detect workflow page and fetch workflow data
  const isWorkflowPage = pathSegments[0] === "workflows" && pathSegments[1];
  const isExecutionPage = pathSegments[0] === "workflow-execution" && pathSegments[1];
  const workflowId = isWorkflowPage || isExecutionPage ? pathSegments[1] : null;

  const { 
    data: workflowDefinition, 
    isLoading: isLoadingDefinition,
    isError: isDefinitionError,
  } = useWorkflowDefinitionById(isWorkflowPage ? (workflowId || "") : "");

  const {
    data: workflowInstance,
    isLoading: isLoadingInstance,
    isError: isInstanceError,
  } = useWorkflowById(isExecutionPage ? (workflowId || "") : "");

  const isLoadingWorkflow = isLoadingDefinition || isLoadingInstance;
  const isWorkflowError = isDefinitionError || isInstanceError;

  // Build breadcrumb items dynamically
  const buildBreadcrumbItems = (): BreadcrumbItemData[] => {
    const items: BreadcrumbItemData[] = [];

    // Handle dashboard page - show only "Dashboard"
    if (pathSegments[0] === "dashboard" && pathSegments.length === 1) {
      items.push({
        label: "Dashboard",
        href: "/dashboard",
        isCurrentPage: true,
      });
      return items;
    }

    // Handle workflow detail page - show only workflow name
    if (pathSegments[0] === "workflows" && pathSegments[1] && pathSegments.length === 2) {
      items.push({
        label: isLoadingDefinition 
          ? "Loading..." 
          : isDefinitionError 
            ? "Unknown Workflow"
            : workflowDefinition?.name || "Workflow",
        href: pathname,
        isCurrentPage: true,
        isLoading: isLoadingDefinition,
      });
      return items;
    }

    // Handle workflow execution page - show definition_name > workflow_name
    if (pathSegments[0] === "workflow-execution" && pathSegments[1] && pathSegments.length === 2) {
      // First segment: Definition
      items.push({
        label: isLoadingInstance 
          ? "Loading..." 
          : isInstanceError 
            ? "Unknown Process"
            : workflowInstance?.definition_name || "Definition",
        href: workflowInstance?.definition_id 
          ? `/workflows/${workflowInstance.definition_id}`
          : "#",
        isCurrentPage: false,
        isLoading: isLoadingInstance,
      });
      
      // Second segment: Execution
      items.push({
        label: isLoadingInstance 
          ? "Loading..." 
          : isInstanceError 
            ? "Unknown Execution"
            : workflowInstance?.workflow_name || "Execution",
        href: pathname,
        isCurrentPage: true,
        isLoading: isLoadingInstance,
      });
      return items;
    }

    // For all other pages, start with Dashboard as home
    if (pathSegments[0] !== "dashboard" && pathSegments[0] !== "workflow-execution") {
      items.push({
        label: "Dashboard",
        href: "/dashboard",
        isCurrentPage: false,
      });
    }

    // Process each path segment
    pathSegments.forEach((segment, index) => {
      const isLast = index === pathSegments.length - 1;
      const href = "/" + pathSegments.slice(0, index + 1).join("/");

      // Skip "dashboard" segment if it's the first one (already added above)
      if (segment === "dashboard" && index === 0) {
        return;
      }

      // Handle workflow pages specially
      if (segment === "workflows" && pathSegments[index + 1]) {
        items.push({
          label: "Workflows",
          href: "/workflows",
          isCurrentPage: false,
        });
        return; // Skip to next iteration
      }

      // Handle workflow ID (dynamic name from API)
      if (pathSegments[index - 1] === "workflows" && workflowId === segment) {
        items.push({
          label: isLoadingDefinition 
            ? "Loading..." 
            : isDefinitionError 
              ? "Unknown Workflow"
              : workflowDefinition?.name || "Workflow",
          href,
          isCurrentPage: isLast,
          isLoading: isLoadingDefinition,
        });
        return;
      }

      // Handle standard routes from config
      const labelFn = ROUTE_CONFIG[segment];
      if (labelFn) {
        items.push({
          label: labelFn(pathSegments),
          href,
          isCurrentPage: isLast,
        });
        return;
      }

      // Fallback: capitalize segment
      if (segment !== workflowId) {
        items.push({
          label: segment.charAt(0).toUpperCase() + segment.slice(1).replace(/-/g, " "),
          href,
          isCurrentPage: isLast,
        });
      }
    });

    return items;
  };

  const breadcrumbItems = buildBreadcrumbItems();

  // Show ellipsis for long breadcrumb trails (mobile optimization)
  const shouldShowEllipsis = breadcrumbItems.length > 3;
  const itemsToShow = shouldShowEllipsis
    ? [breadcrumbItems[0], ...breadcrumbItems.slice(-2)]
    : breadcrumbItems;
  const hiddenItems = shouldShowEllipsis
    ? breadcrumbItems.slice(1, -2)
    : [];

  return (
    <Breadcrumb>
      <BreadcrumbList>
        {shouldShowEllipsis ? (
          <>
            {/* First item */}
            <BreadcrumbItem>
              {(itemsToShow[0] as any).isCurrentPage ? (
                <BreadcrumbPage className="flex items-center gap-2">
                  {(itemsToShow[0] as any).icon}
                  {(itemsToShow[0] as any).label}
                </BreadcrumbPage>
              ) : (
                <BreadcrumbLink 
                  href={(itemsToShow[0] as any).href}
                  className="flex items-center gap-2"
                >
                  {(itemsToShow[0] as any).icon}
                  {(itemsToShow[0] as any).label}
                </BreadcrumbLink>
              )}
            </BreadcrumbItem>
            <BreadcrumbSeparator>
              <IconChevronRight className="size-4" />
            </BreadcrumbSeparator>

            {/* Ellipsis dropdown for hidden items */}
            <BreadcrumbItem>
              <DropdownMenu>
                <DropdownMenuTrigger className="flex items-center gap-1">
                  <BreadcrumbEllipsis className="size-4" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  {hiddenItems.map((item) => (
                    <DropdownMenuItem key={item.href}>
                      <a href={item.href} className="flex items-center gap-2">
                        {item.icon}
                        {item.label}
                      </a>
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </BreadcrumbItem>
            <BreadcrumbSeparator>
              <IconChevronRight className="size-4" />
            </BreadcrumbSeparator>

            {/* Last two items */}
            {itemsToShow.slice(1).map((item, index) => (
              <Fragment key={(item as any).href}>
                <BreadcrumbItem className="hidden md:block">
                  {(item as any).isCurrentPage ? (
                    <BreadcrumbPage>
                      {(item as any).isLoading ? (
                        <Skeleton className="h-4 w-32 animate-pulse" />
                      ) : (
                        <span className="flex items-center gap-2">
                          {(item as any).icon}
                          {(item as any).label}
                        </span>
                      )}
                    </BreadcrumbPage>
                  ) : (
                    <BreadcrumbLink 
                      href={(item as any).href}
                      className="flex items-center gap-2"
                    >
                      {(item as any).icon}
                      {(item as any).label}
                    </BreadcrumbLink>
                  )}
                </BreadcrumbItem>
                {index < itemsToShow.slice(1).length - 1 && (
                  <BreadcrumbSeparator className="hidden md:block">
                    <IconChevronRight className="size-4" />
                  </BreadcrumbSeparator>
                )}
              </Fragment>
            ))}
          </>
        ) : (
          // Regular breadcrumb for short paths
          breadcrumbItems.map((item, index) => (
            <Fragment key={item.href}>
              <BreadcrumbItem className="hidden md:block">
                {item.isCurrentPage ? (
                  <BreadcrumbPage>
                    {item.isLoading ? (
                      <Skeleton className="h-4 w-32 animate-pulse" />
                    ) : (
                      <span className="flex items-center gap-2">
                        {item.icon}
                        {item.label}
                      </span>
                    )}
                  </BreadcrumbPage>
                ) : (
                  <BreadcrumbLink 
                    href={item.href}
                    className="flex items-center gap-2"
                  >
                    {item.icon}
                    {item.label}
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
              {index < breadcrumbItems.length - 1 && (
                <BreadcrumbSeparator className="hidden md:block">
                  <IconChevronRight className="size-4" />
                </BreadcrumbSeparator>
              )}
            </Fragment>
          ))
        )}
      </BreadcrumbList>
    </Breadcrumb>
  );
}