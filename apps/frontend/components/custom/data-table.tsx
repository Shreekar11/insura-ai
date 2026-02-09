"use client";

import * as React from "react";
import {
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconChevronsLeft,
  IconChevronsRight,
  IconLayoutColumns,
  IconPlus,
} from "@tabler/icons-react";
import {
  flexRender,
  getCoreRowModel,
  getFacetedRowModel,
  getFacetedUniqueValues,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnFiltersState,
  type Row,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table";
import { useRouter, usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent } from "@/components/ui/tabs";

function ClickableRow<TData>({ row }: { row: Row<TData> }) {
  const router = useRouter();

  const handleRowClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (
      target.closest("button") ||
      target.closest('input[type="checkbox"]') ||
      target.closest("a") ||
      target.closest('[role="button"]')
    ) {
      return;
    }

    // Get workflow_id from the row data
    const workflowId =
      (row.original as any).workflow_id || (row.original as any).id;

    if (workflowId) {
      router.push(`/workflow-execution/${workflowId}`);
    }
  };

  return (
    <TableRow
      data-state={row.getIsSelected() && "selected"}
      onClick={handleRowClick}
      className="cursor-pointer hover:bg-muted transition-colors"
    >
      {row.getVisibleCells().map((cell: any) => (
        <TableCell key={cell.id}>
          {flexRender(cell.column.columnDef.cell, cell.getContext())}
        </TableCell>
      ))}
    </TableRow>
  );
}

export function DataTable<TData, TValue>({
  title,
  data: initialData,
  columns,
  onAddClick,
  addLabel = "Add Item",
  manualPagination = false,
  pageCount,
  paginationState,
  onPaginationChange,
  workflowDefinitionId,
  total,
  workflowDefinitions,
}: {
  title?: string;
  data: TData[];
  columns: ColumnDef<TData, TValue>[];
  onAddClick?: (workflowDefinitionId: string) => void;
  addLabel?: string;
  manualPagination?: boolean;
  pageCount?: number;
  paginationState?: {
    pageIndex: number;
    pageSize: number;
  };
  onPaginationChange?: (pagination: {
    pageIndex: number;
    pageSize: number;
  }) => void;
  workflowDefinitionId?: string;
  total?: number;
  workflowDefinitions?: any[];
}) {
  const pathname = usePathname();
  const [data, setData] = React.useState(() => initialData);
  const [rowSelection, setRowSelection] = React.useState({});
  const [columnVisibility, setColumnVisibility] =
    React.useState<VisibilityState>({});
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>(
    [],
  );
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [paginationInternal, setPaginationInternal] = React.useState({
    pageIndex: 0,
    pageSize: 10,
  });

  // Update internal data state when initialData changes
  React.useEffect(() => {
    setData(initialData);
  }, [initialData]);

  // Determine whether to use controlled or uncontrolled pagination state
  const pagination = paginationState ?? paginationInternal;
  const setPagination = (updater: any) => {
    const nextValue =
      typeof updater === "function" ? updater(pagination) : updater;
    if (onPaginationChange) {
      onPaginationChange(nextValue);
    } else {
      setPaginationInternal(nextValue);
    }
  };

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnVisibility,
      rowSelection,
      columnFilters,
      pagination,
    },
    getRowId: (row: any) => row.id.toString(),
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFacetedRowModel: getFacetedRowModel(),
    getFacetedUniqueValues: getFacetedUniqueValues(),
    manualPagination,
    pageCount,
  });

  return (
    <div className="w-full flex flex-col gap-6">
      <div
        className={`flex flex-col gap-4 px-4 lg:px-6 ${pathname === "/dashboard" ? "" : "pt-4"}`}
      >
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-1">
            {pathname !== "/dashboard" && (
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                {(initialData[0] as any)?.definition_name ||
                  workflowDefinitions?.find(
                    (def) => def.id === workflowDefinitionId,
                  )?.name ||
                  "Workflow"}{" "}
                Overview
              </h1>
            )}
            <p className="text-sm text-muted-foreground">
              Manage and monitor your workflow executions.
            </p>
          </div>
          <div
            className={`flex items-center gap-2 ${pathname === "/dashboard" ? "justify-end w-full" : ""}`}
          >
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  className="h-8 gap-1 rounded"
                  size="sm"
                >
                  <IconLayoutColumns className="size-3.5" />
                  <span className="hidden lg:inline">View</span>
                  <IconChevronDown className="size-3.5 text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                {table
                  .getAllColumns()
                  .filter(
                    (column: any) =>
                      typeof column.accessorFn !== "undefined" &&
                      column.getCanHide(),
                  )
                  .map((column: any) => {
                    return (
                      <DropdownMenuCheckboxItem
                        key={column.id}
                        className="capitalize"
                        checked={column.getIsVisible()}
                        onCheckedChange={(value) =>
                          column.toggleVisibility(!!value)
                        }
                      >
                        {column.id}
                      </DropdownMenuCheckboxItem>
                    );
                  })}
              </DropdownMenuContent>
            </DropdownMenu>
            {onAddClick &&
              (pathname === "/dashboard" &&
              workflowDefinitions &&
              workflowDefinitions.length > 0 ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="outline"
                      className="h-8 gap-1 rounded"
                      size="sm"
                    >
                      <IconPlus className="size-3.5" />
                      <span className="hidden lg:inline">{addLabel}</span>
                      <IconChevronDown className="size-3.5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    <DropdownMenuLabel>Select Workflow</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    {workflowDefinitions.map((def) => (
                      <DropdownMenuItem
                        key={def.id}
                        onClick={() => onAddClick(def.id)}
                      >
                        {def.name}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <Button
                  variant="outline"
                  className="h-8 gap-1 rounded"
                  size="sm"
                  onClick={() => onAddClick(workflowDefinitionId || "")}
                >
                  <IconPlus className="size-3.5" />
                  <span className="hidden lg:inline">{addLabel}</span>
                </Button>
              ))}
          </div>
        </div>
      </div>

      <div className="mx-4 lg:mx-6 overflow-hidden rounded-md border shadow-sm">
        <Table>
          <TableHeader className="bg-muted">
            {table.getHeaderGroups().map((headerGroup: any) => (
              <TableRow key={headerGroup.id} className="hover:bg-transparent">
                {headerGroup.headers.map((header: any) => {
                  return (
                    <TableHead
                      key={header.id}
                      colSpan={header.colSpan}
                      className="h-10 text-xs font-medium uppercase tracking-wider text-muted-foreground"
                    >
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows?.length ? (
              table
                .getRowModel()
                .rows.map((row: any) => <ClickableRow key={row.id} row={row} />)
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-24 text-center text-muted-foreground hover:bg-transparent"
                >
                  No flows found. Create one to get started.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className="flex items-center justify-end px-2 py-2">
        <div className="flex w-full items-center gap-8 lg:w-fit">
          <div className="hidden items-center gap-2 lg:flex">
            <p className="text-sm font-medium text-muted-foreground">
              Rows per page
            </p>
            <Select
              value={`${table.getState().pagination.pageSize}`}
              onValueChange={(value) => {
                table.setPageSize(Number(value));
              }}
            >
              <SelectTrigger size="sm" className="h-8 w-[70px]">
                <SelectValue
                  placeholder={table.getState().pagination.pageSize}
                />
              </SelectTrigger>
              <SelectContent side="top">
                {[10, 20, 30, 40, 50, 100]
                  .filter(
                    (size) =>
                      total === undefined || size <= total || size === 10,
                  )
                  .concat(
                    total !== undefined &&
                      total > 0 &&
                      ![10, 20, 30, 40, 50, 100].includes(total)
                      ? [total]
                      : [],
                  )
                  .sort((a, b) => a - b)
                  .map((pageSize) => (
                    <SelectItem key={pageSize} value={`${pageSize}`}>
                      {pageSize}
                    </SelectItem>
                  ))}
                {total !== undefined && total > 100 && (
                  <SelectItem value="100">100 (Max)</SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>
          <div className="flex w-fit items-center justify-center text-sm font-medium text-muted-foreground">
            Page {table.getState().pagination.pageIndex + 1} of{" "}
            {table.getPageCount()}
          </div>
          <div className="ml-auto flex items-center gap-2 lg:ml-0">
            <Button
              variant="outline"
              className="hidden h-8 w-8 p-0 lg:flex"
              onClick={() => table.setPageIndex(0)}
              disabled={!table.getCanPreviousPage()}
            >
              <span className="sr-only">Go to first page</span>
              <IconChevronsLeft className="size-4" />
            </Button>
            <Button
              variant="outline"
              className="size-8 p-0"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              <span className="sr-only">Go to previous page</span>
              <IconChevronLeft className="size-4" />
            </Button>
            <Button
              variant="outline"
              className="size-8 p-0"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              <span className="sr-only">Go to next page</span>
              <IconChevronRight className="size-4" />
            </Button>
            <Button
              variant="outline"
              className="hidden size-8 p-0 lg:flex"
              onClick={() => table.setPageIndex(table.getPageCount() - 1)}
              disabled={!table.getCanNextPage()}
            >
              <span className="sr-only">Go to last page</span>
              <IconChevronsRight className="size-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
