"use client"

import React from "react"

interface DashboardHeaderProps {
  userName?: string
}

export function DashboardHeader({userName = "User" }: DashboardHeaderProps) {
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

  return (
    <div className="flex flex-col gap-6 px-4 lg:px-6 pb-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">
          {greeting}, {userName}
        </h1>
      </div>
    </div>
  )
}