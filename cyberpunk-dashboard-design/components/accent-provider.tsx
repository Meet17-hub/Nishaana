"use client"

import * as React from "react"

type AccentColor = "orange" | "green" | "blue"

interface AccentProviderProps {
  children: React.ReactNode
  defaultAccent?: AccentColor
  storageKey?: string
}

interface AccentProviderState {
  accent: AccentColor
  setAccent: (accent: AccentColor) => void
  cycleAccent: () => void
}

const AccentProviderContext = React.createContext<AccentProviderState | undefined>(undefined)

const accentCycle: AccentColor[] = ["blue", "green", "orange"]

export function AccentProvider({
  children,
  defaultAccent = "orange",
  storageKey = "lakshya-accent",
  ...props
}: AccentProviderProps) {
  const [accent, setAccentState] = React.useState<AccentColor>(defaultAccent)
  const [mounted, setMounted] = React.useState(false)

  // Load accent from localStorage on mount
  React.useEffect(() => {
    const stored = localStorage.getItem(storageKey) as AccentColor | null
    if (stored && accentCycle.includes(stored)) {
      setAccentState(stored)
    }
    setMounted(true)
  }, [storageKey])

  // Apply accent class to document
  React.useEffect(() => {
    if (!mounted) return
    
    const root = document.documentElement
    // Remove all accent classes
    root.classList.remove("accent-orange", "accent-green", "accent-blue")
    // Add current accent class
    root.classList.add(`accent-${accent}`)
  }, [accent, mounted])

  const setAccent = React.useCallback((newAccent: AccentColor) => {
    setAccentState(newAccent)
    localStorage.setItem(storageKey, newAccent)
  }, [storageKey])

  const cycleAccent = React.useCallback(() => {
    const currentIndex = accentCycle.indexOf(accent)
    const nextIndex = (currentIndex + 1) % accentCycle.length
    const nextAccent = accentCycle[nextIndex]
    setAccent(nextAccent)
  }, [accent, setAccent])

  const value = {
    accent,
    setAccent,
    cycleAccent,
  }

  return (
    <AccentProviderContext.Provider {...props} value={value}>
      {children}
    </AccentProviderContext.Provider>
  )
}

export const useAccent = () => {
  const context = React.useContext(AccentProviderContext)

  if (context === undefined)
    throw new Error("useAccent must be used within an AccentProvider")

  return context
}

// Helper to get accent colors for components
export const accentColors = {
  orange: {
    primary: "orange-500",
    hover: "orange-600",
    bg: "orange-500/10",
    border: "orange-500/50",
    text: "text-orange-500",
    hex: "#f97316",
  },
  green: {
    primary: "green-500",
    hover: "green-600",
    bg: "green-500/10",
    border: "green-500/50",
    text: "text-green-500",
    hex: "#1dd88a",
  },
  blue: {
    primary: "blue-500",
    hover: "blue-600",
    bg: "blue-500/10",
    border: "blue-500/50",
    text: "text-blue-500",
    hex: "#3b82f6",
  },
}
