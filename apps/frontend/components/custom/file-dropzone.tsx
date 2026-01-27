"use client";

import React, { useCallback, useState } from "react";
import { useDropzone, type Accept } from "react-dropzone";
import { cn } from "@/lib/utils";
import {
  IconUpload,
  IconFile,
  IconCheck,
  IconX,
  IconLoader2,
} from "@tabler/icons-react";

export interface UploadedFile {
  id: string;
  name: string;
  status: "uploading" | "success" | "error";
  error?: string;
}

interface FileDropzoneProps {
  onFilesSelect: (files: File[]) => void;
  uploadedFiles: UploadedFile[];
  accept?: Accept;
  maxFiles?: number;
  disabled?: boolean;
  isUploading?: boolean;
  className?: string;
}

export function FileDropzone({
  onFilesSelect,
  uploadedFiles,
  accept = { "application/pdf": [".pdf"] },
  maxFiles = 10,
  disabled = false,
  isUploading = false,
  className,
}: FileDropzoneProps) {
  const [isDragActive, setIsDragActive] = useState(false);

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length > 0 && !disabled && !isUploading) {
        onFilesSelect(acceptedFiles);
      }
    },
    [onFilesSelect, disabled, isUploading]
  );

  const { getRootProps, getInputProps, isDragReject } = useDropzone({
    onDrop,
    accept,
    maxFiles,
    disabled: disabled || isUploading,
    onDragEnter: () => setIsDragActive(true),
    onDragLeave: () => setIsDragActive(false),
    onDropAccepted: () => setIsDragActive(false),
    onDropRejected: () => setIsDragActive(false),
  });

  return (
    <div className={cn("w-full space-y-3 max-w-2xl", className)}>
      {/* Compact Dropzone Area */}
      <div
        {...getRootProps()}
        className={cn(
          "relative cursor-pointer rounded-lg border border-dashed p-6 transition-all duration-150",
          "flex flex-col items-center justify-center gap-3",
          "bg-background hover:bg-muted/30",
          isDragActive && !isDragReject && "border-primary bg-primary/5",
          isDragReject && "border-destructive bg-destructive/5",
          (disabled || isUploading) && "cursor-not-allowed opacity-50",
          !isDragActive && !disabled && "border-muted-foreground/30 hover:border-muted-foreground/50"
        )}
      >
        <input {...getInputProps()} />

        {/* Upload Icon */}
        {isUploading ? (
          <IconLoader2 className="size-6 text-primary animate-spin" />
        ) : (
          <IconUpload
            className={cn(
              "size-6 transition-colors",
              isDragActive && !isDragReject
                ? "text-primary"
                : isDragReject
                  ? "text-destructive"
                  : "text-muted-foreground"
            )}
          />
        )}

        {/* Text */}
        <div className="text-center">
          <p className="text-sm text-muted-foreground">
            {isDragReject
              ? "Invalid file type"
              : isDragActive
                ? "Drop files here"
                : "Drag & Drop or Click to Upload Files"}
          </p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            PDF files supported
          </p>
        </div>
      </div>

      {/* Uploaded Files - Compact inline list */}
      {uploadedFiles.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {uploadedFiles.map((file) => (
            <div
              key={file.id}
              className={cn(
                "inline-flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs",
                file.status === "success" && "border-green-500/40 bg-green-500/5 text-green-700 dark:text-green-400",
                file.status === "error" && "border-destructive/40 bg-destructive/5 text-destructive",
                file.status === "uploading" && "border-muted bg-muted/30 text-muted-foreground"
              )}
            >
              <IconFile className="size-3.5" />
              <span className="max-w-[150px] truncate">{file.name}</span>
              {file.status === "uploading" && (
                <IconLoader2 className="size-3.5 animate-spin" />
              )}
              {file.status === "success" && (
                <IconCheck className="size-3.5" />
              )}
              {file.status === "error" && (
                <IconX className="size-3.5" />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
