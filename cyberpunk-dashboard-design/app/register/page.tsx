"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Target, User, Lock, Mail, AlertCircle, CheckCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { useAccent } from "@/components/accent-provider"
import { getErrorMessage, registerUser } from "@/lib/api"

export default function RegisterPage() {
  const router = useRouter()
  const { accent } = useAccent()
  const [mounted, setMounted] = useState(false)
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    setMounted(true)
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setIsLoading(true)

    if (!username || !email || !password || !confirmPassword) {
      setError("All fields are required")
      setIsLoading(false)
      return
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match")
      setIsLoading(false)
      return
    }

    if (password.length < 6) {
      setError("Password must be at least 6 characters")
      setIsLoading(false)
      return
    }

    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email)) {
      setError("Please enter a valid email address")
      setIsLoading(false)
      return
    }

    try {
      const response = await registerUser(username.trim(), email.trim(), password)
      if (!response.ok) {
        setError(await getErrorMessage(response, "Registration failed"))
        return
      }

      // Success
      setSuccess(true)
      setTimeout(() => {
        router.push("/login")
      }, 2000)
    } catch (err) {
      console.error("Registration error:", err)
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
              REGISTER
            </span>
          </CardTitle>
          <CardDescription className="text-muted-foreground tracking-wide">
            CREATE YOUR LAKSHYA ACCOUNT
          </CardDescription>
        </CardHeader>

        <CardContent className="pt-6">
          {success ? (
            <div className="text-center py-8">
              <div className="w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-4">
                <CheckCircle className="w-8 h-8 text-green-500" />
              </div>
              <h3 className="text-xl font-semibold text-foreground mb-2">Registration Successful!</h3>
              <p className="text-muted-foreground">Redirecting to login...</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                  <AlertCircle className="w-4 h-4" />
                  {error}
                </div>
              )}

              <div className="space-y-2">
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
                    className={`pl-10 bg-secondary border-border text-foreground placeholder:text-muted-foreground ${accentFocus}`}
                    placeholder="Enter username"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="email" className="text-foreground text-sm tracking-wide">
                  EMAIL
                </Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className={`pl-10 bg-secondary border-border text-foreground placeholder:text-muted-foreground ${accentFocus}`}
                    placeholder="Enter email"
                  />
                </div>
              </div>

              <div className="space-y-2">
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
                    className={`pl-10 bg-secondary border-border text-foreground placeholder:text-muted-foreground ${accentFocus}`}
                    placeholder="Enter password"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirmPassword" className="text-foreground text-sm tracking-wide">
                  CONFIRM PASSWORD
                </Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    id="confirmPassword"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className={`pl-10 bg-secondary border-border text-foreground placeholder:text-muted-foreground ${accentFocus}`}
                    placeholder="Confirm password"
                  />
                </div>
              </div>

              <Button
                type="submit"
                disabled={isLoading}
                className={`w-full bg-gradient-to-r ${accentGradient} ${accentGradientHover} text-white font-semibold py-5 tracking-wide transition-all duration-300 shadow-lg ${accentShadow} ${accentShadowHover}`}
              >
                {isLoading ? (
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    CREATING ACCOUNT...
                  </div>
                ) : (
                  "CREATE ACCOUNT"
                )}
              </Button>

              <p className="text-center text-xs text-muted-foreground mt-4">
                Already have an account?{" "}
                <a href="/login" className={`${accentText} ${accentTextHover} transition-colors`}>
                  Login here
                </a>
              </p>
            </form>
          )}
        </CardContent>
      </Card>

      {/* Bottom decorative line */}
      <div className={`absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent ${accentVia} to-transparent opacity-50`} />
    </div>
  )
}
