"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useRouter } from "next/navigation"
import { io, Socket } from "socket.io-client"
import {
  Target,
  Settings,
  RotateCcw,
  Power,
  Send,
  Clock,
  RefreshCw,
  ChevronRight,
  Crosshair,
  Activity,
  History,
  User,
  LogOut,
  Zap,
  Menu,
  Sun,
  Moon,
  Palette,
  ZoomIn,
  ZoomOut,
  Move,
  Mail,
  Edit2,
  Save,
} from "lucide-react"
import { useTheme } from "next-themes"
import { useAccent } from "@/components/accent-provider"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  getLiveScore, 
  resetScore, 
  nextTarget, 
  setRifleMode, 
  setPistolMode,
  rebootDevice,
  shutdownApp,
  checkConnection,
  selectDevice,
  selectDeviceByIp,
  sendEmailWithScore,
  getCurrentUser,
  API_BASE,
  SOCKET_BASE,
  clearShotSession,
  logout,
  type ScoreData,
  type Shot
} from "@/lib/api"
import { calculateShotDirection, getDirectionColor } from "@/lib/shot-direction"
import { 
  startNewSession, 
  updateCurrentSession, 
  saveCurrentSession,
  getCurrentSession,
  saveSeriesToHistory,
  clearCurrentSession,
} from "@/lib/session-store"
import { isCustomDevice, CUSTOM_IP_ID } from "@/lib/device-ips"
import { hasActiveSubscription } from "@/lib/subscription"
import SettingsModal from "./settings-modal"
import TargetOverlay from "@/components/target-overlay"
import { useToast } from "@/hooks/use-toast"

export default function DashboardPage() {
  const AUTO_NEXT_BUFFER_MS = 2500
  const SHOTS_PER_SERIES = 10
  const router = useRouter()
  const { toast } = useToast()
  const { theme, setTheme } = useTheme()
  const { accent, cycleAccent } = useAccent()
  const [mounted, setMounted] = useState(false)
  
  // State
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [activeSection, setActiveSection] = useState("dashboard")
  const [shootingMode, setShootingMode] = useState<"rifle" | "pistol">("rifle")
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [currentTime, setCurrentTime] = useState(new Date())
  
  // Score state
  const [totalScore, setTotalScore] = useState<number>(0)
  const [shots, setShots] = useState<Shot[]>([])
  const [imageUrl, setImageUrl] = useState<string>("")
  const [targetSeq, setTargetSeq] = useState<number>(1)
  const [seriesShots, setSeriesShots] = useState<Record<string, Shot[]>>({})
  const [seriesTotals, setSeriesTotals] = useState<Record<string, number>>({})
  const [currentSeries, setCurrentSeries] = useState<number>(1)
  const [selectedSeriesKey, setSelectedSeriesKey] = useState<string | null>(null)
  const [sessionMode, setSessionMode] = useState<"tournament" | "training" | "free_training">("training")
  const [trainingShotLimit, setTrainingShotLimit] = useState<number>(10)

  // Username
  const [username, setUsername] = useState<string>("")
  const [userEmail, setUserEmail] = useState<string>("")
  const [emailEditing, setEmailEditing] = useState(false)
  const [editingEmail, setEditingEmail] = useState<string>("")
  const [isSendingEmail, setIsSendingEmail] = useState(false)
  const [deviceIP, setDeviceIP] = useState<string>("")
  
  // Display zoom & pan state
  const [displayZoom, setDisplayZoom] = useState(1)
  const [panX, setPanX] = useState(0)
  const [panY, setPanY] = useState(0)
  const [hoveredShotId, setHoveredShotId] = useState<number | null>(null)

  // Image ref for email capture
  const imageRef = useRef<HTMLImageElement>(null)
  const shotsContainerRef = useRef<HTMLDivElement>(null)
  const previousShotCountRef = useRef(0)
  const autoNextTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const autoNextPendingRef = useRef(false)
  const shotsAtTargetStartRef = useRef(0)

  // Dynamic accent color classes
  const accentText = accent === "orange" ? "text-orange-500" : accent === "green" ? "text-green-500" : "text-blue-500"
  const accentBg = accent === "orange" ? "bg-orange-500" : accent === "green" ? "bg-green-500" : "bg-blue-500"
  const accentBorder = accent === "orange" ? "border-orange-500/50" : accent === "green" ? "border-green-500/50" : "border-blue-500/50"
  const accentShadow = accent === "orange" ? "shadow-orange-500/20" : accent === "green" ? "shadow-green-500/20" : "shadow-blue-500/20"
  const accentHoverText = accent === "orange" ? "hover:text-orange-500" : accent === "green" ? "hover:text-green-500" : "hover:text-blue-500"
  const accentHoverBg = accent === "orange" ? "hover:bg-orange-500" : accent === "green" ? "hover:bg-green-500" : "hover:bg-blue-500"
  const accentGradient = accent === "orange" 
    ? "bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700" 
    : accent === "green" 
    ? "bg-gradient-to-r from-green-500 to-green-600 hover:from-green-600 hover:to-green-700" 
    : "bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700"
  const accentTextGradient = accent === "orange"
    ? "bg-gradient-to-r from-orange-400 to-orange-600 bg-clip-text text-transparent"
    : accent === "green"
    ? "bg-gradient-to-r from-green-400 to-green-600 bg-clip-text text-transparent"
    : "bg-gradient-to-r from-blue-400 to-blue-600 bg-clip-text text-transparent"
  const accentBgHover = accent === "orange" ? "bg-orange-500 hover:bg-orange-600" : accent === "green" ? "bg-green-500 hover:bg-green-600" : "bg-blue-500 hover:bg-blue-600"
  const accentBorderHover = accent === "orange" 
    ? "border-orange-500/50 text-orange-500 hover:bg-orange-500 hover:text-white hover:border-orange-500" 
    : accent === "green" 
    ? "border-green-500/50 text-green-500 hover:bg-green-500 hover:text-white hover:border-green-500" 
    : "border-blue-500/50 text-blue-500 hover:bg-blue-500 hover:text-white hover:border-blue-500"
  const accentHoverLight = accent === "orange" ? "hover:bg-orange-500/10" : accent === "green" ? "hover:bg-green-500/10" : "hover:bg-blue-500/10"
  const accentBorderSolid = accent === "orange" ? "border-orange-500" : accent === "green" ? "border-green-500" : "border-blue-500"

  // Handle hydration for theme
  useEffect(() => {
    setMounted(true)
  }, [])

  // Initialize
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
          localStorage.removeItem("lakshya_logged_in")
          localStorage.removeItem("lakshya_username")
          router.push("/login")
        }
        return
      }

      if (!hasActiveSubscription(currentUser)) {
        router.push("/subscription")
        return
      }

      if (cancelled) {
        return
      }

      localStorage.setItem("lakshya_username", currentUser.username)
      setUsername(currentUser.username)
      setUserEmail(currentUser.email)
      setEditingEmail(currentUser.email)

      const savedDeviceId = localStorage.getItem("lakshya_device_id")
      const savedDeviceIp = localStorage.getItem("lakshya_device_ip")
      if (savedDeviceIp) {
        setDeviceIP(savedDeviceIp)
      }

      if (savedDeviceId) {
        let devicePromise: Promise<Response>
        if (isCustomDevice(savedDeviceId)) {
          devicePromise = savedDeviceIp ? selectDeviceByIp(savedDeviceIp) : Promise.reject(new Error("No IP saved"))
        } else {
          devicePromise = selectDevice(savedDeviceId)
        }

        devicePromise
          .then(async (response) => {
            if (cancelled) {
              return
            }

            if (response.ok) {
              const data = await response.json()
              console.log("âœ… Device synced with Flask:", data)
              setDeviceIP(data.selected_ip)
              toast({
                title: "Device Connected",
                description: `Connected to ${data.selected_ip}`,
              })
            } else {
              console.error("âŒ Failed to select device in Flask")
              toast({
                title: "Connection Warning",
                description: "Could not set device in backend. API calls may fail.",
                variant: "destructive",
              })
            }
          })
          .catch(err => {
            if (cancelled) {
              return
            }

            console.error("âŒ Could not connect to Flask:", err)
            toast({
              title: "Backend Not Running",
              description: "Flask server may not be running. Start it first.",
              variant: "destructive",
            })
          })
      }

      const savedMode = localStorage.getItem("shootingMode") as "rifle" | "pistol"
      if (savedMode) {
        setShootingMode(savedMode)
      }

      const savedSessionMode = localStorage.getItem("lakshya_training_session_mode")
      if (savedSessionMode === "training" || savedSessionMode === "tournament" || savedSessionMode === "free_training") {
        setSessionMode(savedSessionMode)
      }
      const savedShotLimit = Number.parseInt(localStorage.getItem("lakshya_training_shot_limit") || "", 10)
      if (Number.isInteger(savedShotLimit) && savedShotLimit >= 1 && savedShotLimit <= 10) {
        setTrainingShotLimit(savedShotLimit)
      }

      const shouldStartClean = localStorage.getItem("lakshya_start_clean") === "true"
      if (shouldStartClean) {
        try {
          const response = await clearShotSession()
          if (!response.ok) {
            console.error("Failed to clear server-side shot session after login")
          }
        } catch (error) {
          console.error("Could not clear server-side shot session:", error)
        }

        clearCurrentSession()
        startNewSession(savedMode || "rifle")
        localStorage.removeItem("lakshya_start_clean")
        setShots([])
        setTotalScore(0)
        previousShotCountRef.current = 0
        setSeriesShots({})
        setSeriesTotals({})
        setCurrentSeries(1)
        setSelectedSeriesKey(null)
        shotsAtTargetStartRef.current = 0
      } else {
        const current = getCurrentSession()
        if (!current) {
          startNewSession(savedMode || "rifle")
        } else {
          setShots(current.shots)
          setTotalScore(current.totalScore)
          previousShotCountRef.current = current.shots.length
          const grouped = groupShotsBySeries(current.shots)
          setSeriesShots(grouped)
          setSeriesTotals(buildSeriesTotals(grouped))
          const lastSeries = sortSeriesKeys(Object.keys(grouped)).at(-1)
          setCurrentSeries(lastSeries ? getSeriesNumberFromKey(lastSeries) : 1)
        }
      }

      checkConnectionStatus()
    }

    void initialize()

    const timer = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [router, toast])

  // Socket.IO connection for auto-update on vibration detection
  const socketRef = useRef<Socket | null>(null)
  const handleUpdateScoreRef = useRef<(() => Promise<void>) | null>(null)

  useEffect(() => {
    // Connect to Flask Socket.IO server
    const socket = io(SOCKET_BASE, {
      transports: ['websocket', 'polling'],
      withCredentials: true,
    })

    socketRef.current = socket

    socket.on('connect', () => {
      console.log('ðŸ”Œ Connected to Flask Socket.IO')
      toast({
        title: "Socket Connected",
        description: "Live shot detection enabled",
      })
    })

    socket.on('disconnect', () => {
      console.log('âŒ Disconnected from Flask Socket.IO')
    })

    // Listen for shot detection signal from Pi vibration
    socket.on('shot_ui_signal', (data: { event: string; ts: number }) => {
      console.log('ðŸŽ¯ Shot detected via vibration:', data)
      toast({
        title: "Shot Detected!",
        description: "Auto-updating score...",
      })
      // Trigger the same update as clicking the button
      if (handleUpdateScoreRef.current) {
        handleUpdateScoreRef.current()
      }
    })

    return () => {
      socket.disconnect()
    }
  }, [toast])

  const checkConnectionStatus = async () => {
    const connected = await checkConnection()
    setIsConnected(connected)
  }

  const clearAutoNextTimer = useCallback(() => {
    if (autoNextTimeoutRef.current) {
      clearTimeout(autoNextTimeoutRef.current)
      autoNextTimeoutRef.current = null
    }
    autoNextPendingRef.current = false
  }, [])

  const triggerAutoNextTarget = useCallback(async () => {
    try {
      const result = await nextTarget()
      if (result.status === "ok") {
        shotsAtTargetStartRef.current = shots.length
        setTargetSeq((prev) => prev + 1)
        toast({
          title: "Auto Next Target",
          description: "Advanced to next target automatically",
        })
      }
    } catch (error) {
      console.error("Auto next target error:", error)
    }
  }, [toast, shots.length])

  const scheduleAutoNextTarget = useCallback(() => {
    if (autoNextPendingRef.current) {
      return
    }

    autoNextPendingRef.current = true
    toast({
      title: "Auto Next Queued",
      description: `Showing scores, next target in ${AUTO_NEXT_BUFFER_MS / 1000}s`,
    })

    autoNextTimeoutRef.current = setTimeout(async () => {
      autoNextTimeoutRef.current = null
      autoNextPendingRef.current = false
      await triggerAutoNextTarget()
    }, AUTO_NEXT_BUFFER_MS)
  }, [toast, triggerAutoNextTarget])

  useEffect(() => {
    return () => {
      if (autoNextTimeoutRef.current) {
        clearTimeout(autoNextTimeoutRef.current)
      }
    }
  }, [])

  const handleDisplayZoomIn = () => {
    const newZoom = Math.min(displayZoom + 0.5, 4)
    setDisplayZoom(newZoom)
  }

  const handleDisplayZoomOut = () => {
    const newZoom = Math.max(displayZoom - 0.5, 1)
    setDisplayZoom(newZoom)
    if (newZoom === 1) {
      setPanX(0)
      setPanY(0)
    }
  }

  const handlePan = (direction: 'up' | 'down' | 'left' | 'right') => {
    const step = 30 / displayZoom
    const maxPan = (displayZoom - 1) * 100
    
    switch (direction) {
      case 'up':
        setPanY(Math.min(panY + step, maxPan))
        break
      case 'down':
        setPanY(Math.max(panY - step, -maxPan))
        break
      case 'left':
        setPanX(Math.min(panX + step, maxPan))
        break
      case 'right':
        setPanX(Math.max(panX - step, -maxPan))
        break
    }
  }

  const handleResetZoom = () => {
    setDisplayZoom(1)
    setPanX(0)
    setPanY(0)
  }

  const getSeriesNumberFromKey = (key: string): number => {
    const match = key.match(/\d+/)
    return match ? Number.parseInt(match[0], 10) : 0
  }

  const sortSeriesKeys = (keys: string[]) => {
    return [...keys].sort((a, b) => getSeriesNumberFromKey(a) - getSeriesNumberFromKey(b))
  }

  const groupShotsBySeries = (allShots: Shot[]) => {
    return allShots.reduce<Record<string, Shot[]>>((acc, shot, index) => {
      const key = `Series ${Math.floor(index / SHOTS_PER_SERIES) + 1}`
      if (!acc[key]) {
        acc[key] = []
      }
      acc[key].push(shot)
      return acc
    }, {})
  }

  const normalizeShots = (rawShots: unknown[]): Shot[] => {
    return rawShots.filter((item): item is Shot => {
      if (!item || typeof item !== "object") return false
      const shot = item as Partial<Shot>
      return (
        typeof shot.x === "number" &&
        typeof shot.y === "number" &&
        typeof shot.score === "number" &&
        Number.isFinite(shot.x) &&
        Number.isFinite(shot.y) &&
        Number.isFinite(shot.score)
      )
    })
  }

  const buildShotFingerprint = (shot: Shot) => {
    const idPart = typeof shot.id === "number" ? shot.id : "na"
    const tsPart = typeof shot.ts === "number" ? shot.ts : "na"
    return `${idPart}:${tsPart}:${shot.x}:${shot.y}:${shot.score}`
  }

  const SHOT_XY_BUFFER_PX = 5

  const isWithinShotBuffer = (a: Shot, b: Shot) => {
    return Math.abs(a.x - b.x) <= SHOT_XY_BUFFER_PX && Math.abs(a.y - b.y) <= SHOT_XY_BUFFER_PX
  }

  const mergeShotsPreserveOrder = (existingShots: Shot[], incomingShots: Shot[]) => {
    const safeExisting = normalizeShots(existingShots as unknown[])
    const safeIncoming = normalizeShots(incomingShots as unknown[])
    const seen = new Set(safeExisting.map(buildShotFingerprint))
    const merged = [...safeExisting]
    for (const shot of safeIncoming) {
      const key = buildShotFingerprint(shot)
      const nearDuplicate = merged.some((existingShot) => isWithinShotBuffer(existingShot, shot))
      if (!seen.has(key) && !nearDuplicate) {
        seen.add(key)
        merged.push(shot)
      }
    }
    return merged
  }

  const buildSeriesTotals = (grouped: Record<string, Shot[]>) => {
    return Object.entries(grouped).reduce<Record<string, number>>((acc, [key, seriesShotList]) => {
      acc[key] = seriesShotList.reduce((sum, shot) => sum + (shot.score || 0), 0)
      return acc
    }, {})
  }

  useEffect(() => {
    const keys = sortSeriesKeys(Object.keys(seriesShots))
    if (keys.length === 0) {
      setSelectedSeriesKey(null)
      return
    }

    if (selectedSeriesKey && keys.includes(selectedSeriesKey)) {
      return
    }

    const preferredKey = `Series ${currentSeries}`
    setSelectedSeriesKey(keys.includes(preferredKey) ? preferredKey : keys[keys.length - 1])
  }, [seriesShots, currentSeries, selectedSeriesKey])

  useEffect(() => {
    if (shotsContainerRef.current) {
      shotsContainerRef.current.scrollTop = shotsContainerRef.current.scrollHeight
    }
  }, [selectedSeriesKey, shots.length])

  // Update score
  const handleUpdateScore = useCallback(async () => {
  const shotLimit = sessionMode === "tournament" ? 1 : sessionMode === "free_training" ? Number.POSITIVE_INFINITY : trainingShotLimit

  setIsLoading(true)
  try {
    const data: ScoreData = await getLiveScore(1.0)

    if (data.image_url) {
      setImageUrl(`${API_BASE}${data.image_url}`)
    }

    let apiShotData: Shot[] = []
    if (data.series) {
      apiShotData = sortSeriesKeys(Object.keys(data.series)).flatMap((seriesKey) =>
        (data.series?.[seriesKey] || []).map((shot) => ({
          ...shot,
          series: shot.series || seriesKey,
        }))
      )
    } else {
      apiShotData = data.stored_shots || data.scored_shots || []
    }
    apiShotData = normalizeShots(apiShotData as unknown[])

    // Some backends reset shot list on target change. Preserve accumulated local shots.
    const backendLooksCumulative = apiShotData.length >= shots.length
    const safePrefixCount = Math.min(shotsAtTargetStartRef.current, shots.length)
    const historicalShots = shots.slice(0, safePrefixCount)
    let shotData = backendLooksCumulative ? apiShotData : [...historicalShots, ...apiShotData]

    shotData = mergeShotsPreserveOrder(shots, shotData)
    const score = shotData.reduce((sum, shot) => sum + (shot.score || 0), 0)

    const groupedSeries = groupShotsBySeries(shotData)
    const totalsBySeries = buildSeriesTotals(groupedSeries)
    setSeriesShots(groupedSeries)
    setSeriesTotals(totalsBySeries)
    setCurrentSeries(Math.max(1, Math.ceil(shotData.length / SHOTS_PER_SERIES)))

    // ðŸ”¥ Apply to state (outside if/else)
    setShots(shotData)
    setTotalScore(score)
    const hasNewShot = shotData.length > previousShotCountRef.current
    previousShotCountRef.current = shotData.length
    const currentTargetShotCount = Math.max(0, shotData.length - shotsAtTargetStartRef.current)

    if (data.target_seq) {
      setTargetSeq(data.target_seq)
    }

    // Update session storage
    updateCurrentSession(shotData, score)

    setIsConnected(true)

    toast({
      title: "Score Updated",
      description: `${shotData.length} shots detected`,
    })

    if (hasNewShot && currentTargetShotCount >= shotLimit) {
      scheduleAutoNextTarget()
    }

  } catch (error) {
    console.error("Score update error:", error)
    setIsConnected(false)
    toast({
      title: "Error",
      description: error instanceof Error ? error.message : "Failed to update score",
      variant: "destructive",
    })
  } finally {
    setIsLoading(false)
  }
}, [toast, scheduleAutoNextTarget, sessionMode, shots, trainingShotLimit])


  // Keep the ref updated so socket can call handleUpdateScore
  useEffect(() => {
    handleUpdateScoreRef.current = handleUpdateScore
  }, [handleUpdateScore])

  const saveActiveSeriesHistory = async () => {
    const currentSeriesKey = `Series ${currentSeries}`
    const currentSeriesShotsList = seriesShots[currentSeriesKey] || []

    if (currentSeriesShotsList.length === 0) {
      return false
    }

    const staticHistoryImage =
      shootingMode === "rifle" ? "/history-rifle-target.svg" : "/history-pistol-target.svg"

    saveSeriesToHistory(currentSeriesShotsList, shootingMode, staticHistoryImage, sessionMode)
    console.log(`[History] Saved series ${currentSeries} with ${currentSeriesShotsList.length} shots (${sessionMode} mode, static target image)`)
    return true
  }

  // Next target
  const handleNextTarget = async () => {
    setIsLoading(true)
    try {
      clearAutoNextTimer()
      
      const result = await nextTarget()
      
      if (result.status === "ok") {
        shotsAtTargetStartRef.current = shots.length
        setTargetSeq(prev => prev + 1)
        
        toast({
          title: "New Target",
          description: "Target changed successfully",
        })
      } else {
        toast({
          title: "Warning",
          description: result.message || "Target not ready",
          variant: "destructive",
        })
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to change target",
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  // Reset
  const handleReset = async () => {
    try {
      clearAutoNextTimer()
      await saveActiveSeriesHistory()
      await resetScore()
      setShots([])
      setTotalScore(0)
      previousShotCountRef.current = 0
      setSeriesShots({})
      setSeriesTotals({})
      setCurrentSeries(1)
      setSelectedSeriesKey(null)
      shotsAtTargetStartRef.current = 0
      startNewSession(shootingMode)
      
      toast({
        title: "Reset Complete",
        description: "All scores cleared",
      })
    } catch (error) {
      toast({
        title: "Error",
        description: "Reset failed",
        variant: "destructive",
      })
    }
  }

  // Mode switching
  const handleModeChange = async (mode: "rifle" | "pistol") => {
    try {
      await saveActiveSeriesHistory()
      if (mode === "rifle") {
        await setRifleMode()
      } else {
        await setPistolMode()
      }
      clearAutoNextTimer()
      await resetScore()
      setShootingMode(mode)
      localStorage.setItem("shootingMode", mode)
      setShots([])
      setTotalScore(0)
      previousShotCountRef.current = 0
      setSeriesShots({})
      setSeriesTotals({})
      setCurrentSeries(1)
      setSelectedSeriesKey(null)
      shotsAtTargetStartRef.current = 0
      startNewSession(mode)
      
      toast({
        title: "Mode Changed",
        description: `${mode.charAt(0).toUpperCase() + mode.slice(1)} mode activated and scores reset`,
      })
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to change mode",
        variant: "destructive",
      })
    }
  }

  // System controls
  const handleReboot = async () => {
    if (!confirm("Reboot the target device?")) return
    try {
      await rebootDevice()
      toast({
        title: "Rebooting",
        description: "Device is rebooting...",
      })
    } catch (error) {
      toast({
        title: "Error",
        description: "Reboot failed",
        variant: "destructive",
      })
    }
  }

  const handlePowerOff = async () => {
    if (!confirm("Shutdown the application?")) return
    await saveActiveSeriesHistory()
    saveCurrentSession()
    try {
      await shutdownApp()
      toast({
        title: "Shutting Down",
        description: "Application is closing...",
      })
    } catch (error) {
      // Expected to fail as server shuts down
    }
  }

  // Note: Use handleSendScoreEmail instead for new email functionality

  const handleSendScoreEmail = async () => {
    if (!userEmail) {
      toast({
        title: "Error",
        description: "User email not configured. Please log in again.",
        variant: "destructive",
      })
      return
    }

    if (shots.length === 0) {
      toast({
        title: "No Data",
        description: "Please record some shots before sending.",
        variant: "destructive",
      })
      return
    }

    setIsSendingEmail(true)
    try {
      const averageScore = shots.length > 0
        ? shots.reduce((sum, shot) => sum + shot.score, 0) / shots.length
        : 0

      // Capture target image as base64
      let imageBase64: string | undefined = undefined
      if (imageRef.current) {
        const canvas = document.createElement('canvas')
        canvas.width = imageRef.current.width
        canvas.height = imageRef.current.height
        const ctx = canvas.getContext('2d')
        if (ctx) {
          ctx.drawImage(imageRef.current, 0, 0)
          imageBase64 = canvas.toDataURL('image/png').split(',')[1] // Remove data:image/png;base64, prefix
        }
      }

      await sendEmailWithScore({
        username,
        email: userEmail,
        totalScore,
        shots,
        mode: shootingMode,
        date: new Date().toLocaleDateString(),
        averageScore,
        imageBase64,
        accent: accent as 'orange' | 'green' | 'blue',
      })

      toast({
        title: "Success",
        description: `Score report sent to ${userEmail}`,
      })
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

  const handleSignout = async () => {
    await saveActiveSeriesHistory()
    saveCurrentSession()
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

  const handleNavigation = (section: string) => {
    setActiveSection(section)
    if (section !== "dashboard") {
      router.push(`/${section}`)
    }
  }

  const sortedSeriesKeys = sortSeriesKeys(Object.keys(seriesShots))
  const selectedSeriesIndex = selectedSeriesKey ? sortedSeriesKeys.indexOf(selectedSeriesKey) : -1
  const selectedSeriesShots = selectedSeriesKey ? (seriesShots[selectedSeriesKey] || []) : []

  const handlePreviousSeries = () => {
    if (selectedSeriesIndex > 0) {
      setSelectedSeriesKey(sortedSeriesKeys[selectedSeriesIndex - 1])
    }
  }

  const handleNextSeriesSelect = () => {
    if (selectedSeriesIndex >= 0 && selectedSeriesIndex < sortedSeriesKeys.length - 1) {
      setSelectedSeriesKey(sortedSeriesKeys[selectedSeriesIndex + 1])
    }
  }

  return (
    <div className="flex h-screen bg-background flex-col md:flex-row">
      {/* Sidebar */}
      <div
        className={`${sidebarCollapsed ? "md:w-20 w-full md:h-screen" : "md:w-64 w-full md:h-screen"} bg-card border-r md:border-r border-b md:border-b-0 border-border transition-all duration-300 flex flex-row md:flex-col`}
      >
        <div className="p-3 md:p-4 flex-1 md:flex-none">
          {/* Header */}
          <div className="flex items-center justify-between mb-4 md:mb-8">
            <div className={`${sidebarCollapsed ? "hidden" : "block"}`}>
              <h1 className={`${accentText} font-bold text-lg md:text-xl tracking-wider`}>LAKSHYA</h1>
              <p className="text-muted-foreground text-xs">TARGET SCORING SYSTEM</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className={`text-muted-foreground ${accentHoverText} hover:bg-accent hidden md:flex`}
              suppressHydrationWarning
            >
              {sidebarCollapsed ? (
                <Menu className="w-5 h-5" />
              ) : (
                <ChevronRight className="w-5 h-5 rotate-180" />
              )}
            </Button>
          </div>

          {/* Navigation */}
          <nav className="space-y-1 md:space-y-2 flex md:flex-col gap-1 md:gap-0 overflow-x-auto md:overflow-x-visible">
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
                className={`whitespace-nowrap flex-shrink-0 md:flex-shrink flex items-center ${sidebarCollapsed ? "justify-center" : ""} gap-2 md:gap-3 p-2 md:p-3 rounded-lg transition-all duration-200 ${
                  activeSection === item.id
                    ? `${accentBg} text-white shadow-lg ${accentShadow}`
                    : "text-muted-foreground hover:text-foreground hover:bg-accent"
                }`}
                title={sidebarCollapsed ? item.label : undefined}
                suppressHydrationWarning
              >
                <item.icon className={sidebarCollapsed ? "w-5 h-5 md:w-6 md:h-6" : "w-4 md:w-5 h-4 md:h-5"} />
                {!sidebarCollapsed && <span className="text-xs md:text-sm font-medium">{item.label}</span>}
              </button>
            ))}
          </nav>

          {/* System Status */}
          {!sidebarCollapsed && (
            <div className="hidden md:block mt-8 p-4 bg-accent/50 border border-border rounded-lg">
              <div className="flex items-center gap-2 mb-3">
                <div className={`w-2 h-2 rounded-full animate-pulse ${isConnected ? "bg-green-500" : "bg-red-500"}`} />
                <span className="text-xs text-foreground">
                  {isConnected ? "SYSTEM ONLINE" : "DISCONNECTED"}
                </span>
              </div>
              <div className="text-xs text-muted-foreground space-y-1 font-mono">
                <div>USER: {username.toUpperCase()}</div>
                <div>MODE: {shootingMode.toUpperCase()}</div>
                <div>TARGET: #{targetSeq}</div>
                {deviceIP && <div className={`${accentText} font-semibold`}>IP: {deviceIP}</div>}
              </div>
            </div>
          )}
        </div>

        {/* Signout */}
        <div className="p-3 md:p-4 mt-auto">
          <button
            onClick={handleSignout}
            className={`w-full flex items-center ${sidebarCollapsed ? "justify-center" : ""} gap-2 md:gap-3 p-2 md:p-3 rounded-lg text-muted-foreground hover:text-white hover:bg-red-500 transition-colors`}
            title={sidebarCollapsed ? "SIGNOUT" : undefined}
            suppressHydrationWarning
          >
            <LogOut className={sidebarCollapsed ? "w-5 h-5 md:w-6 md:h-6" : "w-4 md:w-5 h-4 md:h-5"} />
            {!sidebarCollapsed && <span className="text-xs md:text-sm font-medium">SIGNOUT</span>}
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Bar */}
        <div className="bg-card border-b border-border px-2 md:px-4 py-1.5 md:py-2">
          <div className="flex flex-wrap items-center justify-between gap-1.5 md:gap-2">
            {/* Left Section */}
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSettingsOpen(true)}
                className={`${accentBorderHover} transition-colors h-7 md:h-8 text-[11px] px-1.5 md:px-2`}
                suppressHydrationWarning
              >
                <Settings className="w-3 h-3 md:w-3.5 md:h-3.5" />
                <span className="hidden lg:inline ml-1">Settings</span>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleReboot}
                className="border-blue-500/50 text-blue-500 hover:bg-blue-500 hover:text-white hover:border-blue-500 transition-colors h-7 md:h-8 text-[11px] px-1.5 md:px-2"
                suppressHydrationWarning
              >
                <RotateCcw className="w-3 h-3 md:w-3.5 md:h-3.5" />
                <span className="hidden lg:inline ml-1">Reboot</span>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handlePowerOff}
                className="border-red-500/50 text-red-500 hover:bg-red-500 hover:text-white hover:border-red-500 transition-colors h-7 md:h-8 text-[11px] px-1.5 md:px-2"
                suppressHydrationWarning
              >
                <Power className="w-3 h-3 md:w-3.5 md:h-3.5" />
                <span className="hidden lg:inline ml-1">Power Off</span>
              </Button>
            </div>

            {/* Right Section */}
            <div className="flex items-center gap-1">
              {/* Email Input */}
              <div className="flex items-center gap-1">
                <div className="relative w-36 md:w-44">
                  <Mail className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
                  <Input
                    value={emailEditing ? editingEmail : userEmail}
                    onChange={(e) => emailEditing && setEditingEmail(e.target.value)}
                    disabled={!emailEditing}
                    className="pl-7 bg-secondary border-border text-foreground disabled:opacity-70 text-xs h-7 md:h-8"
                    placeholder="Email"
                    suppressHydrationWarning
                  />
                </div>
                <button
                  onClick={() => emailEditing ? setEmailEditing(false) : setEmailEditing(true)}
                  className={`p-1 rounded text-muted-foreground hover:text-white ${
                    accent === "orange" ? "hover:bg-orange-500/20" :
                    accent === "green" ? "hover:bg-green-500/20" :
                    "hover:bg-blue-500/20"
                  } transition-colors h-7 md:h-8 flex items-center justify-center`}
                  title={emailEditing ? "Save" : "Edit"}
                  suppressHydrationWarning
                >
                  {emailEditing ? (
                    <Save className="w-3 h-3 md:w-3.5 md:h-3.5" />
                  ) : (
                    <Edit2 className="w-3 h-3 md:w-3.5 md:h-3.5" />
                  )}
                </button>
              </div>

              {/* Send Score Email Button */}
              <Button
                onClick={handleSendScoreEmail}
                disabled={isSendingEmail || shots.length === 0}
                size="sm"
                className={`${accentGradient} text-white shadow-lg ${accentShadow} text-xs h-7 md:h-8 px-2`}
                title="Send score report via email"
                suppressHydrationWarning
              >
                {isSendingEmail ? (
                  <RefreshCw className="w-3 h-3 md:w-3.5 md:h-3.5 mr-1 animate-spin" />
                ) : (
                  <Send className="w-3 h-3 md:w-3.5 md:h-3.5 mr-1" />
                )}
                <span className="hidden lg:inline">Send Email</span>
              </Button>

              {/* Accent Color Toggle */}
              <Button
                variant="outline"
                size="sm"
                onClick={cycleAccent}
                title={`Accent: ${accent}`}
                className="border-border hover:bg-accent/20 h-7 md:h-8 w-7 md:w-8 p-0"
                suppressHydrationWarning
              >
                {mounted && (
                  <Palette 
                    className={`w-3 h-3 md:w-3.5 md:h-3.5 ${
                      accent === "orange" ? "text-orange-500" : 
                      accent === "green" ? "text-green-500" : 
                      "text-blue-500"
                    }`} 
                  />
                )}
              </Button>
              {/* Theme Toggle */}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                className="border-border text-muted-foreground hover:bg-accent hover:text-foreground h-7 md:h-8 w-7 md:w-8 p-0"
                suppressHydrationWarning
              >
                {mounted && (theme === "dark" ? <Sun className="w-3 h-3 md:w-3.5 md:h-3.5" /> : <Moon className="w-3 h-3 md:w-3.5 md:h-3.5" />)}
              </Button>
            </div>
          </div>
        </div>

        {/* Dashboard Grid */}
        <div className="flex-1 p-4 md:p-6 overflow-auto">
          <div className="grid grid-cols-1 lg:grid-cols-[70%_30%] gap-4 md:gap-6 min-h-full">
            {/* Camera Feed - Center */}
            <div className="flex flex-col gap-4">
              <Card className="flex-1 bg-card border-border overflow-hidden">
                <CardContent className="p-4 h-full flex flex-col">
                  {/* Target Frame - Square Container */}
                  <div className="bg-secondary dark:bg-neutral-950 rounded-xl border-2 border-border overflow-hidden relative flex items-center justify-center mx-auto aspect-square" style={{ width: '640px', height: '640px' }}>
                    {imageUrl ? (
                      <img
                        ref={imageRef}
                        src={imageUrl}
                        alt="Live Feed"
                        crossOrigin="anonymous"
                        className="w-full h-full object-cover transition-transform duration-200"
                        style={{
                          transform: `scale(${displayZoom}) translate(${panX}px, ${panY}px)`,
                          transformOrigin: 'center center'
                        }}
                      />
                    ) : null}
                    {/* Shot Overlay */}
                    {selectedSeriesKey && seriesShots[selectedSeriesKey] && (
                      <TargetOverlay
                        shots={seriesShots[selectedSeriesKey]}
                        hoveredShotId={hoveredShotId}
                        onShotHover={setHoveredShotId}
                        containerSize={640}
                        imageWidth={640}
                        imageHeight={640}
                        zoom={displayZoom}
                        panX={panX}
                        panY={panY}
                      />
                    )}
                    <div className={`absolute top-3 right-3 px-3 py-1 rounded-full border text-xs md:text-sm font-semibold ${
                      accent === "orange" ? "border-orange-500/50 text-orange-500 bg-orange-500/10" :
                      accent === "green" ? "border-green-500/50 text-green-500 bg-green-500/10" :
                      "border-blue-500/50 text-blue-500 bg-blue-500/10"
                    }`}>
                      TARGET #{targetSeq}
                    </div>
                    {!imageUrl && (
                      <div className="text-center">
                        <Target className="w-12 md:w-16 h-12 md:h-16 text-muted-foreground/50 mx-auto" />
                      </div>
                    )}
                  </div>

                  {/* Shooting Mode Toggle */}
                  <div className="flex flex-col sm:flex-row items-center justify-center gap-2 md:gap-3 mt-2">
                    <span className="text-muted-foreground text-sm">Shooting Mode</span>
                    <div className="flex gap-2">
                      <Button
                        variant={shootingMode === "rifle" ? "default" : "outline"}
                        size="sm"
                        onClick={() => handleModeChange("rifle")}
                        className={shootingMode === "rifle" 
                          ? `${accentBgHover} text-white` 
                          : "border-border text-muted-foreground hover:text-foreground hover:bg-accent"
                        }
                        suppressHydrationWarning
                      >
                        Rifle
                      </Button>
                      <Button
                        variant={shootingMode === "pistol" ? "default" : "outline"}
                        size="sm"
                        onClick={() => handleModeChange("pistol")}
                        className={shootingMode === "pistol" 
                          ? `${accentBgHover} text-white` 
                          : "border-border text-muted-foreground hover:text-foreground hover:bg-accent"
                        }
                        suppressHydrationWarning
                      >
                        Pistol
                      </Button>
                    </div>
                  </div>

                  {/* Display Zoom & Pan Controls */}
                  <div className="flex flex-col items-center gap-2 mt-2 pt-2 border-t border-border">
                    <div className="flex items-center gap-2">
                      <Move className="w-4 h-4 text-cyan-500" />
                      <span className="text-muted-foreground text-sm">Display Zoom</span>
                      <span className="text-cyan-500 font-mono text-sm font-bold">{Math.round(displayZoom * 100)}%</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* Zoom Out */}
                      <Button
                        onClick={handleDisplayZoomOut}
                        disabled={displayZoom <= 1}
                        size="sm"
                        variant="outline"
                        className="border-border text-muted-foreground hover:text-foreground hover:bg-accent h-8 w-8 p-0"
                        suppressHydrationWarning
                      >
                        <ZoomOut className="w-4 h-4" />
                      </Button>
                      
                      {/* Pan Controls */}
                      <div className="flex items-center gap-1">
                        <Button
                          onClick={() => handlePan('left')}
                          disabled={displayZoom <= 1}
                          size="sm"
                          variant="outline"
                          className="border-border text-muted-foreground hover:text-foreground hover:bg-accent h-8 w-8 p-0"
                          suppressHydrationWarning
                        >
                          â†
                        </Button>
                        <div className="flex flex-col gap-1">
                          <Button
                            onClick={() => handlePan('up')}
                            disabled={displayZoom <= 1}
                            size="sm"
                            variant="outline"
                            className="border-border text-muted-foreground hover:text-foreground hover:bg-accent h-6 w-8 p-0 text-xs"
                            suppressHydrationWarning
                          >
                            â†‘
                          </Button>
                          <Button
                            onClick={handleResetZoom}
                            size="sm"
                            className="bg-cyan-600 hover:bg-cyan-700 text-white h-6 w-8 p-0"
                            title="Reset Zoom"
                            suppressHydrationWarning
                          >
                            <RotateCcw className="w-3 h-3" />
                          </Button>
                          <Button
                            onClick={() => handlePan('down')}
                            disabled={displayZoom <= 1}
                            size="sm"
                            variant="outline"
                            className="border-border text-muted-foreground hover:text-foreground hover:bg-accent h-6 w-8 p-0 text-xs"
                            suppressHydrationWarning
                          >
                            â†“
                          </Button>
                        </div>
                        <Button
                          onClick={() => handlePan('right')}
                          disabled={displayZoom <= 1}
                          size="sm"
                          variant="outline"
                          className="border-border text-muted-foreground hover:text-foreground hover:bg-accent h-8 w-8 p-0"
                          suppressHydrationWarning
                        >
                          â†’
                        </Button>
                      </div>
                      
                      {/* Zoom In */}
                      <Button
                        onClick={handleDisplayZoomIn}
                        disabled={displayZoom >= 4}
                        size="sm"
                        variant="outline"
                        className="border-border text-muted-foreground hover:text-foreground hover:bg-accent h-8 w-8 p-0"
                        suppressHydrationWarning
                      >
                        <ZoomIn className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Right Panel */}
            <div className="flex flex-col gap-3 min-h-0">
              {/* Total Score Card */}
              <Card className="bg-card border-border">
                <CardHeader className="pb-0">
                  <CardTitle className="text-foreground text-sm tracking-[0.12em] flex items-center gap-2">
                    <Zap className={`w-4 h-4 ${accentText}`} />
                    GRAND TOTAL
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-2 pb-3">
                  <div className={`text-4xl md:text-5xl font-bold text-center py-1 font-mono leading-none ${accentTextGradient}`}>
                    {totalScore.toFixed(1)}
                  </div>
                  <div className="flex items-center justify-center text-xs text-muted-foreground mt-2 mb-1 px-1">
                    <div className="flex items-center gap-2 bg-secondary/50 border border-border rounded-lg px-2 py-1">
                      <Button
                        onClick={handlePreviousSeries}
                        disabled={selectedSeriesIndex <= 0}
                        variant="outline"
                        size="sm"
                        className="h-6 px-2 text-[10px] border-border text-muted-foreground hover:text-foreground hover:bg-accent"
                        suppressHydrationWarning
                      >
                        Prev
                      </Button>
                      <span className="font-semibold text-foreground min-w-[74px] text-center text-xs">
                        {selectedSeriesKey || "-"}
                      </span>
                      <Button
                        onClick={handleNextSeriesSelect}
                        disabled={selectedSeriesIndex < 0 || selectedSeriesIndex >= sortedSeriesKeys.length - 1}
                        variant="outline"
                        size="sm"
                        className="h-6 px-2 text-[10px] border-border text-muted-foreground hover:text-foreground hover:bg-accent"
                        suppressHydrationWarning
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground mb-2 px-1 text-center">
                    {sessionMode === "tournament" ? "Tournament" : sessionMode === "free_training" ? "Free Training" : "Training"} • {sessionMode === "tournament" ? "1 shot" : sessionMode === "free_training" ? "Unlimited shots" : `${trainingShotLimit} shots`}
                  </div>
                  <div className="grid grid-cols-2 gap-2 mt-1">
                    <Button
                      onClick={handleUpdateScore}
                      disabled={isLoading}
                      className={`${accentGradient} text-white shadow-lg ${accentShadow} text-sm min-w-0 h-10`}
                      suppressHydrationWarning
                    >
                      {isLoading ? (
                        <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <RefreshCw className="w-4 h-4 mr-2" />
                      )}
                      UPDATE
                    </Button>
                    <Button
                      onClick={handleNextTarget}
                      disabled={isLoading}
                      variant="outline"
                      className={`${accentBorder} ${accentText} ${accentHoverLight} text-sm min-w-0 h-10`}
                      suppressHydrationWarning
                    >
                      <Target className="w-4 h-4 mr-2" />
                      NEXT
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Recent Shots */}
              <Card className="bg-card border-border overflow-hidden">
                <CardHeader className="pb-0" />
                <CardContent ref={shotsContainerRef} className="overflow-auto max-h-[160px] md:max-h-[220px]">
                  {sortedSeriesKeys.length > 0 ? (
                    <div className="space-y-2">
                      {selectedSeriesKey && (
                        <div key={selectedSeriesKey} className="space-y-2 rounded-lg border border-border/60 p-2">
                          <div className="flex items-center justify-between px-1">
                            <span className="text-xs md:text-sm font-semibold text-foreground">{selectedSeriesKey}</span>
                            <span className={`text-xs md:text-sm font-mono font-bold ${accentText}`}>
                              Sub-total: {(seriesTotals[selectedSeriesKey] ?? 0).toFixed(1)}
                            </span>
                          </div>
                          {selectedSeriesShots.map((shot, index) => {
                            const direction = calculateShotDirection(shot.x, shot.y, 320, 320)
                            const directionColor = getDirectionColor(direction.direction)
                            const isHovered = hoveredShotId === (shot.id || index)
                            return (
                              <div
                                key={`${selectedSeriesKey}-${shot.id || index}`}
                                className={`flex items-center justify-between p-2 md:p-3 rounded-lg border-l-4 ${accentBorderSolid} transition-all ${
                                  isHovered
                                    ? "bg-green-500/20 border-green-500 ring-2 ring-green-500/30"
                                    : "bg-yellow-500/10 hover:bg-yellow-500/20"
                                }`}
                                onMouseEnter={() => setHoveredShotId(shot.id || index)}
                                onMouseLeave={() => setHoveredShotId(null)}
                              >
                                <div className="flex items-center gap-2">
                                  <span className={`text-foreground font-medium text-sm md:text-base ${isHovered ? "text-green-400" : "text-yellow-400"}`}>
                                    Shot {index + 1}
                                  </span>
                                  <span className={`text-lg md:text-xl font-bold ${isHovered ? "text-green-400" : directionColor}`} title={`${direction.direction} (${direction.angle}°)`}>
                                    {direction.arrow}
                                  </span>
                                  <span className={`text-xs font-mono ${isHovered ? "text-green-400" : directionColor}`}>
                                    {direction.direction}
                                  </span>
                                </div>
                                <span className={`font-bold font-mono text-base md:text-lg ${isHovered ? "text-green-400" : "text-yellow-400"}`}>
                                  {shot.score.toFixed(1)}
                                </span>
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-center py-4 md:py-8 text-muted-foreground">
                      <Target className="w-8 md:w-10 h-8 md:h-10 mx-auto mb-2 opacity-50" />
                      <p className="text-sm md:text-base">No shots recorded</p>
                      <p className="text-xs md:text-sm mt-1">Click Update Score to detect shots</p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Reset Button */}
              <Button
                onClick={handleReset}
                variant="outline"
                className="w-full border-red-500/50 text-red-400 hover:bg-red-500/10 hover:border-red-500 text-xs md:text-sm h-8 md:h-9"
                suppressHydrationWarning
              >
                <RotateCcw className="w-3 md:w-4 h-3 md:h-4 mr-2" />
                Reset
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Settings Modal */}
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  )
}


