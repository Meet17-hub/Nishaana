"use client"

import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import {
  History as HistoryIcon,
  Target,
  FlaskConical,
  ChevronDown,
  ChevronUp,
  Calendar,
  Clock,
  Trash2,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { 
  getAllHistory, 
  clearAllHistory, 
  deleteHistoryItem,
  type SeriesHistoryItem 
} from "@/lib/session-store"
import Sidebar from "@/components/sidebar"
import { useAccent } from "@/components/accent-provider"

type TargetAlignment = {
  liveCenterX: number
  liveCenterY: number
  liveOuterRadius: number
  staticCenterX: number
  staticCenterY: number
  staticOuterRadius: number
}

const TARGET_ALIGNMENTS: Record<"rifle" | "pistol", TargetAlignment> = {
  rifle: {
    liveCenterX: 320,
    liveCenterY: 320,
    liveOuterRadius: 320,
    staticCenterX: 320,
    staticCenterY: 312,
    staticOuterRadius: 280,
  },
  pistol: {
    liveCenterX: 320,
    liveCenterY: 320,
    liveOuterRadius: 320,
    staticCenterX: 320,
    staticCenterY: 320,
    staticOuterRadius: 255,
  },
}

const RIFLE_RING_RADII_PX: Record<number, number> = {
  1: 280.0,
  2: 249.23,
  3: 218.46,
  4: 190.69,
  5: 158.92,
  6: 135.15,
  7: 100.38,
  8: 68.62,
  9: 33.85,
  10: 3.08,
}

function getRifleRadiusFromScore(score: number) {
  const clamped = Math.max(0, Math.min(10.9, score))
  const base = Math.floor(clamped)
  const decimal = Math.round((clamped - base) * 10)

  if (base <= 0) {
    return RIFLE_RING_RADII_PX[1]
  }

  if (base >= 10) {
    const outer = RIFLE_RING_RADII_PX[9]
    const inner = RIFLE_RING_RADII_PX[10]
    const t = Math.max(0, Math.min(1, decimal / 9))
    return outer + (inner - outer) * t
  }

  const outer = RIFLE_RING_RADII_PX[base]
  const inner = RIFLE_RING_RADII_PX[base + 1]
  const t = Math.max(0, Math.min(1, decimal / 9))
  return outer + (inner - outer) * t
}

function mapShotToHistoryTarget(shot: SeriesHistoryItem["shots"][number], mode: "rifle" | "pistol") {
  const alignment = TARGET_ALIGNMENTS[mode]
  let mappedX: number
  let mappedY: number

  if (mode === "rifle") {
    const rawDx = shot.dx ?? (shot.x - (shot.center_x ?? alignment.liveCenterX))
    const rawDy = shot.dy ?? ((shot.center_y ?? alignment.liveCenterY) - shot.y)
    const magnitude = Math.hypot(rawDx, rawDy)

    if (magnitude > 0) {
      const ux = rawDx / magnitude
      const uy = rawDy / magnitude
      const radius = getRifleRadiusFromScore(shot.score)
      mappedX = alignment.staticCenterX + ux * radius
      mappedY = alignment.staticCenterY - uy * radius
    } else {
      mappedX = alignment.staticCenterX
      mappedY = alignment.staticCenterY
    }
  } else {
    const liveCenterX = shot.center_x ?? alignment.liveCenterX
    const liveCenterY = shot.center_y ?? alignment.liveCenterY
    const scale = alignment.staticOuterRadius / alignment.liveOuterRadius

    mappedX = alignment.staticCenterX + (shot.x - liveCenterX) * scale
    mappedY = alignment.staticCenterY + (shot.y - liveCenterY) * scale
  }

  return {
    xPercent: (mappedX / 640) * 100,
    yPercent: (mappedY / 640) * 100,
  }
}

function groupHistoryShots(item: SeriesHistoryItem) {
  const groups = new Map<string, SeriesHistoryItem["shots"]>()

  item.shots.forEach((shot, index) => {
    const fallbackLabel = `Series ${Math.floor(index / 10) + 1}`
    const label = shot.series || fallbackLabel
    const existing = groups.get(label) || []
    existing.push(shot)
    groups.set(label, existing)
  })

  return Array.from(groups.entries()).map(([label, shots], index) => ({
    index,
    label,
    shots,
    total: shots.reduce((sum, shot) => sum + shot.score, 0),
  }))
}

function formatDayHeader(dateStr: string) {
  const itemDate = new Date(dateStr)
  const now = new Date()

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  const targetDay = new Date(itemDate.getFullYear(), itemDate.getMonth(), itemDate.getDate())

  if (targetDay.getTime() === today.getTime()) return "Today"
  if (targetDay.getTime() === yesterday.getTime()) return "Yesterday"

  return itemDate.toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

function getHistoryDayKey(dateStr: string) {
  const date = new Date(dateStr)
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

function groupHistoryItemsByDay(items: SeriesHistoryItem[]) {
  const groups = new Map<string, { label: string; items: SeriesHistoryItem[] }>()

  items.forEach((item) => {
    const key = getHistoryDayKey(item.date)
    const existing = groups.get(key)

    if (existing) {
      existing.items.push(item)
      return
    }

    groups.set(key, {
      label: formatDayHeader(item.date),
      items: [item],
    })
  })

  return Array.from(groups.entries()).map(([key, value]) => ({
    key,
    label: value.label,
    items: value.items,
  }))
}

export default function HistoryPage() {
  const router = useRouter()
  const { accent } = useAccent()
  const [historyItems, setHistoryItems] = useState<SeriesHistoryItem[]>([])
  const [expandedItem, setExpandedItem] = useState<string | null>(null)
  const [selectedSeriesByItem, setSelectedSeriesByItem] = useState<Record<string, number>>({})

  // Dynamic accent classes
  const accentText = accent === "orange" ? "text-orange-500" : accent === "green" ? "text-green-500" : "text-blue-500"
  const accentBg = accent === "orange" ? "bg-orange-500" : accent === "green" ? "bg-green-500" : "bg-blue-500"
  const accentBgLight = accent === "orange" ? "bg-orange-600/90" : accent === "green" ? "bg-green-600/90" : "bg-blue-600/90"
  const accentBgTable = accent === "orange" ? "bg-orange-600/80" : accent === "green" ? "bg-green-600/80" : "bg-blue-600/80"

  useEffect(() => {
    const loggedIn = localStorage.getItem("lakshya_logged_in")
    if (!loggedIn) {
      router.push("/login")
      return
    }

    setHistoryItems(getAllHistory())
  }, [router])

  const handleClearHistory = () => {
    if (confirm("Clear all series history? This cannot be undone.")) {
      clearAllHistory()
      setHistoryItems([])
    }
  }

  const handleDeleteItem = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirm("Delete this series record?")) {
      deleteHistoryItem(id)
      setHistoryItems(getAllHistory())
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    })
  }

  const formatTime = (dateStr: string) => {
    return new Date(dateStr).toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    })
  }

  const formatShotTime = (ts?: number) => {
    if (!ts) return "-"
    return new Date(ts * 1000).toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
  }

  const formatSessionMode = (mode?: string) => {
    switch (mode) {
      case "tournament": return "Tournament"
      case "free_training": return "Free Training"
      case "training": return "Training"
      default: return "Training"
    }
  }

  const getSessionModeColor = (mode?: string) => {
    switch (mode) {
      case "tournament": return "bg-purple-500 text-white"
      case "free_training": return "bg-emerald-500 text-white"
      case "training": return "bg-cyan-500 text-white"
      default: return "bg-gray-500 text-white"
    }
  }

  const historyGroups = groupHistoryItemsByDay(historyItems)

  return (
    <div className="flex h-screen bg-background">
      <Sidebar activeSection="history" />

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="h-16 bg-card border-b border-border flex items-center justify-between px-6">
          <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <HistoryIcon className={`w-6 h-6 ${accentText}`} />
            SERIES HISTORY
          </h1>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/history/demo")}
              className="border-border text-foreground hover:bg-accent"
            >
              <FlaskConical className="w-4 h-4 mr-2" />
              Demo
            </Button>
            {historyItems.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearHistory}
                className="border-red-500/50 text-red-400 hover:bg-red-500/10"
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Clear All
              </Button>
            )}
          </div>
        </div>

        <div className="flex-1 p-6 overflow-auto">
          {historyItems.length > 0 ? (
            <div className="space-y-4">
              {historyGroups.map((group) => (
                <section key={group.key} className="space-y-3">
                  <div className="sticky top-0 z-10 flex items-center gap-3 bg-background/95 py-1 backdrop-blur supports-[backdrop-filter]:bg-background/80">
                    <div className="h-px flex-1 bg-border" />
                    <div className="rounded-full border border-border bg-muted px-4 py-1 text-sm font-semibold text-foreground">
                      {group.label}
                    </div>
                    <div className="h-px flex-1 bg-border" />
                  </div>

                  <div className="space-y-4">
                    {group.items.map((item) => (
                      <Card key={item.id} className="bg-card border-border overflow-hidden">
                  {(() => {
                    const seriesGroups = groupHistoryShots(item)
                    const selectedSeriesIndex = selectedSeriesByItem[item.id] ?? 0
                    const activeSeries = seriesGroups[selectedSeriesIndex] || seriesGroups[0]

                    return (
                      <>
                  {/* Header Row - Uses accent color */}
                  <CardHeader className={`pb-2 ${accentBgLight}`}>
                    <div
                      className="flex items-center justify-between cursor-pointer"
                      onClick={() => {
                        setExpandedItem(expandedItem === item.id ? null : item.id)
                        setSelectedSeriesByItem((current) => (
                          current[item.id] !== undefined ? current : { ...current, [item.id]: 0 }
                        ))
                      }}
                    >
                      <div className="flex items-center gap-3 flex-wrap">
                        <div className="flex items-center gap-2 text-white text-sm">
                          <Calendar className="w-4 h-4" />
                          {formatDate(item.date)}
                        </div>
                        <div className="flex items-center gap-2 text-white text-sm">
                          <Clock className="w-4 h-4" />
                          {formatTime(item.date)}
                        </div>
                        {/* Shooting Mode Badge */}
                        <span className={`text-xs px-2 py-1 rounded font-semibold ${
                          item.mode === "rifle"
                            ? "bg-orange-500 text-white"
                            : "bg-blue-500 text-white"
                        }`}>
                          {item.mode.toUpperCase()}
                        </span>
                        {/* Session Mode Badge */}
                        <span className={`text-xs px-2 py-1 rounded font-semibold ${getSessionModeColor(item.sessionMode)}`}>
                          {formatSessionMode(item.sessionMode)}
                        </span>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right text-white">
                          <div className="text-sm opacity-80">{item.shots.length} shots</div>
                          <div className="text-xl font-bold">
                            {item.totalScore.toFixed(1)}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => handleDeleteItem(item.id, e)}
                          className="text-white/70 hover:text-red-300 hover:bg-red-500/20"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                        {expandedItem === item.id ? (
                          <ChevronUp className="w-5 h-5 text-white" />
                        ) : (
                          <ChevronDown className="w-5 h-5 text-white" />
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  
                  {/* Expanded Content: 2-Column Layout */}
                  {expandedItem === item.id && (
                    <CardContent className="p-4 space-y-6">
                      <div className="grid grid-cols-1 xl:grid-cols-[1.2fr_0.95fr] gap-6">
                        <div className="rounded-xl border border-border overflow-hidden">
                          <div className={`${accentBgTable} px-4 py-3 text-white font-semibold`}>
                            All Shots
                          </div>
                          <div className="max-h-[420px] overflow-auto">
                            <table className="w-full">
                              <thead className="bg-muted/70 sticky top-0">
                                <tr>
                                  <th className="py-2 px-3 text-left font-semibold text-sm">S.N</th>
                                  <th className="py-2 px-3 text-left font-semibold text-sm">SERIES</th>
                                  <th className="py-2 px-3 text-center font-semibold text-sm">SCORE</th>
                                  <th className="py-2 px-3 text-right font-semibold text-sm">TIME</th>
                                </tr>
                              </thead>
                              <tbody>
                                {item.shots.map((shot, index) => (
                                  <tr
                                    key={shot.id || index}
                                    className={`border-b border-border/50 ${
                                      index % 2 === 0 ? "bg-muted/30" : "bg-background"
                                    }`}
                                  >
                                    <td className="py-2 px-3 text-left text-foreground font-medium">
                                      {index + 1}
                                    </td>
                                    <td className="py-2 px-3 text-left text-muted-foreground text-sm">
                                      {shot.series || `Series ${Math.floor(index / 10) + 1}`}
                                    </td>
                                    <td className={`py-2 px-3 text-center font-bold ${
                                      shot.score >= 10 ? "text-green-500" :
                                      shot.score >= 9 ? "text-emerald-500" :
                                      shot.score >= 8 ? "text-yellow-500" :
                                      "text-orange-500"
                                    }`}>
                                      {shot.score.toFixed(1)}
                                    </td>
                                    <td className="py-2 px-3 text-right text-muted-foreground text-sm">
                                      {formatShotTime(shot.ts)}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>

                          <div className="border-t border-border bg-muted/30 p-4 space-y-2">
                            <div className="flex justify-between items-center">
                              <span className="font-semibold text-foreground">TOTAL:</span>
                              <span className={`text-xl font-bold ${accentText}`}>
                                {item.totalScore.toFixed(1)}
                              </span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="font-semibold text-foreground">INNER 10:</span>
                              <span className="text-lg font-bold text-green-500">
                                {item.inner10}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="p-4 flex items-center justify-center bg-muted/20 rounded-xl border border-border">
                          <div className="relative w-full max-w-[400px] aspect-square">
                            {item.imageUrl ? (
                              <>
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img
                                  src={item.imageUrl}
                                  alt="Target"
                                  className="w-full h-full object-contain rounded-lg"
                                  onError={(e) => {
                                    const target = e.currentTarget as HTMLImageElement
                                    target.style.display = "none"
                                  }}
                                />
                                {item.shots.map((shot, index) => {
                                  const mapped = mapShotToHistoryTarget(shot, item.mode)
                                  return (
                                    <div
                                      key={shot.id || index}
                                      className="absolute w-4 h-4 rounded-full border-2 border-red-500 bg-red-500/50 transform -translate-x-1/2 -translate-y-1/2 flex items-center justify-center"
                                      style={{
                                        left: `${mapped.xPercent}%`,
                                        top: `${mapped.yPercent}%`,
                                      }}
                                      title={`Shot ${index + 1}: ${shot.score.toFixed(1)}`}
                                    >
                                      <span className="text-[8px] font-bold text-white">
                                        {index + 1}
                                      </span>
                                    </div>
                                  )
                                })}
                              </>
                            ) : (
                              <div className="w-full h-full flex items-center justify-center bg-muted rounded-lg">
                                <div className="text-center text-muted-foreground">
                                  <Target className="w-16 h-16 mx-auto mb-2 opacity-50" />
                                  <p className="text-sm">No image available</p>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      {seriesGroups.length > 0 && (
                        <>
                          <div className="space-y-3">
                            <div className="flex items-center gap-2">
                              <Target className={`w-5 h-5 ${accentText}`} />
                              <h3 className="text-lg font-semibold text-foreground">Series</h3>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
                              {seriesGroups.map((series) => (
                                <Button
                                  key={`${item.id}-${series.label}`}
                                  variant={selectedSeriesIndex === series.index ? "default" : "outline"}
                                  onClick={() => setSelectedSeriesByItem((current) => ({
                                    ...current,
                                    [item.id]: series.index,
                                  }))}
                                  className={`h-auto py-3 px-4 justify-between ${
                                    selectedSeriesIndex === series.index ? accentBg : "border-border"
                                  }`}
                                >
                                  <span className="text-left">{series.label}</span>
                                  <span className="text-right">
                                    {series.shots.length} shots | {series.total.toFixed(1)}
                                  </span>
                                </Button>
                              ))}
                            </div>
                          </div>

                          {activeSeries && (
                            <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_0.95fr] gap-6">
                              <div className="rounded-xl border border-border overflow-hidden">
                                <div className={`${accentBgTable} px-4 py-3 text-white font-semibold`}>
                                  {activeSeries.label}
                                </div>
                                <table className="w-full">
                                  <thead className="bg-muted/70">
                                    <tr>
                                      <th className="py-2 px-3 text-left font-semibold text-sm">S.N</th>
                                      <th className="py-2 px-3 text-center font-semibold text-sm">SCORE</th>
                                      <th className="py-2 px-3 text-right font-semibold text-sm">TIME</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {activeSeries.shots.map((shot, index) => (
                                      <tr
                                        key={shot.id || index}
                                        className={`border-b border-border/50 ${
                                          index % 2 === 0 ? "bg-muted/30" : "bg-background"
                                        }`}
                                      >
                                        <td className="py-2 px-3 text-left text-foreground font-medium">
                                          {index + 1}
                                        </td>
                                        <td className={`py-2 px-3 text-center font-bold ${
                                          shot.score >= 10 ? "text-green-500" :
                                          shot.score >= 9 ? "text-emerald-500" :
                                          shot.score >= 8 ? "text-yellow-500" :
                                          "text-orange-500"
                                        }`}>
                                          {shot.score.toFixed(1)}
                                        </td>
                                        <td className="py-2 px-3 text-right text-muted-foreground text-sm">
                                          {formatShotTime(shot.ts)}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                                <div className="border-t border-border bg-muted/30 px-4 py-3 flex items-center justify-between">
                                  <span className="font-semibold text-foreground">SERIES TOTAL:</span>
                                  <span className={`text-lg font-bold ${accentText}`}>
                                    {activeSeries.total.toFixed(1)}
                                  </span>
                                </div>
                              </div>

                              <div className="p-4 flex items-center justify-center bg-muted/20 rounded-xl border border-border">
                                <div className="relative w-full max-w-[400px] aspect-square">
                                  {item.imageUrl ? (
                                    <>
                                      {/* eslint-disable-next-line @next/next/no-img-element */}
                                      <img
                                        src={item.imageUrl}
                                        alt="Series target"
                                        className="w-full h-full object-contain rounded-lg"
                                        onError={(e) => {
                                          const target = e.currentTarget as HTMLImageElement
                                          target.style.display = "none"
                                        }}
                                      />
                                      {activeSeries.shots.map((shot, index) => {
                                        const mapped = mapShotToHistoryTarget(shot, item.mode)
                                        return (
                                          <div
                                            key={shot.id || index}
                                            className="absolute w-5 h-5 rounded-full border-2 border-red-500 bg-red-500/60 transform -translate-x-1/2 -translate-y-1/2 flex items-center justify-center"
                                            style={{
                                              left: `${mapped.xPercent}%`,
                                              top: `${mapped.yPercent}%`,
                                            }}
                                            title={`${activeSeries.label} shot ${index + 1}: ${shot.score.toFixed(1)}`}
                                          >
                                            <span className="text-[8px] font-bold text-white">
                                              {index + 1}
                                            </span>
                                          </div>
                                        )
                                      })}
                                    </>
                                  ) : (
                                    <div className="w-full h-full flex items-center justify-center bg-muted rounded-lg">
                                      <div className="text-center text-muted-foreground">
                                        <Target className="w-16 h-16 mx-auto mb-2 opacity-50" />
                                        <p className="text-sm">No image available</p>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          )}
                        </>
                      )}
                    </CardContent>
                  )}
                      </>
                    )
                  })()}
                      </Card>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <Target className="w-16 h-16 mx-auto mb-4 opacity-50" />
              <p className="text-lg">No series history</p>
              <p className="text-sm mt-2">Complete a series to see it here</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
