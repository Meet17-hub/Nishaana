"use client"

import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import {
  Activity,
  TrendingUp,
  BarChart3,
  PieChart,
  Send,
  RefreshCw,
  Mail,
  Edit2,
  Save,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { getAllSessions, getAllHistory, type SessionData, type SeriesHistoryItem } from "@/lib/session-store"
import type { Shot } from "@/lib/api"
import { getCurrentUser, sendEmailWithWrap } from "@/lib/api"
import Sidebar from "@/components/sidebar"
import { useAccent } from "@/components/accent-provider"
import { useToast } from "@/hooks/use-toast"

interface ScoreDistribution {
  range: string
  count: number
  percentage: number
  color: string
}

export default function AnalyticsPage() {
  const router = useRouter()
  const { accent } = useAccent()
  const { toast } = useToast()
  const [username, setUsername] = useState<string>("")
  const [userEmail, setUserEmail] = useState<string>("")
  const [emailEditing, setEmailEditing] = useState(false)
  const [editingEmail, setEditingEmail] = useState<string>("")
  const [isSendingEmail, setIsSendingEmail] = useState(false)
  const [stats, setStats] = useState({
    totalSessions: 0,
    totalShots: 0,
    averageScore: 0,
    bestScore: 0,
    bestSingleShot: 0,
    rifleShots: 0,
    pistolShots: 0,
  })
  const [scoreDistribution, setScoreDistribution] = useState<ScoreDistribution[]>([])
  const [hasData, setHasData] = useState(false)

  useEffect(() => {
    let cancelled = false

    const initialize = async () => {
      const loggedIn = localStorage.getItem("lakshya_logged_in")
      if (!loggedIn) {
        router.push("/login")
        return
      }

      const currentUser = await getCurrentUser()
      if (!currentUser) {
        if (!cancelled) {
          router.push("/login")
        }
        return
      }

      if (cancelled) {
        return
      }

      localStorage.setItem("lakshya_username", currentUser.username)
      setUsername(currentUser.username)
      setUserEmail(currentUser.email)
      setEditingEmail(currentUser.email)

      const sessions = getAllSessions()
      const history = getAllHistory()

      const allShots: { shot: Shot; mode: 'rifle' | 'pistol' }[] = []
      let totalScoreSum = 0
      let bestSessionScore = 0
      let rifleShots = 0
      let pistolShots = 0
      let totalSeries = 0
      let totalInner10 = 0

      sessions.forEach((session: SessionData) => {
        session.shots.forEach((shot) => {
          allShots.push({ shot, mode: session.mode })
        })
        totalScoreSum += session.totalScore
        if (session.totalScore > bestSessionScore) bestSessionScore = session.totalScore
        if (session.mode === "rifle") rifleShots += session.shots.length
        else pistolShots += session.shots.length
      })

      history.forEach((item: SeriesHistoryItem) => {
        item.shots.forEach((shot) => {
          allShots.push({ shot, mode: item.mode })
        })
        totalScoreSum += item.totalScore
        totalInner10 += item.inner10
        if (item.totalScore > bestSessionScore) bestSessionScore = item.totalScore
        if (item.mode === "rifle") rifleShots += item.shots.length
        else pistolShots += item.shots.length
        totalSeries++
      })

      const totalShots = allShots.length
      const combinedSessionCount = sessions.length + totalSeries

      let bestSingleShot = 0
      allShots.forEach(({ shot }) => {
        if (shot.score > bestSingleShot) bestSingleShot = shot.score
      })

      let range9to10 = 0
      let range8to9 = 0
      let range7to8 = 0
      let below7 = 0

      allShots.forEach(({ shot }) => {
        const score = shot.score
        if (score >= 9.0) range9to10++
        else if (score >= 8.0) range8to9++
        else if (score >= 7.0) range7to8++
        else below7++
      })

      const distribution: ScoreDistribution[] = totalShots > 0 ? [
        {
          range: "9.0 - 10.0",
          count: range9to10,
          percentage: Math.round((range9to10 / totalShots) * 100),
          color: "bg-green-500",
        },
        {
          range: "8.0 - 8.9",
          count: range8to9,
          percentage: Math.round((range8to9 / totalShots) * 100),
          color: "bg-orange-500",
        },
        {
          range: "7.0 - 7.9",
          count: range7to8,
          percentage: Math.round((range7to8 / totalShots) * 100),
          color: "bg-yellow-500",
        },
        {
          range: "Below 7.0",
          count: below7,
          percentage: Math.round((below7 / totalShots) * 100),
          color: "bg-red-500",
        },
      ] : []

      setScoreDistribution(distribution)
      setHasData(totalShots > 0)
      setStats({
        totalSessions: combinedSessionCount,
        totalShots,
        averageScore: combinedSessionCount > 0 ? totalScoreSum / combinedSessionCount : 0,
        bestScore: bestSessionScore,
        bestSingleShot,
        rifleShots,
        pistolShots,
      })
    }

    void initialize()

    return () => {
      cancelled = true
    }
  }, [router])

  // Calculate pie chart segments
  const riflePercentage = stats.totalShots > 0 ? (stats.rifleShots / stats.totalShots) * 100 : 0
  const pistolPercentage = stats.totalShots > 0 ? (stats.pistolShots / stats.totalShots) * 100 : 0

  const handleSendWrapEmail = async () => {
    const emailToUse = emailEditing ? editingEmail : userEmail
    
    if (!emailToUse) {
      toast({
        title: "Error",
        description: "Email is required to send a wrap report.",
        variant: "destructive",
      })
      return
    }

    if (stats.totalSessions === 0) {
      toast({
        title: "No Data",
        description: "Please complete some sessions before sending a wrap.",
        variant: "destructive",
      })
      return
    }

    setIsSendingEmail(true)
    try {
      // Fetch latest wrapped image
      let imageData = null
      try {
        const imageResponse = await fetch('/latest_image')
        if (imageResponse.ok) {
          const blob = await imageResponse.blob()
          imageData = await new Promise<string>((resolve) => {
            const reader = new FileReader()
            reader.onloadend = () => resolve((reader.result as string).split(',')[1])
            reader.readAsDataURL(blob)
          })
        }
      } catch (error) {
        console.log("Could not fetch latest image:", error)
      }

      const summary = `You've completed ${stats.totalSessions} session(s) with ${stats.totalShots} total shots. Your average session score is ${stats.averageScore.toFixed(2)} points, with a best session score of ${stats.bestScore.toFixed(2)}. Keep up the great practice!`

      await sendEmailWithWrap({
        username,
        email: emailToUse,
        summary,
        stats: {
          totalSessions: stats.totalSessions,
          totalShots: stats.totalShots,
          averageScore: stats.averageScore,
          bestScore: stats.bestScore,
        },
        date: new Date().toLocaleDateString(),
        imageData: imageData || undefined,
      })

      toast({
        title: "Success",
        description: `Wrap report sent to ${emailToUse}`,
      })
      
      // Update userEmail if email was edited
      if (emailEditing && editingEmail !== userEmail) {
        setUserEmail(editingEmail)
      }
      setEmailEditing(false)
    } catch (error) {
      console.error("Email send error:", error)
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to send email",
        variant: "destructive",
      })
    } finally {
      setIsSendingEmail(false)
    }
  }

  return (
    <div className="flex h-screen bg-background">
      <Sidebar activeSection="analytics" />

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="h-auto bg-card border-b border-border px-6 py-3 flex items-center justify-between gap-4">
          <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <Activity className={`w-6 h-6 ${
              accent === "orange" ? "text-orange-500" : 
              accent === "green" ? "text-green-500" : 
              "text-blue-500"
            }`} />
            ANALYTICS
          </h1>
          
          <div className="flex items-center gap-3">
            {/* Email Input */}
            <div className="flex items-center gap-2">
              <div className="relative w-64">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  value={emailEditing ? editingEmail : userEmail}
                  onChange={(e) => emailEditing && setEditingEmail(e.target.value)}
                  disabled={!emailEditing}
                  className="pl-10 bg-secondary border-border text-foreground disabled:opacity-70 text-sm h-9"
                  placeholder="Email"
                  suppressHydrationWarning
                />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => emailEditing ? setEmailEditing(false) : setEmailEditing(true)}
                className={`${
                  accent === "orange" ? "border-orange-500/50 text-orange-500 hover:bg-orange-500/10" :
                  accent === "green" ? "border-green-500/50 text-green-500 hover:bg-green-500/10" :
                  "border-blue-500/50 text-blue-500 hover:bg-blue-500/10"
                } h-9`}
              >
                {emailEditing ? (
                  <>
                    <Save className="w-4 h-4" />
                  </>
                ) : (
                  <>
                    <Edit2 className="w-4 h-4" />
                  </>
                )}
              </Button>
            </div>

            <Button
              onClick={handleSendWrapEmail}
              disabled={isSendingEmail || stats.totalSessions === 0}
              className={`${
                accent === "orange" 
                  ? "bg-orange-500 hover:bg-orange-600" 
                  : accent === "green"
                  ? "bg-green-500 hover:bg-green-600"
                  : "bg-blue-500 hover:bg-blue-600"
              } text-white text-sm h-9`}
            >
              {isSendingEmail ? (
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Send className="w-4 h-4 mr-2" />
              )}
              Send Wrap Email
            </Button>
          </div>
        </div>

        <div className="flex-1 p-6 overflow-auto">
          {/* Stats Grid - Always show */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-muted-foreground text-sm flex items-center gap-2">
                  <BarChart3 className="w-4 h-4" />
                  Total Sessions
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-foreground">{stats.totalSessions}</div>
                <div className="flex items-center gap-1 text-green-400 text-xs mt-1">
                  <TrendingUp className="w-3 h-3" />
                  All time
                </div>
              </CardContent>
            </Card>

            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-muted-foreground text-sm flex items-center gap-2">
                  <Activity className="w-4 h-4" />
                  Total Shots
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-foreground">{stats.totalShots}</div>
                <div className="text-muted-foreground text-xs mt-1">
                  Rifle: {stats.rifleShots} | Pistol: {stats.pistolShots}
                </div>
              </CardContent>
            </Card>

            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-muted-foreground text-sm flex items-center gap-2">
                  <PieChart className="w-4 h-4" />
                  Average Score
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-orange-500">
                  {stats.averageScore.toFixed(1)}
                </div>
                <div className="flex items-center gap-1 text-muted-foreground text-xs mt-1">
                  Per session
                </div>
              </CardContent>
            </Card>

            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-muted-foreground text-sm flex items-center gap-2">
                  <TrendingUp className="w-4 h-4" />
                  Best Score
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-green-400">
                  {stats.bestScore.toFixed(1)}
                </div>
                <div className="flex items-center gap-1 text-green-400 text-xs mt-1">
                  Personal best
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Charts - Only show when there's data */}
          {hasData ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle className="text-foreground flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-orange-500" />
                    Score Distribution
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {scoreDistribution.map((item, index) => (
                      <div key={index}>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-muted-foreground">{item.range}</span>
                          <span className="text-foreground">
                            {item.count} shots ({item.percentage}%)
                          </span>
                        </div>
                        <div className="h-2 bg-secondary rounded-full overflow-hidden">
                          <div
                            className={`h-full ${item.color} rounded-full transition-all duration-500`}
                            style={{ width: `${item.percentage}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 pt-4 border-t border-border">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Best Single Shot</span>
                      <span className="text-green-400 font-bold">{stats.bestSingleShot.toFixed(1)}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle className="text-foreground flex items-center gap-2">
                    <PieChart className="w-5 h-5 text-orange-500" />
                    Mode Breakdown
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-center py-8">
                    <div className="relative">
                      {/* Pie chart visualization with conic gradient */}
                      <div 
                        className="w-40 h-40 rounded-full flex items-center justify-center"
                        style={{
                          background: stats.totalShots > 0 
                            ? `conic-gradient(
                                #f97316 0% ${riflePercentage}%, 
                                #3b82f6 ${riflePercentage}% 100%
                              )`
                            : '#374151'
                        }}
                      >
                        <div className="w-28 h-28 rounded-full bg-card flex items-center justify-center">
                          <div className="text-center">
                            <div className="text-2xl font-bold text-foreground">{stats.totalShots}</div>
                            <div className="text-muted-foreground text-sm">Total Shots</div>
                          </div>
                        </div>
                      </div>
                      <div className="absolute -right-20 -top-4 text-sm">
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 bg-orange-500 rounded-full" />
                          <span className="text-muted-foreground">
                            Rifle ({stats.rifleShots}) - {riflePercentage.toFixed(0)}%
                          </span>
                        </div>
                      </div>
                      <div className="absolute -right-20 -bottom-4 text-sm">
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 bg-blue-500 rounded-full" />
                          <span className="text-muted-foreground">
                            Pistol ({stats.pistolShots}) - {pistolPercentage.toFixed(0)}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          ) : (
            /* No data message - Only show when no shots recorded */
            <div className="text-center py-12 text-muted-foreground">
              <Activity className="w-16 h-16 mx-auto mb-4 opacity-50" />
              <p className="text-lg">No analytics data yet</p>
              <p className="text-sm mt-2">Start shooting to see your statistics</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
