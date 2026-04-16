"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import {
  ChevronRight,
  Target,
  Crosshair,
  Activity,
  History,
  User,
  LogOut,
  Menu,
  Sun,
  Moon,
  Palette,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { useTheme } from "next-themes"
import { useAccent } from "@/components/accent-provider"
import { logout } from "@/lib/api"
import { clearCurrentSession } from "@/lib/session-store"

interface SidebarProps {
  activeSection: string
}

export default function Sidebar({ activeSection }: SidebarProps) {
  const router = useRouter()
  const { theme, setTheme } = useTheme()
  const { accent, cycleAccent } = useAccent()
  const [mounted, setMounted] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const handleNavigation = (section: string) => {
    if (section === "dashboard") {
      router.push("/dashboard")
    } else {
      router.push(`/${section}`)
    }
  }

  const handleSignout = async () => {
    clearCurrentSession()
    try {
      await logout()
    } catch (error) {
      console.error("Logout request failed:", error)
    }
    localStorage.removeItem("lakshya_logged_in")
    localStorage.removeItem("lakshya_username")
    localStorage.removeItem("lakshya_device_id")
    localStorage.removeItem("lakshya_device_ip")
    localStorage.removeItem("lakshya_start_clean")
    router.push("/login")
  }

  // Dynamic accent color classes
  const getAccentClasses = () => {
    switch (accent) {
      case "green":
        return {
          title: "text-green-500",
          active: "bg-green-500 shadow-green-500/20",
          hover: "hover:text-green-500",
        }
      case "blue":
        return {
          title: "text-blue-500",
          active: "bg-blue-500 shadow-blue-500/20",
          hover: "hover:text-blue-500",
        }
      default:
        return {
          title: "text-orange-500",
          active: "bg-orange-500 shadow-orange-500/20",
          hover: "hover:text-orange-500",
        }
    }
  }

  const accentClasses = getAccentClasses()

  return (
    <div
      className={`${sidebarCollapsed ? "w-20" : "w-64"} bg-card border-r border-border transition-all duration-300 flex flex-col`}
    >
      <div className="p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className={`${sidebarCollapsed ? "hidden" : "block"}`}>
            <h1 className={`${accentClasses.title} font-bold text-xl tracking-wider`}>LAKSHYA</h1>
            <p className="text-muted-foreground text-xs">TARGET SCORING SYSTEM</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className={`text-muted-foreground ${accentClasses.hover} hover:bg-accent`}
          >
            {sidebarCollapsed ? (
              <Menu className="w-5 h-5" />
            ) : (
              <ChevronRight className="w-5 h-5 rotate-180" />
            )}
          </Button>
        </div>

        {/* Navigation */}
        <nav className="space-y-2">
          {[
            { id: "dashboard", icon: Target, label: "DASHBOARD" },
            { id: "training", icon: Crosshair, label: "TRAINING" },
            { id: "analytics", icon: Activity, label: "ANALYTICS" },
            { id: "history", icon: History, label: "HISTORY" },
            { id: "profile", icon: User, label: "PROFILE" },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => handleNavigation(item.id)}
              className={`w-full flex items-center ${sidebarCollapsed ? "justify-center" : ""} gap-3 p-3 rounded-lg transition-all duration-200 ${
                activeSection === item.id
                  ? `${accentClasses.active} text-white shadow-lg`
                  : "text-muted-foreground hover:text-foreground hover:bg-accent"
              }`}
              title={sidebarCollapsed ? item.label : undefined}
            >
              <item.icon className={sidebarCollapsed ? "w-6 h-6" : "w-5 h-5"} />
              {!sidebarCollapsed && <span className="text-sm font-medium">{item.label}</span>}
            </button>
          ))}
        </nav>

        {/* Theme & Accent Toggle */}
        {!sidebarCollapsed && (
          <div className="mt-8 p-4 bg-accent/50 border border-border rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Theme</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                className="border-border text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                {mounted && (theme === "dark" ? (
                  <>
                    <Sun className="w-4 h-4 mr-2" />
                    Light
                  </>
                ) : (
                  <>
                    <Moon className="w-4 h-4 mr-2" />
                    Dark
                  </>
                ))}
              </Button>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Accent</span>
              <Button
                variant="outline"
                size="sm"
                onClick={cycleAccent}
                className="border-border text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                {mounted && (
                  <>
                    <Palette className={`w-4 h-4 mr-2 ${
                      accent === "orange" ? "text-orange-500" : 
                      accent === "green" ? "text-green-500" : 
                      "text-blue-500"
                    }`} />
                    {accent.charAt(0).toUpperCase() + accent.slice(1)}
                  </>
                )}
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Signout */}
      <div className="mt-auto p-4">
        <button
          onClick={handleSignout}
          className={`w-full flex items-center ${sidebarCollapsed ? "justify-center" : ""} gap-3 p-3 rounded-lg text-muted-foreground hover:text-white hover:bg-red-500 transition-colors`}
          title={sidebarCollapsed ? "SIGNOUT" : undefined}
        >
          <LogOut className={sidebarCollapsed ? "w-6 h-6" : "w-5 h-5"} />
          {!sidebarCollapsed && <span className="text-sm font-medium">SIGNOUT</span>}
        </button>
      </div>
    </div>
  )
}
