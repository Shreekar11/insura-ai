"use client"

import React from "react"
import { IconActivity, IconCircleCheck, IconAlertCircle } from "@tabler/icons-react"
import { WorkflowListItem } from "@/schema/generated/workflows"

interface DashboardHeaderProps {
  workflows: WorkflowListItem[]
  userName?: string
}

export function DashboardHeader({ workflows, userName = "User" }: DashboardHeaderProps) {
  const [greeting, setGreeting] = React.useState("")

  React.useEffect(() => {
    const hour = new Date().getHours()
    if (hour < 12) {
      setGreeting("Good morning")
    } else if (hour < 18) {
      setGreeting("Good afternoon")
    } else {
      setGreeting("Good evening")
    }
  }, [])

  const stats = {
    total: workflows.length,
    running: workflows.filter(w => w.status?.toLowerCase() === "running").length,
    completed: workflows.filter(w => w.status?.toLowerCase() === "completed").length,
    failed: workflows.filter(w => w.status?.toLowerCase() === "failed").length
  }

  return (
    <div className="flex flex-col gap-6 px-4 lg:px-6 pb-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">
          {greeting}, {userName}
        </h1>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
        <StatCard 
          label="Total Workflows" 
          value={stats.total} 
          icon={<IconActivity className="size-4" />}
          color="blue"
        />
        <StatCard 
          label="Active" 
          value={stats.running} 
          icon={<IconLoader className="size-4 animate-spin" />}
          color="indigo" 
        />
        <StatCard 
          label="Completed" 
          value={stats.completed} 
          icon={<IconCircleCheck className="size-4" />}
          color="emerald" 
        />
        <StatCard 
          label="Issues" 
          value={stats.failed} 
          icon={<IconAlertCircle className="size-4" />}
          color="red" 
        />
      </div>
    </div>
  )
}

function StatCard({ label, value, icon, color }: { label: string, value: number, icon: any, color: string }) {
  const colorMap: Record<string, string> = {
    blue: "text-blue-600 bg-blue-50 dark:bg-blue-500/10",
    indigo: "text-indigo-600 bg-indigo-50 dark:bg-indigo-500/10",
    emerald: "text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10",
    red: "text-red-600 bg-red-50 dark:bg-red-500/10"
  }

  return (
    <div className="flex flex-col gap-1 p-4 rounded-2xl border border-border bg-card shadow-sm hover:shadow-md transition-all duration-300">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground uppercase">{label}</span>
        <div className={`p-1.5 rounded-lg ${colorMap[color]}`}>
          {icon}
        </div>
      </div>
      <span className="text-2xl font-bold text-foreground">{value}</span>
    </div>
  )
}

function IconLoader({ className }: { className?: string }) {
  return (
    <svg 
      xmlns="http://www.w3.org/2000/svg" 
      width="24" 
      height="24" 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round" 
      className={className}
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  )
}
