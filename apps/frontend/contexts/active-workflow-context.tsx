"use client";

import React, { createContext, useContext, useState, ReactNode } from "react";

interface ActiveWorkflowContextType {
  activeWorkflowDefinitionId: string | null;
  setActiveWorkflowDefinitionId: (id: string | null) => void;
}

const ActiveWorkflowContext = createContext<ActiveWorkflowContextType | undefined>(
  undefined
);

export function ActiveWorkflowProvider({ children }: { children: ReactNode }) {
  const [activeWorkflowDefinitionId, setActiveWorkflowDefinitionId] =
    useState<string | null>(null);

  return (
    <ActiveWorkflowContext.Provider
      value={{ activeWorkflowDefinitionId, setActiveWorkflowDefinitionId }}
    >
      {children}
    </ActiveWorkflowContext.Provider>
  );
}

export function useActiveWorkflow() {
  const context = useContext(ActiveWorkflowContext);
  if (context === undefined) {
    throw new Error(
      "useActiveWorkflow must be used within an ActiveWorkflowProvider"
    );
  }
  return context;
}
