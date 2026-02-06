"use client";

import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface TableSkeletonProps {
  columnCount?: number;
  rowCount?: number;
}

export function TableSkeleton({
  columnCount = 5,
  rowCount = 10,
}: TableSkeletonProps) {
  return (
    <div className="w-full flex flex-col gap-6">
      <div className="mx-4 lg:mx-6 overflow-hidden rounded-md border shadow-sm mt-4">
        <Table>
          <TableHeader className="bg-muted text-[#21232D]">
            <TableRow className="hover:bg-transparent">
              {Array.from({ length: columnCount }).map((_, i) => (
                <TableHead key={i} className="h-10">
                  <Skeleton className="h-4 w-24" />
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {Array.from({ length: rowCount }).map((_, i) => (
              <TableRow key={i}>
                {Array.from({ length: columnCount }).map((_, j) => (
                  <TableCell key={j}>
                    <Skeleton className="h-4 w-full" />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="flex items-center justify-end px-6 py-2 gap-2">
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-8 w-8" />
        <Skeleton className="h-8 w-8" />
      </div>
    </div>
  );
}
