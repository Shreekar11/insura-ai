"use client";

import { ColumnDef } from "@tanstack/react-table";
import { WorkflowListItem } from "@/schema/generated/workflows";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  IconCircleCheckFilled,
  IconLoader2,
  IconCircleXFilled,
  IconDotsVertical,
  IconClock,
  IconFileText,
} from "@tabler/icons-react";
import { format } from "date-fns";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";

export const workflowColumns: ColumnDef<WorkflowListItem>[] = [
  {
    accessorKey: "workflow_name",
    header: "Workflow",
    cell: ({ row }) => {
      const name = row.getValue("workflow_name") as string;
      return (
        <div className="flex flex-col gap-0.5 w-[150px]">
          <span className="font-medium text-foreground">{name}</span>
        </div>
      );
    },
  },
  {
    accessorKey: "definition_name",
    header: "Workflow Type",
    cell: ({ row }) => {
      const name = row.getValue("definition_name") as string;
      return (
        <div className="flex flex-col gap-0.5">
          <span className="font-medium text-foreground">{name}</span>
        </div>
      );
    },
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.getValue("status") as string;

      const statusConfig: Record<
        string,
        { label: string; icon: any; color: string }
      > = {
        running: {
          label: "Running",
          icon: <IconLoader2 className="size-3.5 animate-spin" />,
          color: "text-blue-500 bg-blue-500/10 border-blue-500/20",
        },
        completed: {
          label: "Completed",
          icon: <IconCircleCheckFilled className="size-3.5" />,
          color: "text-emerald-500 bg-emerald-500/10 border-emerald-500/20",
        },
        failed: {
          label: "Failed",
          icon: <IconCircleXFilled className="size-3.5" />,
          color: "text-red-500 bg-red-500/10 border-red-500/20",
        },
        pending: {
          label: "Pending",
          icon: <IconClock className="size-3.5" />,
          color: "text-amber-500 bg-amber-500/10 border-amber-500/20",
        },
        draft: {
          label: "Draft",
          icon: <IconFileText className="size-3.5" />,
          color: "text-gray-500 bg-gray-500/10 border-gray-500/20",
        }
      };

      const config = statusConfig[status.toLowerCase()] || {
        label: status,
        icon: null,
        color: "text-gray-500 bg-gray-500/10 border-gray-500/20",
      };

      return (
        <Badge
          variant="outline"
          className={`${config.color} rounded gap-1.5 px-2 py-0.5 font-medium`}
        >
          {config.icon}
          {config.label}
        </Badge>
      );
    },
  },
  {
    accessorKey: "created_at",
    header: "Started",
    cell: ({ row }) => {
      const dateString = row.getValue("created_at") as string;
      if (!dateString) return <span className="text-muted-foreground">-</span>;
      return (
        <div className="text-sm text-muted-foreground">
          {format(new Date(dateString), "MMM d, h:mm a")}
        </div>
      );
    },
  },
  {
    accessorKey: "duration_seconds",
    header: "Duration",
    cell: ({ row }) => {
      const seconds = row.original.duration_seconds;

      if (seconds == null || seconds < 0) {
        return <span className="text-muted-foreground">-</span>;
      }

      const formatDuration = (totalSeconds: number) => {
        const s = Math.round(totalSeconds);

        if (s < 60) {
          return `${s}s`;
        }

        const mins = Math.floor(s / 60);
        const secs = s % 60;

        if (mins < 60) {
          return `${mins}m ${secs}s`;
        }

        const hours = Math.floor(mins / 60);
        const remMins = mins % 60;

        return `${hours}h ${remMins}m ${secs}s`;
      };

      return (
        <div className="text-sm font-medium text-muted-foreground">
          {formatDuration(seconds)}
        </div>
      );
    },
  },
  {
    id: "actions",
    cell: ({ row }) => {
      return (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="size-8 p-0">
              <span className="sr-only">Open menu</span>
              <IconDotsVertical className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-[160px] z-50">
            <DropdownMenuLabel>Actions</DropdownMenuLabel>
            <DropdownMenuItem
              onClick={() => navigator.clipboard.writeText(row.original.id!)}
            >
              Copy Workflow ID
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="!text-red-600">
              Cancel Workflow
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      );
    },
  },
];
