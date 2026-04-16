"use client"

import { useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import {
  ChevronLeft,
  FlaskConical,
  History as HistoryIcon,
  Target,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { Shot } from "@/lib/api"
import Sidebar from "@/components/sidebar"
import { useAccent } from "@/components/accent-provider"

type DemoMode = "rifle" | "pistol"

type TargetAlignment = {
  liveCenterX: number
  liveCenterY: number
  liveOuterRadius: number
  staticCenterX: number
  staticCenterY: number
  staticOuterRadius: number
}

type DemoDataset = {
  mode: DemoMode
  label: string
  imageUrl: string
  shots: Shot[]
}

const TARGET_ALIGNMENTS: Record<DemoMode, TargetAlignment> = {
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

function createDemoShots(mode: DemoMode, scores: number[], startTs: number): Shot[] {
  const alignment = TARGET_ALIGNMENTS[mode]
  const angleOffset = mode === "rifle" ? 12 : 26

  return scores.map((score, index) => {
    const sequence = index + 1
    const angle = (sequence * 37 + angleOffset) % 360
    const radians = (angle * Math.PI) / 180
    const radiusFactor = mode === "rifle"
      ? Math.max(0.02, (10.9 - score) / 10.4)
      : Math.max(0.08, (10.9 - score) / 10.8)
    const radius = alignment.liveOuterRadius * radiusFactor
    const dx = Math.cos(radians) * radius
    const dy = Math.sin(radians) * radius

    return {
      id: sequence,
      score,
      x: alignment.liveCenterX + dx,
      y: alignment.liveCenterY - dy,
      center_x: alignment.liveCenterX,
      center_y: alignment.liveCenterY,
      dx,
      dy,
      angle,
      ts: startTs + index * 45,
      series: `Series ${Math.floor(index / 10) + 1}`,
    }
  })
}

function mapShotToHistoryTarget(shot: Shot, mode: DemoMode) {
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

function formatShotTime(ts?: number) {
  if (!ts) return "-"
  return new Date(ts * 1000).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

const rifleScores = [
  10.7, 10.4, 10.1, 9.9, 10.5, 10.2, 9.8, 10.6, 10.0, 9.7,
  10.3, 10.8, 10.1, 9.6, 10.4, 9.9, 10.7, 10.0, 9.8, 10.2,
  10.5, 9.7, 10.6, 10.1, 9.9, 10.4, 10.2, 9.8, 10.3, 10.7,
  10.0, 9.9, 10.5, 10.1, 9.8, 10.6, 10.2, 9.7, 10.4, 10.8,
]

const pistolScores = [
  9.8, 10.0, 9.5, 9.9, 10.2, 9.7, 10.1, 9.6, 10.3, 9.8,
  10.0, 9.4, 10.4, 9.7, 9.9, 10.1, 9.6, 10.2, 9.8, 9.5,
  10.3, 9.9, 9.7, 10.0, 9.6, 10.1, 9.8, 9.4, 10.2, 9.7,
  10.0, 9.5, 10.4, 9.8, 9.6, 10.1, 9.9, 9.7, 10.2, 9.8,
]

const DEMO_DATA: Record<DemoMode, DemoDataset> = {
  rifle: {
    mode: "rifle",
    label: "Rifle Demo",
    imageUrl: "/history-rifle-target.svg",
    shots: createDemoShots("rifle", rifleScores, 1711015200),
  },
  pistol: {
    mode: "pistol",
    label: "Pistol Demo",
    imageUrl: "/history-pistol-target.svg",
    shots: createDemoShots("pistol", pistolScores, 1711022400),
  },
}

export default function HistoryDemoPage() {
  const router = useRouter()
  const { accent } = useAccent()
  const [selectedMode, setSelectedMode] = useState<DemoMode>("rifle")
  const [selectedSeries, setSelectedSeries] = useState(0)

  const accentText = accent === "orange" ? "text-orange-500" : accent === "green" ? "text-green-500" : "text-blue-500"
  const accentBg = accent === "orange" ? "bg-orange-600/90" : accent === "green" ? "bg-green-600/90" : "bg-blue-600/90"
  const accentBorder = accent === "orange" ? "border-orange-500/50" : accent === "green" ? "border-green-500/50" : "border-blue-500/50"
  const accentSoftBg = accent === "orange" ? "bg-orange-500/10" : accent === "green" ? "bg-green-500/10" : "bg-blue-500/10"

  useEffect(() => {
    const loggedIn = localStorage.getItem("lakshya_logged_in")
    if (!loggedIn) {
      router.push("/login")
    }
  }, [router])

  const dataset = DEMO_DATA[selectedMode]

  const seriesGroups = useMemo(() => {
    return Array.from({ length: 4 }, (_, index) => {
      const shots = dataset.shots.slice(index * 10, index * 10 + 10)
      const total = shots.reduce((sum, shot) => sum + shot.score, 0)
      return {
        index,
        label: `Series ${index + 1}`,
        shots,
        total,
      }
    })
  }, [dataset])

  const activeSeries = seriesGroups[selectedSeries]
  const totalScore = dataset.shots.reduce((sum, shot) => sum + shot.score, 0)
  const inner10 = dataset.shots.filter((shot) => shot.score >= 10).length

  return (
    <div className="flex h-screen bg-background">
      <Sidebar activeSection="history" />

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="h-16 bg-card border-b border-border flex items-center justify-between px-6">
          <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <HistoryIcon className={`w-6 h-6 ${accentText}`} />
            HISTORY DEMO
          </h1>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/history")}
              className="border-border text-foreground hover:bg-accent"
            >
              <ChevronLeft className="w-4 h-4 mr-2" />
              Back To History
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-6 space-y-6">
          <Card className="bg-card border-border">
            <CardHeader className={`border-b ${accentBorder}`}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-foreground">
                    <FlaskConical className={`w-5 h-5 ${accentText}`} />
                    Demo History File
                  </CardTitle>
                  <p className="text-sm text-muted-foreground mt-2">
                    Static rifle and pistol history with 40 shots each. The live history page and saved data are untouched.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {(["rifle", "pistol"] as DemoMode[]).map((mode) => (
                    <Button
                      key={mode}
                      variant={selectedMode === mode ? "default" : "outline"}
                      onClick={() => {
                        setSelectedMode(mode)
                        setSelectedSeries(0)
                      }}
                      className={selectedMode === mode ? accentBg : ""}
                    >
                      {mode === "rifle" ? "Rifle 40 Shots" : "Pistol 40 Shots"}
                    </Button>
                  ))}
                </div>
              </div>
            </CardHeader>

            <CardContent className="p-6">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className={`rounded-lg border ${accentBorder} ${accentSoftBg} p-4`}>
                  <div className="text-sm text-muted-foreground">Selected Demo</div>
                  <div className="mt-1 text-2xl font-bold text-foreground">{dataset.label}</div>
                </div>
                <div className={`rounded-lg border ${accentBorder} ${accentSoftBg} p-4`}>
                  <div className="text-sm text-muted-foreground">Total Score</div>
                  <div className={`mt-1 text-2xl font-bold ${accentText}`}>{totalScore.toFixed(1)}</div>
                </div>
                <div className={`rounded-lg border ${accentBorder} ${accentSoftBg} p-4`}>
                  <div className="text-sm text-muted-foreground">Shots / Inner 10</div>
                  <div className="mt-1 text-2xl font-bold text-foreground">
                    {dataset.shots.length} / <span className="text-green-500">{inner10}</span>
                  </div>
                </div>
              </div>

              <div className="mt-6 grid grid-cols-1 xl:grid-cols-[1.25fr_0.95fr] gap-6">
                <div className="rounded-xl border border-border overflow-hidden">
                  <div className={`${accentBg} px-4 py-3 text-white font-semibold`}>
                    First 40 Shots
                  </div>
                  <div className="max-h-[480px] overflow-auto">
                    <table className="w-full">
                      <thead className="bg-muted/70 sticky top-0">
                        <tr>
                          <th className="py-2 px-3 text-left text-sm font-semibold">S.N</th>
                          <th className="py-2 px-3 text-left text-sm font-semibold">Series</th>
                          <th className="py-2 px-3 text-center text-sm font-semibold">Score</th>
                          <th className="py-2 px-3 text-right text-sm font-semibold">Time</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dataset.shots.map((shot, index) => (
                          <tr
                            key={shot.id}
                            className={`border-t border-border/60 ${index % 2 === 0 ? "bg-background" : "bg-muted/20"}`}
                          >
                            <td className="py-2 px-3 font-medium text-foreground">{index + 1}</td>
                            <td className="py-2 px-3 text-muted-foreground">{shot.series}</td>
                            <td className={`py-2 px-3 text-center font-bold ${
                              shot.score >= 10 ? "text-green-500" :
                              shot.score >= 9.5 ? "text-yellow-500" :
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
                </div>

                <div className="rounded-xl border border-border p-4 bg-muted/10">
                  <div className="flex items-center justify-between gap-3 mb-4">
                    <div>
                      <h2 className="text-lg font-semibold text-foreground">40 Shot Target View</h2>
                      <p className="text-sm text-muted-foreground">{dataset.mode.toUpperCase()} demo overlay</p>
                    </div>
                    <div className={`rounded-full px-3 py-1 text-xs font-semibold ${
                      dataset.mode === "rifle" ? "bg-orange-500 text-white" : "bg-blue-500 text-white"
                    }`}>
                      {dataset.mode.toUpperCase()}
                    </div>
                  </div>
                  <div className="relative mx-auto w-full max-w-[430px] aspect-square">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={dataset.imageUrl}
                      alt={`${dataset.mode} target`}
                      className="w-full h-full object-contain rounded-lg"
                    />
                    {dataset.shots.map((shot, index) => {
                      const mapped = mapShotToHistoryTarget(shot, dataset.mode)
                      return (
                        <div
                          key={shot.id}
                          className="absolute w-5 h-5 rounded-full border-2 border-red-500 bg-red-500/60 transform -translate-x-1/2 -translate-y-1/2 flex items-center justify-center"
                          style={{
                            left: `${mapped.xPercent}%`,
                            top: `${mapped.yPercent}%`,
                          }}
                          title={`Shot ${index + 1}: ${shot.score.toFixed(1)}`}
                        >
                          <span className="text-[8px] font-bold text-white">{index + 1}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>

              <div className="mt-8">
                <div className="mb-3 flex items-center gap-2">
                  <Target className={`w-5 h-5 ${accentText}`} />
                  <h2 className="text-lg font-semibold text-foreground">4 Series Buttons</h2>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
                  {seriesGroups.map((series) => (
                    <Button
                      key={series.label}
                      variant={selectedSeries === series.index ? "default" : "outline"}
                      onClick={() => setSelectedSeries(series.index)}
                      className={`h-auto py-3 px-4 justify-between ${
                        selectedSeries === series.index ? accentBg : "border-border"
                      }`}
                    >
                      <span className="text-left">
                        {series.label}
                      </span>
                      <span className="text-right">
                        {series.shots.length} shots | {series.total.toFixed(1)}
                      </span>
                    </Button>
                  ))}
                </div>
              </div>

              <div className="mt-6 grid grid-cols-1 xl:grid-cols-[1.15fr_0.95fr] gap-6">
                <div className="rounded-xl border border-border overflow-hidden">
                  <div className={`${accentBg} px-4 py-3 text-white font-semibold`}>
                    {activeSeries.label} - 10 Shots
                  </div>
                  <div>
                    <table className="w-full">
                      <thead className="bg-muted/70">
                        <tr>
                          <th className="py-2 px-3 text-left text-sm font-semibold">S.N</th>
                          <th className="py-2 px-3 text-center text-sm font-semibold">Score</th>
                          <th className="py-2 px-3 text-right text-sm font-semibold">Time</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activeSeries.shots.map((shot, index) => (
                          <tr
                            key={shot.id}
                            className={`border-t border-border/60 ${index % 2 === 0 ? "bg-background" : "bg-muted/20"}`}
                          >
                            <td className="py-2 px-3 font-medium text-foreground">{index + 1}</td>
                            <td className={`py-2 px-3 text-center font-bold ${
                              shot.score >= 10 ? "text-green-500" :
                              shot.score >= 9.5 ? "text-yellow-500" :
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
                      <span className="font-semibold text-foreground">Series Total</span>
                      <span className={`text-lg font-bold ${accentText}`}>{activeSeries.total.toFixed(1)}</span>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-border p-4 bg-muted/10">
                  <div className="flex items-center justify-between gap-3 mb-4">
                    <div>
                      <h2 className="text-lg font-semibold text-foreground">{activeSeries.label} Target</h2>
                      <p className="text-sm text-muted-foreground">Selected 10-shot series overlay</p>
                    </div>
                    <div className={`rounded-full px-3 py-1 text-xs font-semibold ${accentSoftBg} ${accentText}`}>
                      10 SHOTS
                    </div>
                  </div>
                  <div className="relative mx-auto w-full max-w-[430px] aspect-square">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={dataset.imageUrl}
                      alt={`${dataset.mode} series target`}
                      className="w-full h-full object-contain rounded-lg"
                    />
                    {activeSeries.shots.map((shot, index) => {
                      const mapped = mapShotToHistoryTarget(shot, dataset.mode)
                      return (
                        <div
                          key={shot.id}
                          className="absolute w-6 h-6 rounded-full border-2 border-red-500 bg-red-500/70 transform -translate-x-1/2 -translate-y-1/2 flex items-center justify-center"
                          style={{
                            left: `${mapped.xPercent}%`,
                            top: `${mapped.yPercent}%`,
                          }}
                          title={`${activeSeries.label} shot ${index + 1}: ${shot.score.toFixed(1)}`}
                        >
                          <span className="text-[9px] font-bold text-white">{index + 1}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
