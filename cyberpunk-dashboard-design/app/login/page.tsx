"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { Target, User, Lock, Cpu, AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useAccent } from "@/components/accent-provider"
import { getErrorMessage, login as loginUser } from "@/lib/api"
import { hasActiveSubscription } from "@/lib/subscription"
import {
  getDeviceOptions,
  isCustomDevice,
  getLastCustomIpOctets,
  octetsToIp,
  validateOctet,
  saveCustomIp,
  getIpForDevice,
} from "@/lib/device-ips"
import { detectLocalIP } from "@/lib/detect-ip"

export default function LoginPage() {
  const router = useRouter()
  const { accent } = useAccent()
  const [mounted, setMounted] = useState(false)
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [deviceId, setDeviceId] = useState("")
  const [error, setError] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [localIP, setLocalIP] = useState<string>("")

  // Custom IP octet inputs
  const [customOctets, setCustomOctets] = useState<number[]>([192, 168, 1, 1])
  const octetRefs = [
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
  ]

  // Device options from shared config
  const deviceOptions = getDeviceOptions()

  useEffect(() => {
    setMounted(true)
    // Load last custom IP from localStorage
    setCustomOctets(getLastCustomIpOctets())
    
    // Detect local IP
    detectLocalIP()
      .then((ip) => setLocalIP(ip))
      .catch(() => setLocalIP(""))
  }, [])

  // Dynamic accent classes
  const accentBgGlow = accent === "orange" 
    ? "bg-orange-500/10" 
    : accent === "green" 
    ? "bg-green-500/10" 
    : "bg-blue-500/10"
  const accentBgGlow2 = accent === "orange" 
    ? "bg-orange-600/10" 
    : accent === "green" 
    ? "bg-green-600/10" 
    : "bg-blue-600/10"
  const accentBorderGlow = accent === "orange" 
    ? "border-orange-500/10" 
    : accent === "green" 
    ? "border-green-500/10" 
    : "border-blue-500/10"
  const accentBorderGlow2 = accent === "orange" 
    ? "border-orange-500/5" 
    : accent === "green" 
    ? "border-green-500/5" 
    : "border-blue-500/5"
  const accentGradient = accent === "orange" 
    ? "from-orange-500 to-orange-600" 
    : accent === "green" 
    ? "from-green-500 to-green-600" 
    : "from-blue-500 to-blue-600"
  const accentGradientHover = accent === "orange" 
    ? "hover:from-orange-600 hover:to-orange-700" 
    : accent === "green" 
    ? "hover:from-green-600 hover:to-green-700" 
    : "hover:from-blue-600 hover:to-blue-700"
  const accentShadow = accent === "orange" 
    ? "shadow-orange-500/20" 
    : accent === "green" 
    ? "shadow-green-500/20" 
    : "shadow-blue-500/20"
  const accentShadowHover = accent === "orange" 
    ? "hover:shadow-orange-500/40" 
    : accent === "green" 
    ? "hover:shadow-green-500/40" 
    : "hover:shadow-blue-500/40"
  const accentTextGradient = accent === "orange" 
    ? "from-orange-400 to-orange-600" 
    : accent === "green" 
    ? "from-green-400 to-green-600" 
    : "from-blue-400 to-blue-600"
  const accentBg = accent === "orange" 
    ? "bg-orange-500" 
    : accent === "green" 
    ? "bg-green-500" 
    : "bg-blue-500"
  const accentText = accent === "orange" 
    ? "text-orange-500" 
    : accent === "green" 
    ? "text-green-500" 
    : "text-blue-500"
  const accentTextHover = accent === "orange" 
    ? "hover:text-orange-400" 
    : accent === "green" 
    ? "hover:text-green-400" 
    : "hover:text-blue-400"
  const accentFocus = accent === "orange" 
    ? "focus:border-orange-500 focus:ring-orange-500/20" 
    : accent === "green" 
    ? "focus:border-green-500 focus:ring-green-500/20" 
    : "focus:border-blue-500 focus:ring-blue-500/20"
  const accentHoverBg = accent === "orange" 
    ? "hover:bg-orange-500/20 focus:bg-orange-500/20" 
    : accent === "green" 
    ? "hover:bg-green-500/20 focus:bg-green-500/20" 
    : "hover:bg-blue-500/20 focus:bg-blue-500/20"
  const gridColor = accent === "orange" 
    ? "rgba(249, 115, 22, 0.3)" 
    : accent === "green" 
    ? "rgba(29, 216, 138, 0.3)" 
    : "rgba(59, 130, 246, 0.3)"
  const accentVia = accent === "orange" 
    ? "via-orange-500" 
    : accent === "green" 
    ? "via-green-500" 
    : "via-blue-500"

  // Handle octet input change
  const handleOctetChange = (index: number, value: string) => {
    // Allow only digits
    const digitsOnly = value.replace(/\D/g, "")
    const numValue = validateOctet(digitsOnly)
    
    const newOctets = [...customOctets]
    newOctets[index] = numValue
    setCustomOctets(newOctets)

    // Auto-advance to next field if 3 digits entered or value >= 26 (can't be more)
    if (digitsOnly.length === 3 || (digitsOnly.length >= 2 && numValue >= 26)) {
      if (index < 3 && octetRefs[index + 1].current) {
        octetRefs[index + 1].current?.focus()
        octetRefs[index + 1].current?.select()
      }
    }
  }

  // Handle keydown for Tab/Enter navigation and backspace
  const handleOctetKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Tab" || e.key === "Enter") {
      if (!e.shiftKey && index < 3) {
        e.preventDefault()
        octetRefs[index + 1].current?.focus()
        octetRefs[index + 1].current?.select()
      } else if (e.shiftKey && index > 0) {
        e.preventDefault()
        octetRefs[index - 1].current?.focus()
        octetRefs[index - 1].current?.select()
      }
    } else if (e.key === "Backspace" && (e.target as HTMLInputElement).value === "" && index > 0) {
      e.preventDefault()
      octetRefs[index - 1].current?.focus()
    } else if (e.key === "." || e.key === "ArrowRight") {
      if (index < 3) {
        e.preventDefault()
        octetRefs[index + 1].current?.focus()
        octetRefs[index + 1].current?.select()
      }
    } else if (e.key === "ArrowLeft" && index > 0) {
      e.preventDefault()
      octetRefs[index - 1].current?.focus()
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setIsLoading(true)

    if (!username || !password || !deviceId) {
      setError("All fields are required")
      setIsLoading(false)
      return
    }

    try {
      const customIp = isCustomDevice(deviceId) ? octetsToIp(customOctets) : undefined
      if (customIp) {
        saveCustomIp(customIp)
      }

      const response = await loginUser(username.trim(), password, deviceId, customIp)
      const data = await response.json().catch(() => null) as
        | { error?: string; selected_ip?: string; user?: { username: string; subscription_end?: string | null } }
        | null

      if (!response.ok || !data?.user) {
        setError(data?.error || await getErrorMessage(response, "Login failed"))
        return
      }

      const finalIp = data.selected_ip || customIp || getIpForDevice(deviceId)
      localStorage.setItem("lakshya_logged_in", "true")
      localStorage.setItem("lakshya_username", data.user.username)
      localStorage.setItem("lakshya_device_id", deviceId)
      localStorage.setItem("lakshya_device_ip", finalIp)
      localStorage.setItem("lakshya_start_clean", "true")
      router.push(hasActiveSubscription(data.user) ? "/dashboard" : "/subscription")
    } catch (err) {
      console.error("Login error:", err)
      setError("An unexpected error occurred. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4 relative overflow-hidden">
      {/* Animated background effects */}
      <div className="absolute inset-0 overflow-hidden">
        <div className={`absolute top-1/4 left-1/4 w-96 h-96 ${accentBgGlow} rounded-full blur-3xl animate-pulse`} />
        <div className={`absolute bottom-1/4 right-1/4 w-96 h-96 ${accentBgGlow2} rounded-full blur-3xl animate-pulse delay-1000`} />
        <div className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] border ${accentBorderGlow} rounded-full`} />
        <div className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] border ${accentBorderGlow2} rounded-full`} />
      </div>

      {/* Grid overlay */}
      {mounted && (
        <div 
          className="absolute inset-0 opacity-5"
          style={{
            backgroundImage: `
              linear-gradient(${gridColor} 1px, transparent 1px),
              linear-gradient(90deg, ${gridColor} 1px, transparent 1px)
            `,
            backgroundSize: '50px 50px'
          }}
        />
      )}

      <Card className="w-full max-w-md bg-card/90 border-border backdrop-blur-xl relative z-10">
        <CardHeader className="text-center pb-2">
          {/* Logo */}
          <div className="flex justify-center mb-4">
            <div className={`w-20 h-20 rounded-full bg-gradient-to-br ${accentGradient} flex items-center justify-center shadow-lg ${accentShadow}`}>
              <Target className="w-10 h-10 text-white" />
            </div>
          </div>
          
          <CardTitle className="text-3xl font-bold tracking-wider">
            <span className={`bg-gradient-to-r ${accentTextGradient} bg-clip-text text-transparent`}>
              LAKSHYA
            </span>
          </CardTitle>
          <CardDescription className="text-muted-foreground tracking-wide">
            TARGET SCORING SYSTEM
          </CardDescription>
          <div className="flex items-center justify-center gap-2 mt-2">
            <div className={`w-2 h-2 ${accentBg} rounded-full animate-pulse`} />
            <span className="text-xs text-muted-foreground font-mono">v2.1.7 SECURE ACCESS</span>
          </div>
        </CardHeader>

        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-5" suppressHydrationWarning>
            {error && (
              <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                <AlertCircle className="w-4 h-4" />
                {error}
              </div>
            )}

            <div className="space-y-2" suppressHydrationWarning>
              <Label htmlFor="username" className="text-foreground text-sm tracking-wide">
                USERNAME
              </Label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  suppressHydrationWarning
                  className={`pl-10 bg-secondary border-border text-foreground placeholder:text-muted-foreground ${accentFocus}`}
                  placeholder="Enter username"
                />
              </div>
            </div>

            <div className="space-y-2" suppressHydrationWarning>
              <Label htmlFor="password" className="text-foreground text-sm tracking-wide">
                PASSWORD
              </Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  suppressHydrationWarning
                  className={`pl-10 bg-secondary border-border text-foreground placeholder:text-muted-foreground ${accentFocus}`}
                  placeholder="Enter password"
                />
              </div>
            </div>

            <div className="space-y-2" suppressHydrationWarning>
              <Label htmlFor="device" className="text-foreground text-sm tracking-wide">
                TARGET DEVICE
              </Label>
              <div className="relative">
                <Cpu className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground z-10" />
                <Select value={deviceId} onValueChange={setDeviceId}>
                  <SelectTrigger className={`pl-10 bg-secondary border-border text-foreground ${accentFocus}`} suppressHydrationWarning>
                    <SelectValue placeholder="Select device" />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border max-h-60">
                    {deviceOptions.map((device) => (
                      <SelectItem 
                        key={device.id} 
                        value={device.id}
                        className={`text-foreground ${accentHoverBg}`}
                      >
                        {device.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Custom IP octet inputs - shown when "Other IP" is selected */}
              {isCustomDevice(deviceId) && (
                <div className="mt-3 p-3 bg-secondary/50 rounded-lg border border-border" suppressHydrationWarning>
                  <Label className="text-xs text-muted-foreground mb-2 block">
                    ENTER CUSTOM IP ADDRESS
                  </Label>
                  <div className="flex items-center justify-center gap-1">
                    {customOctets.map((octet, index) => (
                      <div key={index} className="flex items-center">
                        <Input
                          ref={octetRefs[index]}
                          type="text"
                          inputMode="numeric"
                          maxLength={3}
                          value={octet.toString()}
                          onChange={(e) => handleOctetChange(index, e.target.value)}
                          onKeyDown={(e) => handleOctetKeyDown(index, e)}
                          onFocus={(e) => e.target.select()}
                          suppressHydrationWarning
                          className={`w-14 text-center bg-secondary border-border text-foreground font-mono ${accentFocus}`}
                          placeholder="0"
                        />
                        {index < 3 && (
                          <span className="text-muted-foreground text-lg font-bold mx-1">.</span>
                        )}
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground mt-2 text-center">
                    Current: {octetsToIp(customOctets)}
                  </p>
                </div>
              )}
            </div>

            <Button
              type="submit"
              disabled={isLoading}
              suppressHydrationWarning
              className={`w-full bg-gradient-to-r ${accentGradient} ${accentGradientHover} text-white font-semibold py-5 tracking-wide transition-all duration-300 shadow-lg ${accentShadow} ${accentShadowHover}`}
            >
              {isLoading ? (
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  AUTHENTICATING...
                </div>
              ) : (
                "ACCESS SYSTEM"
              )}
            </Button>

            <p className="text-center text-xs text-muted-foreground mt-4">
              Don&apos;t have an account?{" "}
              <a href="/register" className={`${accentText} ${accentTextHover} transition-colors`}>
                Register here
              </a>
            </p>
          </form>
        </CardContent>
      </Card>

      {/* Bottom decorative line */}
      <div className={`absolute bottom-12 left-0 right-0 h-1 bg-gradient-to-r from-transparent ${accentVia} to-transparent opacity-50`} />

      {/* Local IP Detection - Display at Bottom */}
      {localIP && (
        <div className="fixed bottom-4 left-0 right-0 text-center">
          <p className="text-xs text-muted-foreground">
            Your Local IP: <span className={`${accentText} font-mono font-semibold`}>{localIP}</span>
          </p>
        </div>
      )}
    </div>
  )
}
