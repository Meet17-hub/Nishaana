"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { Target } from "lucide-react"
import { getCurrentUser } from "@/lib/api"
import { hasActiveSubscription } from "@/lib/subscription"

export default function HomePage() {
  const router = useRouter()

  useEffect(() => {
    let cancelled = false

    const clearStoredLogin = () => {
      localStorage.removeItem("lakshya_logged_in")
      localStorage.removeItem("lakshya_username")
    }

    const routeUser = async () => {
      const loggedIn = localStorage.getItem("lakshya_logged_in")
      if (!loggedIn) {
        router.replace("/login")
        return
      }

      const user = await getCurrentUser()
      if (cancelled) {
        return
      }

      if (!user) {
        clearStoredLogin()
        router.replace("/login")
        return
      }

      localStorage.setItem("lakshya_username", user.username)

      if (!hasActiveSubscription(user)) {
        clearStoredLogin()
        router.replace("/login")
        return
      }

      router.replace("/dashboard")
    }

    void routeUser()

    return () => {
      cancelled = true
    }
  }, [router])

  // Loading screen while redirecting
  return (
    <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
      <div className="text-center">
        <div className="w-24 h-24 rounded-full bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center mx-auto mb-6 animate-pulse">
          <Target className="w-12 h-12 text-white" />
        </div>
        <h1 className="text-3xl font-bold tracking-wider mb-2">
          <span className="bg-gradient-to-r from-orange-400 to-orange-600 bg-clip-text text-transparent">
            LAKSHYA
          </span>
        </h1>
        <p className="text-neutral-500">Loading...</p>
      </div>
    </div>
  )
}
